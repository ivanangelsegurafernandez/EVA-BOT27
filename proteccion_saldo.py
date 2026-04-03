#!/usr/bin/env python3
"""
Protección de saldo REAL DERIV (standalone).

Programa único, limpio y robusto que integra:
- Núcleo lógico de protección (estado único en ProtectionEngine).
- Lectura robusta de fuentes reales con prioridad definida.
- Monitor visual profesional con PySide6 + pyqtgraph.

Dependencias:
  pip install PySide6 pyqtgraph pandas numpy
"""

from __future__ import annotations

import glob
import json
import os
import re
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
    import winsound
except Exception:
    winsound = None


# ------------------------------ Configuración ------------------------------
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

BANNER_HIDE_CONFIRM_REFRESHES = 3
MAX_PLOT_POINTS = 3000

BASE_DIR = Path(__file__).resolve().parent
FILE_SALDO_HISTORY = BASE_DIR / "saldo_real_live_history.jsonl"
FILE_SALDO_LIVE = BASE_DIR / "saldo_real_live.json"
FILE_SALDO_SERIES = BASE_DIR / "saldo_real_series.csv"
DIR_LOG_SALDOS = BASE_DIR / "LOG_SALDOS"
PATTERN_AUX_CSV = str(BASE_DIR / "registro_enriquecido_fulll*.csv")


# ------------------------------ Utilidades ------------------------------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def fmt_money(v: Optional[float]) -> str:
    if v is None or not np.isfinite(v):
        return "--"
    return f"{v:,.2f} USD"


def fmt_dt(dt: Optional[datetime]) -> str:
    if dt is None:
        return "--"
    return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")


def fmt_countdown(seconds_left: int) -> str:
    total = max(0, int(seconds_left))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def beep_on_activate() -> None:
    if winsound is None:
        return
    try:
        winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
    except Exception:
        pass


def beep_on_deactivate() -> None:
    if winsound is None:
        return
    try:
        winsound.MessageBeep(winsound.MB_OK)
    except Exception:
        pass


def safe_float(value: object) -> Optional[float]:
    try:
        if value is None:
            return None
        if isinstance(value, str):
            value = value.strip().replace(",", "")
        x = float(value)
        if np.isfinite(x):
            return x
    except Exception:
        return None
    return None


# ------------------------------ Lógica de detección ------------------------------
def detect_equity_structure_break(equity_series: pd.Series) -> tuple[bool, str]:
    """
    Ruta A: quiebre estructural sobre ventana reciente.

    Reglas:
    - <20 muestras: no activa.
    - ruptura tendencia por STD_FACTOR * std residual.
    - drawdown local <= EQUITY_BREAK_DRAWDOWN.
    - caída rápida (último - hace 4 muestras) <= EQUITY_BREAK_FAST_DROP.
    """
    clean = pd.to_numeric(equity_series, errors="coerce").dropna()
    if len(clean) < 20:
        return False, ""

    window = clean.tail(min(STRUCT_WINDOW, len(clean))).reset_index(drop=True)
    y = window.to_numpy(dtype=float)
    x = np.arange(len(y), dtype=float)

    if len(y) < 20:
        return False, ""

    slope, intercept = np.polyfit(x, y, 1)
    trend = slope * x + intercept
    residual = y - trend
    std = float(np.std(residual)) if len(residual) > 1 else 0.0

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
    """Ruta B: EMA alerta < EMA calma y drawdown en zona de protección."""
    if not all(np.isfinite(v) for v in [ema_alerta, ema_calma, drawdown_pct]):
        return False
    return ema_alerta < ema_calma and drawdown_pct <= DD_PROTECTION_THRESHOLD_PCT


@dataclass
class Metrics:
    ts_series: pd.Series
    equity_series: pd.Series
    equity_actual: float
    ema_alerta: float
    ema_calma: float
    peak_equity: float
    drawdown_pct: float


@dataclass
class ProtectionState:
    active: bool = False
    reason: str = ""
    pause_started_ts: Optional[datetime] = None
    pause_until_ts: Optional[datetime] = None
    rearme_blocked: bool = False
    hide_confirm_counter: int = 0
    last_status_bucket: int = -1


class ProtectionEngine:
    """Única fuente de verdad del estado de protección."""

    def __init__(self) -> None:
        self.state = ProtectionState()

    def evaluate(self, metrics: Optional[Metrics], now: datetime) -> ProtectionState:
        if metrics is None:
            self._handle_no_metrics(now)
            return self.state

        structure_trigger, structure_reason = detect_equity_structure_break(metrics.equity_series)
        ema_drawdown_trigger = should_pause_by_ema_drawdown(
            metrics.ema_alerta,
            metrics.ema_calma,
            metrics.drawdown_pct,
        )
        raw_trigger = structure_trigger or ema_drawdown_trigger
        reason = structure_reason if structure_trigger else "ema_drawdown"

        if not self.state.active:
            can_rearm = (not self.state.rearme_blocked) or self._is_recovery_confirmed(metrics)
            if can_rearm and raw_trigger:
                self._activate_pause(now, reason, metrics.drawdown_pct)
            elif self.state.rearme_blocked and self._is_recovery_confirmed(metrics):
                self.state.rearme_blocked = False
        else:
            self._log_active(now)

        # Mantener pausa viva hasta expiración real; no se apaga por lecturas transitorias.
        if self.state.active and self.state.pause_until_ts and now >= self.state.pause_until_ts:
            self._deactivate_pause("expirada")

        return self.state

    def force_reset_internal(self) -> None:
        self._deactivate_pause("reset_manual")
        self.state.rearme_blocked = False

    def _activate_pause(self, now: datetime, reason: str, drawdown_pct: float) -> None:
        self.state.active = True
        self.state.reason = reason
        self.state.pause_started_ts = now
        self.state.pause_until_ts = now + timedelta(minutes=PAUSE_MINUTES)
        self.state.hide_confirm_counter = 0
        self.state.last_status_bucket = -1
        beep_on_activate()
        print(f"PROTECCION_SALDO: ACTIVADA | reason={reason} | dd={drawdown_pct:.2f}% | pausa=30m")

    def _deactivate_pause(self, cause: str) -> None:
        was_active = self.state.active
        self.state.active = False
        self.state.reason = ""
        self.state.pause_started_ts = None
        self.state.pause_until_ts = None
        self.state.rearme_blocked = True
        self.state.hide_confirm_counter = 0
        self.state.last_status_bucket = -1
        if was_active:
            beep_on_deactivate()
            print(f"PROTECCION_SALDO: FINALIZADA | sistema reanudado | causa={cause}")

    def _log_active(self, now: datetime) -> None:
        if not self.state.pause_until_ts:
            return
        remaining = int((self.state.pause_until_ts - now).total_seconds())
        bucket = remaining // 10
        if remaining > 0 and bucket != self.state.last_status_bucket:
            self.state.last_status_bucket = bucket
            print(f"PROTECCION_SALDO: ACTIVA | restante={fmt_countdown(remaining)}")

    def _is_recovery_confirmed(self, metrics: Metrics) -> bool:
        dd_recovered = metrics.drawdown_pct > (DD_PROTECTION_THRESHOLD_PCT + DD_RECOVERY_MARGIN_PCT)
        ema_recovered = metrics.ema_alerta >= metrics.ema_calma
        return dd_recovered or ema_recovered

    def _handle_no_metrics(self, now: datetime) -> None:
        if not self.state.active:
            return
        if self.state.pause_until_ts and now >= self.state.pause_until_ts:
            self._deactivate_pause("sin_metricas")
        else:
            self._log_active(now)


# ------------------------------ Lectura de datos ------------------------------
class DataLoader:
    """
    Lector robusto de fuentes con prioridad solicitada:
    1) saldo_real_live_history.jsonl
    2) saldo_real_live.json
    3) saldo_real_series.csv
    4) LOG_SALDOS/*.log|*.txt
    5) registro_enriquecido_fulll*.csv
    """

    def load_dataframe(self) -> pd.DataFrame:
        errors: list[str] = []

        for source_name, loader in [
            ("saldo_real_live_history.jsonl", self._load_history_jsonl),
            ("saldo_real_live.json", self._load_live_json),
            ("saldo_real_series.csv", self._load_series_csv),
            ("LOG_SALDOS", self._load_log_saldos),
            ("registro_enriquecido_fulll*.csv", self._load_aux_csv),
        ]:
            try:
                df = loader()
                if not df.empty:
                    return df
            except Exception as ex:
                errors.append(f"{source_name}: {ex}")

        if errors:
            print("PROTECCION_SALDO: warning lectura fuentes -> " + " | ".join(errors))
        return pd.DataFrame(columns=["ts", "equity", "cuenta", "source"])

    def _load_history_jsonl(self) -> pd.DataFrame:
        if not FILE_SALDO_HISTORY.exists():
            return pd.DataFrame()
        rows = []
        with FILE_SALDO_HISTORY.open("r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(row, dict):
                    rows.append(row)
        if not rows:
            return pd.DataFrame()
        return self._normalize_df(pd.DataFrame(rows), source="saldo_real_live_history.jsonl")

    def _load_live_json(self) -> pd.DataFrame:
        if not FILE_SALDO_LIVE.exists():
            return pd.DataFrame()
        content = FILE_SALDO_LIVE.read_text(encoding="utf-8", errors="ignore").strip()
        if not content:
            return pd.DataFrame()
        obj = json.loads(content)
        if isinstance(obj, dict):
            return self._normalize_df(pd.DataFrame([obj]), source="saldo_real_live.json")
        if isinstance(obj, list):
            return self._normalize_df(pd.DataFrame(obj), source="saldo_real_live.json")
        return pd.DataFrame()

    def _load_series_csv(self) -> pd.DataFrame:
        if not FILE_SALDO_SERIES.exists():
            return pd.DataFrame()
        df = pd.read_csv(FILE_SALDO_SERIES)
        return self._normalize_df(df, source="saldo_real_series.csv")

    def _load_log_saldos(self) -> pd.DataFrame:
        if not DIR_LOG_SALDOS.exists() or not DIR_LOG_SALDOS.is_dir():
            return pd.DataFrame()

        files = sorted(list(DIR_LOG_SALDOS.glob("*.log")) + list(DIR_LOG_SALDOS.glob("*.txt")))
        if not files:
            return pd.DataFrame()

        rows = []
        num_pattern = re.compile(r"[-+]?\d*\.?\d+")
        ts_pattern = re.compile(r"\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}")

        for fp in files[-8:]:
            try:
                lines = fp.read_text(encoding="utf-8", errors="ignore").splitlines()[-800:]
            except Exception:
                continue
            for ln in lines:
                nums = num_pattern.findall(ln)
                if not nums:
                    continue
                eq = safe_float(nums[-1])
                if eq is None:
                    continue
                ts_match = ts_pattern.search(ln)
                ts_val = ts_match.group(0) if ts_match else pd.Timestamp.utcnow().isoformat()
                rows.append({"timestamp": ts_val, "equity": eq, "cuenta": "REAL", "source": fp.name})

        if not rows:
            return pd.DataFrame()
        return self._normalize_df(pd.DataFrame(rows), source="LOG_SALDOS")

    def _load_aux_csv(self) -> pd.DataFrame:
        paths = sorted(glob.glob(PATTERN_AUX_CSV))
        if not paths:
            return pd.DataFrame()
        df = pd.read_csv(paths[-1])
        return self._normalize_df(df, source=os.path.basename(paths[-1]))

    def _normalize_df(self, df: pd.DataFrame, source: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["ts", "equity", "cuenta", "source"])

        work = df.copy()
        colmap = {str(c).strip().lower(): c for c in work.columns}

        ts_col = self._pick_column(colmap, ["ts", "timestamp", "time", "fecha_hora", "datetime", "date"])
        eq_col = self._pick_column(colmap, ["equity", "saldo_real", "saldo", "balance", "equidad"])
        acct_col = self._pick_column(colmap, ["cuenta", "account", "tipo_cuenta", "mode", "tipo"])

        if eq_col is None:
            return pd.DataFrame(columns=["ts", "equity", "cuenta", "source"])

        if ts_col is None:
            work["ts"] = pd.date_range(end=pd.Timestamp.utcnow(), periods=len(work), freq="min")
        else:
            work["ts"] = pd.to_datetime(work[ts_col], errors="coerce", utc=True)

        work["equity"] = pd.to_numeric(work[eq_col], errors="coerce")

        if acct_col is None:
            work["cuenta"] = "REAL"
        else:
            work["cuenta"] = work[acct_col].astype(str).str.upper().str.strip()
            work["cuenta"] = work["cuenta"].replace({"": "REAL", "NAN": "REAL"})

        work["source"] = source
        work = work.dropna(subset=["ts", "equity"]) \
                   .sort_values("ts") \
                   .drop_duplicates(subset=["ts", "cuenta"], keep="last")

        return work[["ts", "equity", "cuenta", "source"]].reset_index(drop=True)

    @staticmethod
    def _pick_column(colmap: dict[str, str], candidates: list[str]) -> Optional[str]:
        for c in candidates:
            if c in colmap:
                return colmap[c]
        return None


# ------------------------------ Cálculo de métricas ------------------------------
def compute_metrics(df: pd.DataFrame) -> Optional[Metrics]:
    if df is None or df.empty:
        return None

    # Requisito operativo: usar equity si existe; fallback saldo_real normalizado a equity en DataLoader.
    eq = pd.to_numeric(df["equity"], errors="coerce").dropna()
    if eq.empty:
        return None

    ts = pd.to_datetime(df.loc[eq.index, "ts"], errors="coerce", utc=True).ffill()

    ema_alerta = float(eq.ewm(span=EMA_ALERTA_SPAN, adjust=False).mean().iloc[-1])
    ema_calma = float(eq.ewm(span=EMA_CALMA_SPAN, adjust=False).mean().iloc[-1])

    peak_equity = float(eq.cummax().iloc[-1])
    equity_actual = float(eq.iloc[-1])
    drawdown_pct = ((equity_actual - peak_equity) / peak_equity) * 100.0 if peak_equity > 0 else 0.0

    return Metrics(
        ts_series=ts,
        equity_series=eq,
        equity_actual=equity_actual,
        ema_alerta=ema_alerta,
        ema_calma=ema_calma,
        peak_equity=peak_equity,
        drawdown_pct=drawdown_pct,
    )


# ------------------------------ UI ------------------------------
class MoneyAxisItem(pg.AxisItem):
    def tickStrings(self, values, scale, spacing):  # type: ignore[override]
        out = []
        for v in values:
            try:
                out.append(f"{v:,.0f}")
            except Exception:
                out.append("")
        return out


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_TITLE)
        self.resize(1520, 930)

        self.loader = DataLoader()
        self.engine = ProtectionEngine()

        self.current_df = pd.DataFrame(columns=["ts", "equity", "cuenta", "source"])
        self.current_metrics: Optional[Metrics] = None

        self.filter_mode = "REAL"  # REAL / DEMO / ALL
        self.visual_pause = False

        self._build_ui()
        self._build_timer()
        self.refresh_once()

    def _build_ui(self) -> None:
        pg.setConfigOptions(antialias=True, background="#0f1420", foreground="#dfe9ff")

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        root = QtWidgets.QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(8)

        self.lbl_title = QtWidgets.QLabel("SALDO REAL DERIV ACTUAL")
        self.lbl_title.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_title.setStyleSheet("font-size:34px;font-weight:900;color:#f5f7ff;")

        self.lbl_equity = QtWidgets.QLabel("--")
        self.lbl_equity.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_equity.setStyleSheet("font-size:56px;font-weight:900;color:#80f5a4;")

        self.lbl_banner = QtWidgets.QLabel("PROTECCIÓN ACTIVADA")
        self.lbl_banner.setAlignment(QtCore.Qt.AlignCenter)
        self.lbl_banner.setStyleSheet(
            "font-size:26px;font-weight:900;color:#ffffff;"
            "background:#b3002d;border:2px solid #ff6b82;border-radius:6px;padding:6px;"
        )
        self.lbl_banner.hide()

        root.addWidget(self.lbl_title)
        root.addWidget(self.lbl_equity)
        root.addWidget(self.lbl_banner)

        # Bloque de estado de protección
        detail = QtWidgets.QFrame()
        detail.setStyleSheet("background:#1a2333;border:1px solid #3b4b66;border-radius:7px;")
        dlay = QtWidgets.QGridLayout(detail)
        dlay.setContentsMargins(10, 10, 10, 10)
        dlay.setHorizontalSpacing(24)

        self.lbl_status_head = QtWidgets.QLabel("MAESTRO EN PAUSA")
        self.lbl_status_head.setStyleSheet("font-size:18px;font-weight:800;color:#ffbec9;")

        self.lbl_reason = QtWidgets.QLabel("Motivo: --")
        self.lbl_drawdown = QtWidgets.QLabel("Drawdown actual: --")
        self.lbl_start = QtWidgets.QLabel("Inicio pausa: --")
        self.lbl_resume = QtWidgets.QLabel("Reanudación: --")

        for lbl in [self.lbl_reason, self.lbl_drawdown, self.lbl_start, self.lbl_resume]:
            lbl.setStyleSheet("font-size:14px;color:#d7e5ff;")

        self.lbl_timer = QtWidgets.QLabel("00:00")
        self.lbl_timer.setAlignment(QtCore.Qt.AlignRight | QtCore.Qt.AlignVCenter)
        self.lbl_timer.setStyleSheet("font-size:40px;font-weight:900;color:#ffe685;")

        dlay.addWidget(self.lbl_status_head, 0, 0)
        dlay.addWidget(self.lbl_reason, 1, 0)
        dlay.addWidget(self.lbl_drawdown, 2, 0)
        dlay.addWidget(self.lbl_start, 0, 1)
        dlay.addWidget(self.lbl_resume, 1, 1)
        dlay.addWidget(self.lbl_timer, 0, 2, 3, 1)

        root.addWidget(detail)

        # Gráficas 2x2
        grid = QtWidgets.QGridLayout()
        self.plot_main = self._make_plot("MAIN")
        self.plot_min = self._make_plot("MINUTOS")
        self.plot_hour = self._make_plot("HORAS")
        self.plot_day = self._make_plot("DÍAS")

        grid.addWidget(self.plot_main, 0, 0)
        grid.addWidget(self.plot_min, 0, 1)
        grid.addWidget(self.plot_hour, 1, 0)
        grid.addWidget(self.plot_day, 1, 1)
        root.addLayout(grid, 1)

        # Botones inferiores
        controls = QtWidgets.QHBoxLayout()
        self.btn_real = QtWidgets.QPushButton("REAL")
        self.btn_demo = QtWidgets.QPushButton("DEMO")
        self.btn_all = QtWidgets.QPushButton("ALL")
        self.btn_pause = QtWidgets.QPushButton("PAUSA")
        self.btn_reset_view = QtWidgets.QPushButton("RESET VISTA")
        self.btn_export = QtWidgets.QPushButton("EXPORTAR CSV")
        self.btn_reset_prot = QtWidgets.QPushButton("RESET PROTECCIÓN")

        for b in [self.btn_real, self.btn_demo, self.btn_all, self.btn_pause, self.btn_reset_view, self.btn_export, self.btn_reset_prot]:
            b.setMinimumHeight(34)
            b.setStyleSheet(
                "QPushButton{font-weight:700;background:#283449;color:#edf3ff;border:1px solid #455a7a;border-radius:6px;padding:5px;}"
                "QPushButton:hover{background:#34435c;}"
            )
            controls.addWidget(b)

        self.btn_real.setToolTip("Filtra visualmente datos REAL.")
        self.btn_demo.setToolTip("Filtra visualmente DEMO (si existe en datos).")
        self.btn_all.setToolTip("Muestra todo en visualización.")
        self.btn_pause.setToolTip("Pausa solo el refresco visual local.")
        self.btn_reset_view.setToolTip("Autoajusta zoom de los paneles.")
        self.btn_export.setToolTip("Exporta a CSV la vista cargada actualmente.")
        self.btn_reset_prot.setToolTip("Resetea de forma segura el estado interno de protección.")

        self.btn_real.clicked.connect(lambda: self._set_filter_mode("REAL"))
        self.btn_demo.clicked.connect(lambda: self._set_filter_mode("DEMO"))
        self.btn_all.clicked.connect(lambda: self._set_filter_mode("ALL"))
        self.btn_pause.clicked.connect(self._toggle_visual_pause)
        self.btn_reset_view.clicked.connect(self._reset_view)
        self.btn_export.clicked.connect(self._export_csv)
        self.btn_reset_prot.clicked.connect(self._reset_protection)

        root.addLayout(controls)
        self._set_filter_mode("REAL")

    def _make_plot(self, title: str) -> pg.PlotWidget:
        axis = pg.graphicsItems.DateAxisItem.DateAxisItem(orientation="bottom")
        plot = pg.PlotWidget(axisItems={"bottom": axis, "left": MoneyAxisItem("left")})
        plot.setTitle(title, color="#e9f1ff", size="12pt")
        plot.showGrid(x=True, y=True, alpha=0.25)
        plot.getAxis("left").setPen(pg.mkPen("#8595b3"))
        plot.getAxis("bottom").setPen(pg.mkPen("#8595b3"))
        plot.setLabel("left", "USD")
        return plot

    def _build_timer(self) -> None:
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(REFRESH_MS)
        self.timer.timeout.connect(self.refresh_once)
        self.timer.start()

    def _set_filter_mode(self, mode: str) -> None:
        self.filter_mode = mode
        for button, val in [(self.btn_real, "REAL"), (self.btn_demo, "DEMO"), (self.btn_all, "ALL")]:
            selected = mode == val
            button.setStyleSheet(
                "QPushButton{font-weight:800;background:%s;color:white;border:1px solid #6f80a0;border-radius:6px;padding:5px;}"
                "QPushButton:hover{background:%s;}" % (
                    "#0b724f" if selected else "#283449",
                    "#148460" if selected else "#34435c",
                )
            )

    def _toggle_visual_pause(self) -> None:
        self.visual_pause = not self.visual_pause
        self.btn_pause.setText("REANUDAR" if self.visual_pause else "PAUSA")

    def _reset_view(self) -> None:
        for p in [self.plot_main, self.plot_min, self.plot_hour, self.plot_day]:
            p.enableAutoRange()

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

    def _reset_protection(self) -> None:
        self.engine.force_reset_internal()
        self._render_status()

    def _apply_visual_filter(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty:
            return df
        if self.filter_mode == "ALL":
            return df
        target = self.filter_mode.upper()
        return df[df["cuenta"].astype(str).str.upper().eq(target)].copy()

    def refresh_once(self) -> None:
        if self.visual_pause:
            return

        df = self.loader.load_dataframe()
        self.current_df = df

        # Protección: preferencia REAL si existe, sino usar carga actual
        real_df = df[df["cuenta"].astype(str).str.upper().eq("REAL")].copy() if not df.empty else df
        prot_df = real_df if not real_df.empty else df

        metrics = compute_metrics(prot_df)
        self.current_metrics = metrics

        state = self.engine.evaluate(metrics, now_utc())

        self._render_equity(metrics)
        self._render_status()
        self._render_banner(state)
        self._render_plots(self._apply_visual_filter(df))

    def _render_equity(self, metrics: Optional[Metrics]) -> None:
        if metrics is None:
            self.lbl_equity.setText("--")
            self.lbl_equity.setStyleSheet("font-size:56px;font-weight:900;color:#d3dbea;")
            return

        self.lbl_equity.setText(fmt_money(metrics.equity_actual))
        color = "#ff6f7f" if metrics.drawdown_pct <= DD_PROTECTION_THRESHOLD_PCT else "#80f5a4"
        self.lbl_equity.setStyleSheet(f"font-size:56px;font-weight:900;color:{color};")

    def _render_status(self) -> None:
        state = self.engine.state
        m = self.current_metrics

        dd_text = f"{m.drawdown_pct:.2f}%" if m else "--"
        self.lbl_drawdown.setText(f"Drawdown actual: {dd_text}")

        if state.active:
            remaining = int((state.pause_until_ts - now_utc()).total_seconds()) if state.pause_until_ts else 0
            self.lbl_status_head.setText("MAESTRO EN PAUSA")
            self.lbl_status_head.setStyleSheet("font-size:18px;font-weight:800;color:#ffbec9;")
            self.lbl_reason.setText(f"Motivo: {state.reason}")
            self.lbl_start.setText(f"Inicio pausa: {fmt_dt(state.pause_started_ts)}")
            self.lbl_resume.setText(f"Reanudación: {fmt_dt(state.pause_until_ts)}")
            self.lbl_timer.setText(fmt_countdown(remaining))
        else:
            txt = "MAESTRO OPERATIVO"
            if state.rearme_blocked:
                txt += " (esperando recuperación real)"
            self.lbl_status_head.setText(txt)
            self.lbl_status_head.setStyleSheet("font-size:18px;font-weight:800;color:#b9f2bf;")
            self.lbl_reason.setText("Motivo: --")
            self.lbl_start.setText("Inicio pausa: --")
            self.lbl_resume.setText("Reanudación: --")
            self.lbl_timer.setText("00:00")

    def _render_banner(self, state: ProtectionState) -> None:
        if state.active:
            state.hide_confirm_counter = 0
            self.lbl_banner.show()
            return

        if self.lbl_banner.isVisible():
            state.hide_confirm_counter += 1
            if state.hide_confirm_counter >= BANNER_HIDE_CONFIRM_REFRESHES:
                self.lbl_banner.hide()

    def _render_plots(self, df: pd.DataFrame) -> None:
        for p in [self.plot_main, self.plot_min, self.plot_hour, self.plot_day]:
            p.clear()

        if df.empty:
            return

        ts = pd.to_datetime(df["ts"], errors="coerce", utc=True)
        eq = pd.to_numeric(df["equity"], errors="coerce")
        valid = ts.notna() & eq.notna()
        if valid.sum() < 2:
            return

        ts = ts[valid]
        eq = eq[valid]
        x = (ts.astype("int64") // 10**9).to_numpy(dtype=float)
        y = eq.to_numpy(dtype=float)

        def sample(xv: np.ndarray, yv: np.ndarray, max_points: int = MAX_PLOT_POINTS) -> tuple[np.ndarray, np.ndarray]:
            n = len(xv)
            if n <= max_points:
                return xv, yv
            idx = np.linspace(0, n - 1, max_points, dtype=int)
            return xv[idx], yv[idx]

        def draw(plot: pg.PlotWidget, mask: np.ndarray, color: str) -> None:
            if int(mask.sum()) < 2:
                return
            xs, ys = sample(x[mask], y[mask])
            plot.addItem(pg.PlotDataItem(xs, ys, pen=pg.mkPen(color=color, width=2)))

        now_sec = int(pd.Timestamp.utcnow().timestamp())
        mask_main = x >= (now_sec - 6 * 3600)
        mask_min = x >= (now_sec - 60 * 60)
        mask_hour = x >= (now_sec - 24 * 3600)
        mask_day = x >= (now_sec - 14 * 24 * 3600)

        draw(self.plot_main, mask_main, "#4ec5ff")
        draw(self.plot_min, mask_min, "#84d889")
        draw(self.plot_hour, mask_hour, "#ffc66d")
        draw(self.plot_day, mask_day, "#d8a8ff")


# ------------------------------ Main ------------------------------
def main() -> int:
    app = QtWidgets.QApplication(sys.argv)
    app.setStyle("Fusion")

    palette = QtGui.QPalette()
    palette.setColor(QtGui.QPalette.Window, QtGui.QColor("#0f1420"))
    palette.setColor(QtGui.QPalette.WindowText, QtGui.QColor("#edf3ff"))
    app.setPalette(palette)

    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
