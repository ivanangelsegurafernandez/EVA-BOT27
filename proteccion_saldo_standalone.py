#!/usr/bin/env python3
"""
Monitor standalone de protección de saldo REAL DERIV.

Características clave:
- Lectura robusta de fuentes de saldo con prioridad real.
- Detección de protección por quiebre estructural o EMA + drawdown.
- Pausa real de 30 minutos sin reinicios/intermitencias.
- UI limpia con PySide6 + pyqtgraph.
- Audio básico en transiciones de estado (Windows).

Requiere: Python 3.10+, PySide6, pyqtgraph, pandas, numpy.
"""

from __future__ import annotations

import glob
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PySide6 import QtCore, QtGui, QtWidgets

try:
    import winsound  # Solo Windows
except Exception:
    winsound = None


# ---------------------------- Configuración ----------------------------
APP_TITLE = "Protección Saldo REAL DERIV"
REFRESH_MS = 4000
PAUSE_MINUTES = 30

EMA_ALERTA_SPAN = 9
EMA_CALMA_SPAN = 21
DD_PROTECTION_THRESHOLD_PCT = -4.0
DD_RECOVERY_MARGIN_PCT = 1.0

STRUCT_WINDOW = 60
STD_FACTOR = 1.5
EQUITY_BREAK_DRAWDOWN = -2.5
EQUITY_BREAK_FAST_DROP = -1.8

HIDE_CONFIRM_REFRESHES = 3

BASE_DIR = Path(__file__).resolve().parent
SALDO_REAL_SERIES_FILE = BASE_DIR / "saldo_real_series.csv"
SALDO_REAL_LIVE_FILE = BASE_DIR / "saldo_real_live.json"
SALDO_REAL_HISTORY_FILE = BASE_DIR / "saldo_real_live_history.jsonl"
LOG_SALDOS_DIR = BASE_DIR / "LOG_SALDOS"
AUX_ENR_PATTERN = str(BASE_DIR / "registro_enriquecido_fulll*.csv")


# ---------------------------- Utilidades ----------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_money(value: Optional[float]) -> str:
    if value is None or not np.isfinite(value):
        return "--"
    return f"{value:,.2f} USD"


def fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "--"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def fmt_countdown(seconds_left: int) -> str:
    s = max(0, int(seconds_left))
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"


def beep_activated() -> None:
    if winsound:
        try:
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
        except Exception:
            pass


def beep_cleared() -> None:
    if winsound:
        try:
            winsound.MessageBeep(winsound.MB_OK)
        except Exception:
            pass


# ---------------------------- Detección ----------------------------
def detect_equity_structure_break(equity_series: pd.Series) -> tuple[bool, str]:
    """Ruta A: quiebre estructural sobre ventana reciente."""
    clean = pd.to_numeric(equity_series, errors="coerce").dropna()
    if len(clean) < 20:
        return False, ""

    window = clean.tail(min(STRUCT_WINDOW, len(clean))).reset_index(drop=True)
    x = np.arange(len(window), dtype=float)
    y = window.to_numpy(dtype=float)

    if len(y) < 20:
        return False, ""

    # Tendencia lineal + desvío residual
    slope, intercept = np.polyfit(x, y, 1)
    trend = slope * x + intercept
    residuals = y - trend
    std = float(np.std(residuals)) if len(residuals) > 1 else 0.0

    if std > 0 and y[-1] < (trend[-1] - STD_FACTOR * std):
        return True, "ruptura_tendencia_equity"

    local_peak = float(np.max(y))
    if local_peak > 0:
        local_dd = ((y[-1] - local_peak) / local_peak) * 100.0
        if local_dd <= EQUITY_BREAK_DRAWDOWN:
            return True, "drawdown_equity"

    if len(y) >= 5:
        fast_drop = y[-1] - y[-5]
        if fast_drop <= EQUITY_BREAK_FAST_DROP:
            return True, "caida_rapida_equity"

    return False, ""


def should_pause_by_ema_drawdown(ema_alerta: float, ema_calma: float, drawdown_pct: float) -> bool:
    """Ruta B: EMA alerta por debajo de EMA calma + drawdown bajo umbral."""
    if not all(np.isfinite(v) for v in [ema_alerta, ema_calma, drawdown_pct]):
        return False
    return ema_alerta < ema_calma and drawdown_pct <= DD_PROTECTION_THRESHOLD_PCT


@dataclass
class Metrics:
    equity_series: pd.Series
    ts_series: pd.Series
    equity_actual: float
    ema_alerta: float
    ema_calma: float
    peak_equity: float
    drawdown_pct: float


@dataclass
class ProtectionState:
    active: bool = False
    reason: str = ""
    started_ts: Optional[datetime] = None
    until_ts: Optional[datetime] = None
    rearme_blocked: bool = False
    hide_confirmation_counter: int = 0
    last_print_bucket: int = -1


class DataLoader:
    """Carga de datos con prioridad real y auxiliares como respaldo visual."""

    def load_equity_df(self) -> pd.DataFrame:
        errors: list[str] = []

        # Prioridad principal para protección
        try:
            if SALDO_REAL_SERIES_FILE.exists():
                df = pd.read_csv(SALDO_REAL_SERIES_FILE)
                df = self._normalize_df(df, source="saldo_real_series.csv")
                if not df.empty:
                    return df
        except Exception as ex:
            errors.append(f"series_csv: {ex}")

        # Fallback 1: history jsonl
        try:
            if SALDO_REAL_HISTORY_FILE.exists():
                rows = []
                with SALDO_REAL_HISTORY_FILE.open("r", encoding="utf-8", errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            rows.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                if rows:
                    df = pd.DataFrame(rows)
                    df = self._normalize_df(df, source="saldo_real_live_history.jsonl")
                    if not df.empty:
                        return df
        except Exception as ex:
            errors.append(f"history_jsonl: {ex}")

        # Fallback 2: snapshot json
        try:
            if SALDO_REAL_LIVE_FILE.exists():
                data = json.loads(SALDO_REAL_LIVE_FILE.read_text(encoding="utf-8", errors="ignore"))
                if isinstance(data, dict):
                    df = pd.DataFrame([data])
                    df = self._normalize_df(df, source="saldo_real_live.json")
                    if not df.empty:
                        return df
        except Exception as ex:
            errors.append(f"live_json: {ex}")

        # Auxiliar: csv enriquecido
        try:
            aux_csv = sorted(glob.glob(AUX_ENR_PATTERN))
            if aux_csv:
                df = pd.read_csv(aux_csv[-1])
                df = self._normalize_df(df, source=os.path.basename(aux_csv[-1]))
                if not df.empty:
                    return df
        except Exception as ex:
            errors.append(f"aux_enriquecido: {ex}")

        # Auxiliar final: logs parseados
        try:
            df = self._load_from_logs()
            if not df.empty:
                return df
        except Exception as ex:
            errors.append(f"logs: {ex}")

        if errors:
            print("PROTECCION_SALDO: warning carga fuentes ->", " | ".join(errors))
        return pd.DataFrame(columns=["ts", "equity", "source"])

    def _normalize_df(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        work = df.copy()
        cols = {c.lower().strip(): c for c in work.columns}

        ts_col = None
        for candidate in ["ts", "timestamp", "time", "fecha_hora", "datetime", "date"]:
            if candidate in cols:
                ts_col = cols[candidate]
                break

        eq_col = None
        if "equity" in cols:
            eq_col = cols["equity"]
        elif "saldo_real" in cols:
            eq_col = cols["saldo_real"]
        elif "saldo" in cols:
            eq_col = cols["saldo"]

        if eq_col is None:
            return pd.DataFrame(columns=["ts", "equity", "source"])

        if ts_col is None:
            ts = pd.date_range(end=pd.Timestamp.utcnow(), periods=len(work), freq="min")
            work["ts"] = ts
        else:
            work["ts"] = pd.to_datetime(work[ts_col], errors="coerce", utc=True)

        work["equity"] = pd.to_numeric(work[eq_col], errors="coerce")
        work = work.dropna(subset=["ts", "equity"]).sort_values("ts").drop_duplicates(subset=["ts"], keep="last")
        work["source"] = source
        return work[["ts", "equity", "source"]].reset_index(drop=True)

    def _load_from_logs(self) -> pd.DataFrame:
        if not LOG_SALDOS_DIR.exists() or not LOG_SALDOS_DIR.is_dir():
            return pd.DataFrame(columns=["ts", "equity", "source"])

        paths = sorted(list(LOG_SALDOS_DIR.glob("*.log")) + list(LOG_SALDOS_DIR.glob("*.txt")))
        rows = []
        for p in paths[-5:]:
            try:
                for line in p.read_text(encoding="utf-8", errors="ignore").splitlines()[-500:]:
                    nums = [token for token in line.replace(",", " ").split() if token.replace(".", "", 1).replace("-", "", 1).isdigit()]
                    if not nums:
                        continue
                    eq = float(nums[-1])
                    ts = pd.Timestamp.utcnow()
                    rows.append({"ts": ts, "equity": eq, "source": p.name})
            except Exception:
                continue
        if not rows:
            return pd.DataFrame(columns=["ts", "equity", "source"])
        df = pd.DataFrame(rows)
        return self._normalize_df(df, source="LOG_SALDOS")


def compute_metrics(df: pd.DataFrame) -> Optional[Metrics]:
    if df.empty:
        return None

    eq = pd.to_numeric(df["equity"], errors="coerce").dropna()
    if eq.empty:
        return None

    ts = pd.to_datetime(df.loc[eq.index, "ts"], errors="coerce", utc=True)
    ts = ts.fillna(method="ffill")

    ema_alerta = float(eq.ewm(span=EMA_ALERTA_SPAN, adjust=False).mean().iloc[-1])
    ema_calma = float(eq.ewm(span=EMA_CALMA_SPAN, adjust=False).mean().iloc[-1])

    peak_equity = float(eq.cummax().iloc[-1])
    equity_actual = float(eq.iloc[-1])
    drawdown_pct = ((equity_actual - peak_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0

    return Metrics(
        equity_series=eq,
        ts_series=ts,
        equity_actual=equity_actual,
        ema_alerta=ema_alerta,
        ema_calma=ema_calma,
        peak_equity=peak_equity,
        drawdown_pct=drawdown_pct,
    )


class ProtectionEngine:
    """Fuente única de verdad del estado de protección."""

    def __init__(self) -> None:
        self.state = ProtectionState()

    def evaluate(self, metrics: Optional[Metrics], now: datetime) -> ProtectionState:
        if metrics is None:
            self._keep_or_finalize_without_metrics(now)
            return self.state

        structure_trigger, reason_structure = detect_equity_structure_break(metrics.equity_series)
        ema_trigger = should_pause_by_ema_drawdown(metrics.ema_alerta, metrics.ema_calma, metrics.drawdown_pct)
        raw_trigger = structure_trigger or ema_trigger
        reason = reason_structure if structure_trigger else "ema_drawdown"

        # Activa una sola vez, sin reiniciar reloj
        if not self.state.active:
            can_rearm = not self.state.rearme_blocked or self._recovery_confirmed(metrics)
            if can_rearm and raw_trigger:
                self._activate(now, reason, metrics.drawdown_pct)
            elif self.state.rearme_blocked and self._recovery_confirmed(metrics):
                self.state.rearme_blocked = False
        else:
            self._keep_active(now)

        # Finaliza solo por expiración real
        if self.state.active and self.state.until_ts and now >= self.state.until_ts:
            self._finalize("expirada")

        return self.state

    def _activate(self, now: datetime, reason: str, drawdown_pct: float) -> None:
        self.state.active = True
        self.state.reason = reason
        self.state.started_ts = now
        self.state.until_ts = now + timedelta(minutes=PAUSE_MINUTES)
        self.state.hide_confirmation_counter = 0
        self.state.last_print_bucket = -1
        beep_activated()
        print(f"PROTECCION_SALDO: ACTIVADA | reason={reason} | dd={drawdown_pct:.2f}% | pausa=30m")

    def _keep_active(self, now: datetime) -> None:
        if not self.state.until_ts:
            return
        remaining = int((self.state.until_ts - now).total_seconds())
        bucket = remaining // 10
        if bucket != self.state.last_print_bucket and remaining > 0:
            self.state.last_print_bucket = bucket
            print(f"PROTECCION_SALDO: ACTIVA | restante={fmt_countdown(remaining)}")

    def _finalize(self, cause: str) -> None:
        was_active = self.state.active
        self.state.active = False
        self.state.reason = ""
        self.state.started_ts = None
        self.state.until_ts = None
        self.state.rearme_blocked = True
        self.state.hide_confirmation_counter = 0
        self.state.last_print_bucket = -1
        if was_active:
            beep_cleared()
            print(f"PROTECCION_SALDO: FINALIZADA | sistema reanudado | causa={cause}")

    def _keep_or_finalize_without_metrics(self, now: datetime) -> None:
        if not self.state.active:
            return
        if self.state.until_ts and now >= self.state.until_ts:
            self._finalize("sin_metricas")
        else:
            self._keep_active(now)

    def _recovery_confirmed(self, metrics: Metrics) -> bool:
        dd_recovered = metrics.drawdown_pct > (DD_PROTECTION_THRESHOLD_PCT + DD_RECOVERY_MARGIN_PCT)
        ema_recovered = metrics.ema_alerta >= metrics.ema_calma
        return dd_recovered or ema_recovered

    def force_reset(self) -> None:
        self._finalize("reset_manual")
        self.state.rearme_blocked = False


class MonitorWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1460, 920)

        self.data_loader = DataLoader()
        self.engine = ProtectionEngine()

        self.current_metrics: Optional[Metrics] = None
        self.current_df = pd.DataFrame(columns=["ts", "equity", "source"])
        self.current_filter = "REAL"
        self.ui_pause = False

        self._build_ui()
        self._setup_timer()
        self.refresh_once()

    def _build_ui(self) -> None:
        pg.setConfigOptions(antialias=True, background="#131722", foreground="#e6edf7")
        root = QtWidgets.QWidget()
        self.setCentralWidget(root)
        lay = QtWidgets.QVBoxLayout(root)
        lay.setContentsMargins(10, 10, 10, 10)
        lay.setSpacing(8)

        # Encabezado
        self.lbl_title = QtWidgets.QLabel("SALDO REAL DERIV ACTUAL")
        self.lbl_title.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size: 34px; font-weight: 800; color: #f4f7ff;")

        self.lbl_equity = QtWidgets.QLabel("--")
        self.lbl_equity.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_equity.setStyleSheet("font-size: 54px; font-weight: 900; color: #8fffa3;")

        self.banner = QtWidgets.QLabel("PROTECCIÓN ACTIVADA")
        self.banner.setAlignment(QtCore.Qt.AlignCenter)
        self.banner.setStyleSheet(
            "font-size: 26px; font-weight: 900; color: white; "
            "background-color: #b00020; border: 2px solid #ff6b6b; border-radius: 6px; padding: 6px;"
        )
        self.banner.hide()

        lay.addWidget(self.lbl_title)
        lay.addWidget(self.lbl_equity)
        lay.addWidget(self.banner)

        # Bloque de detalle
        detail = QtWidgets.QFrame()
        detail.setStyleSheet("background:#1f2533;border:1px solid #3a4661;border-radius:6px;")
        dlay = QtWidgets.QGridLayout(detail)
        dlay.setContentsMargins(10, 10, 10, 10)
        dlay.setHorizontalSpacing(24)

        self.lbl_pause_title = QtWidgets.QLabel("MAESTRO EN PAUSA")
        self.lbl_pause_title.setStyleSheet("font-size: 18px; font-weight: 800; color:#ffbac3;")

        self.lbl_reason = QtWidgets.QLabel("Motivo: --")
        self.lbl_dd = QtWidgets.QLabel("Drawdown actual: --")
        self.lbl_start = QtWidgets.QLabel("Inicio pausa: --")
        self.lbl_until = QtWidgets.QLabel("Reanudación: --")
        for lbl in [self.lbl_reason, self.lbl_dd, self.lbl_start, self.lbl_until]:
            lbl.setStyleSheet("font-size: 14px; color:#dbe6ff;")

        self.lbl_timer = QtWidgets.QLabel("00:00")
        self.lbl_timer.setStyleSheet("font-size: 38px; font-weight: 900; color:#ffec99;")
        self.lbl_timer.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)

        dlay.addWidget(self.lbl_pause_title, 0, 0)
        dlay.addWidget(self.lbl_reason, 1, 0)
        dlay.addWidget(self.lbl_dd, 2, 0)
        dlay.addWidget(self.lbl_start, 0, 1)
        dlay.addWidget(self.lbl_until, 1, 1)
        dlay.addWidget(self.lbl_timer, 0, 2, 3, 1)

        lay.addWidget(detail)

        # Gráficas
        plots = QtWidgets.QGridLayout()
        self.plot_main = self._mk_plot("MAIN")
        self.plot_min = self._mk_plot("MINUTOS")
        self.plot_hour = self._mk_plot("HORAS")
        self.plot_day = self._mk_plot("DÍAS")

        plots.addWidget(self.plot_main, 0, 0)
        plots.addWidget(self.plot_min, 0, 1)
        plots.addWidget(self.plot_hour, 1, 0)
        plots.addWidget(self.plot_day, 1, 1)
        lay.addLayout(plots, 1)

        # Controles inferiores
        ctrl_row = QtWidgets.QHBoxLayout()
        self.btn_real = QtWidgets.QPushButton("REAL")
        self.btn_demo = QtWidgets.QPushButton("DEMO")
        self.btn_all = QtWidgets.QPushButton("ALL")
        self.btn_pause = QtWidgets.QPushButton("PAUSA")
        self.btn_reset_view = QtWidgets.QPushButton("RESET VISTA")
        self.btn_export = QtWidgets.QPushButton("EXPORTAR CSV")
        self.btn_reset_prot = QtWidgets.QPushButton("RESET PROTECCIÓN")

        for btn in [self.btn_real, self.btn_demo, self.btn_all, self.btn_pause, self.btn_reset_view, self.btn_export, self.btn_reset_prot]:
            btn.setMinimumHeight(34)
            btn.setStyleSheet("QPushButton{font-weight:700;background:#293246;color:#edf2ff;border:1px solid #455373;border-radius:5px;padding:5px;}QPushButton:hover{background:#36435f;}")
            ctrl_row.addWidget(btn)

        self.btn_real.setToolTip("Usa serie REAL para visualización (protección siempre usa equity real disponible).")
        self.btn_demo.setToolTip("Filtro visual reservado; no afecta la lógica de protección real.")
        self.btn_all.setToolTip("Muestra todo lo leído para inspección visual.")
        self.btn_pause.setToolTip("Pausa/reanuda refresco visual local.")
        self.btn_export.setToolTip("Exporta la vista actual a CSV.")
        self.btn_reset_prot.setToolTip("Limpia estado interno de protección de forma segura.")

        self.btn_real.clicked.connect(lambda: self._set_filter("REAL"))
        self.btn_demo.clicked.connect(lambda: self._set_filter("DEMO"))
        self.btn_all.clicked.connect(lambda: self._set_filter("ALL"))
        self.btn_pause.clicked.connect(self._toggle_pause_ui)
        self.btn_reset_view.clicked.connect(self._reset_view)
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_reset_prot.clicked.connect(self._reset_protection)

        lay.addLayout(ctrl_row)

        self._set_filter("REAL")

    def _mk_plot(self, title: str) -> pg.PlotWidget:
        w = pg.PlotWidget(title=title)
        w.showGrid(x=True, y=True, alpha=0.25)
        w.getAxis("left").setPen(pg.mkPen("#7f8ca8"))
        w.getAxis("bottom").setPen(pg.mkPen("#7f8ca8"))
        w.setLabel("left", "USD")
        return w

    def _setup_timer(self) -> None:
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh_once)
        self.timer.start()

    def _set_filter(self, mode: str) -> None:
        self.current_filter = mode
        for b, v in [(self.btn_real, "REAL"), (self.btn_demo, "DEMO"), (self.btn_all, "ALL")]:
            b.setStyleSheet(
                "QPushButton{font-weight:800;background:%s;color:white;border:1px solid #6f7f9f;border-radius:5px;padding:5px;}"
                % ("#0b6e4f" if mode == v else "#293246")
            )

    def _toggle_pause_ui(self) -> None:
        self.ui_pause = not self.ui_pause
        self.btn_pause.setText("REANUDAR" if self.ui_pause else "PAUSA")

    def _reset_view(self) -> None:
        for p in [self.plot_main, self.plot_min, self.plot_hour, self.plot_day]:
            p.enableAutoRange()

    def _reset_protection(self) -> None:
        self.engine.force_reset()
        self._render_status()

    def _export_csv(self) -> None:
        if self.current_df.empty:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), "No hay datos para exportar")
            return
        out = BASE_DIR / f"export_proteccion_saldo_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        try:
            self.current_df.to_csv(out, index=False)
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), f"Exportado: {out.name}")
        except Exception as ex:
            QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), f"Error exportando CSV: {ex}")

    def refresh_once(self) -> None:
        if self.ui_pause:
            return

        df = self.data_loader.load_equity_df()
        self.current_df = df
        metrics = compute_metrics(df)
        self.current_metrics = metrics

        state = self.engine.evaluate(metrics, now_utc())
        self._render_equity(metrics)
        self._render_status()
        self._render_plots(df)

        # Anti-intermitencia visual de ocultamiento
        if not state.active and self.banner.isVisible():
            state.hide_confirmation_counter += 1
            if state.hide_confirmation_counter >= HIDE_CONFIRM_REFRESHES:
                self.banner.hide()
        elif state.active:
            state.hide_confirmation_counter = 0
            self.banner.show()

    def _render_equity(self, metrics: Optional[Metrics]) -> None:
        if metrics is None:
            self.lbl_equity.setText("--")
            self.lbl_equity.setStyleSheet("font-size: 54px; font-weight: 900; color: #d8dee9;")
            return

        self.lbl_equity.setText(fmt_money(metrics.equity_actual))
        color = "#ff6b6b" if metrics.drawdown_pct <= DD_PROTECTION_THRESHOLD_PCT else "#8fffa3"
        self.lbl_equity.setStyleSheet(f"font-size: 54px; font-weight: 900; color: {color};")

    def _render_status(self) -> None:
        state = self.engine.state
        metrics = self.current_metrics

        dd_text = f"{metrics.drawdown_pct:.2f}%" if metrics else "--"
        self.lbl_dd.setText(f"Drawdown actual: {dd_text}")

        if state.active:
            remaining = int((state.until_ts - now_utc()).total_seconds()) if state.until_ts else 0
            self.lbl_reason.setText(f"Motivo: {state.reason}")
            self.lbl_start.setText(f"Inicio pausa: {fmt_dt(state.started_ts)}")
            self.lbl_until.setText(f"Reanudación: {fmt_dt(state.until_ts)}")
            self.lbl_timer.setText(fmt_countdown(remaining))
            self.lbl_pause_title.setText("MAESTRO EN PAUSA")
            self.lbl_pause_title.setStyleSheet("font-size: 18px; font-weight: 800; color:#ffbac3;")
            self.banner.show()
        else:
            self.lbl_reason.setText("Motivo: --")
            self.lbl_start.setText("Inicio pausa: --")
            self.lbl_until.setText("Reanudación: --")
            self.lbl_timer.setText("00:00")
            txt = "MAESTRO OPERATIVO"
            if state.rearme_blocked:
                txt += " (esperando recuperación real)"
            self.lbl_pause_title.setText(txt)
            self.lbl_pause_title.setStyleSheet("font-size: 18px; font-weight: 800; color:#b7f0c0;")

    def _render_plots(self, df: pd.DataFrame) -> None:
        for plot in [self.plot_main, self.plot_min, self.plot_hour, self.plot_day]:
            plot.clear()

        if df.empty:
            return

        # Filtros visuales sencillos (lógica de protección NO depende de esto)
        data = df.copy()
        if self.current_filter == "DEMO":
            data = data.iloc[0:0]

        if data.empty:
            return

        ts = pd.to_datetime(data["ts"], errors="coerce", utc=True)
        eq = pd.to_numeric(data["equity"], errors="coerce")
        valid = ts.notna() & eq.notna()
        ts, eq = ts[valid], eq[valid]
        if len(eq) < 2:
            return

        x = ts.astype("int64") // 10**9
        y = eq.to_numpy(dtype=float)

        def draw(plot: pg.PlotWidget, mask: np.ndarray, color: str):
            if mask.sum() < 2:
                return
            curve = pg.PlotDataItem(x[mask], y[mask], pen=pg.mkPen(color=color, width=2))
            plot.addItem(curve)

        now_ts = int(pd.Timestamp.utcnow().timestamp())
        mask_main = (x >= now_ts - 6 * 3600).to_numpy()
        mask_min = (x >= now_ts - 60 * 60).to_numpy()
        mask_hour = (x >= now_ts - 24 * 3600).to_numpy()
        mask_day = (x >= now_ts - 14 * 24 * 3600).to_numpy()

        draw(self.plot_main, mask_main, "#4fc3f7")
        draw(self.plot_min, mask_min, "#81c784")
        draw(self.plot_hour, mask_hour, "#ffb74d")
        draw(self.plot_day, mask_day, "#ce93d8")


def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#131722"))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#edf2ff"))
    app.setPalette(palette)

    win = MonitorWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
