#!/usr/bin/env python3
"""Exportador de evidencia técnica para diagnóstico 5R6M.

Lee archivos relevantes, copia evidencia (con redacción para texto/código),
genera reportes y empaqueta el resultado en ZIP.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import locale
import os
import platform
import re
import shutil
import sys
import traceback
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import pandas as pd  # type: ignore
except Exception:
    pd = None

try:
    import joblib  # type: ignore
except Exception:
    joblib = None

IMPORTANT_EXACT = {
    "5R6M-1-2-4-8-16.py",
    "board_state.py",
    "board_features.py",
    "board_model.py",
    "board_fusion.py",
    "dataset_incremental.csv",
    "ia_signals_log.csv",
    "model_meta_v2.json",
    "feature_names_v2.pkl",
    "scaler_v2.pkl",
    "modelo_xgb_v2.pkl",
    "boardgate_model.pkl",
    "boardgate_scaler.pkl",
    "boardgate_features.pkl",
    "boardgate_meta.json",
}

KEY_GROUPS = {
    "principal": ["5R6M-1-2-4-8-16.py"],
    "boardgate_modulos": [
        "board_state.py",
        "board_features.py",
        "board_model.py",
        "board_fusion.py",
    ],
    "data_logs": ["dataset_incremental.csv", "ia_signals_log.csv"],
    "artefactos_modelo": ["model_meta_v2.json", "feature_names_v2.pkl", "scaler_v2.pkl", "modelo_xgb_v2.pkl"],
    "artefactos_boardgate": [
        "boardgate_model.pkl",
        "boardgate_scaler.pkl",
        "boardgate_features.pkl",
        "boardgate_meta.json",
    ],
}

TEXT_EXTENSIONS = {".py", ".txt", ".md", ".log", ".json", ".yaml", ".yml", ".ini", ".cfg", ".env"}

SENSITIVE_ASSIGNMENT_RE = re.compile(
    r'(?P<prefix>\b(?:DERIV_)?(?:TOKEN|API[_-]?KEY|SECRET|PASSWORD|PASS|AUTH)[A-Z0-9_\-]*\b\s*[=:]\s*)'
    r'(?P<value>"[^"]*"|\'[^\']*\'|[^\s#]+)',
    flags=re.IGNORECASE,
)

BEARER_RE = re.compile(r"(?i)(Bearer\s+)([A-Za-z0-9\-._~+/]+=*)")
GENERIC_KEY_RE = re.compile(r"(?i)\b(api[_-]?key|token|secret|password)\b\s*[:=]\s*([\"\']?)([^\"\'\s,;]{8,})\2")


def sha256_file(path: Path) -> Optional[str]:
    try:
        h = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()
    except Exception:
        return None


def is_text_candidate(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def redact_text(content: str) -> str:
    content = SENSITIVE_ASSIGNMENT_RE.sub(lambda m: f"{m.group('prefix')}\"***REDACTED***\"", content)
    content = BEARER_RE.sub(r"\1***REDACTED***", content)

    def _generic_sub(match: re.Match[str]) -> str:
        key = match.group(1)
        quote = match.group(2) or '"'
        return f"{key}={quote}***REDACTED***{quote}"

    return GENERIC_KEY_RE.sub(_generic_sub, content)


def find_candidate_files(root: Path) -> Dict[str, List[Path]]:
    found: Dict[str, List[Path]] = {name: [] for name in IMPORTANT_EXACT}
    found["_pattern"] = []

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        name = p.name
        lower_name = name.lower()
        if name in IMPORTANT_EXACT:
            found[name].append(p)
        if (
            name.startswith("boardgate_")
            or p.suffix.lower() == ".log"
            or (p.suffix.lower() == ".json" and any(k in lower_name for k in ["meta", "calibration", "signals", "report"]))
            or any(k in lower_name for k in ["meta", "signals", "incremental", "features", "scaler", "model"])
        ):
            found["_pattern"].append(p)

    # Unificar y quitar duplicados de patrones ya capturados por exactos
    exact_set = {q.resolve() for k, v in found.items() if k != "_pattern" for q in v}
    uniq_pattern = []
    seen = set()
    for p in found["_pattern"]:
        rp = p.resolve()
        if rp in exact_set or rp in seen:
            continue
        seen.add(rp)
        uniq_pattern.append(p)
    found["_pattern"] = uniq_pattern
    return found


def safe_relative(path: Path, root: Path) -> Path:
    try:
        return path.resolve().relative_to(root.resolve())
    except Exception:
        return Path(path.name)


def copy_with_redaction_if_needed(src: Path, dst: Path) -> Tuple[bool, Optional[str]]:
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if is_text_candidate(src):
            text = src.read_text(encoding="utf-8", errors="replace")
            redacted = redact_text(text)
            dst.write_text(redacted, encoding="utf-8")
            return True, None
        shutil.copy2(src, dst)
        return False, None
    except Exception as exc:
        return False, f"Error copiando {src}: {exc}"


def _load_feature_names(path: Path) -> Tuple[List[str], List[str]]:
    warnings: List[str] = []
    features: List[str] = []
    obj = None
    if joblib is not None:
        try:
            obj = joblib.load(path)
        except Exception as exc:
            warnings.append(f"No se pudo cargar feature_names con joblib: {exc}")
    if obj is None:
        import pickle

        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
        except Exception as exc:
            warnings.append(f"No se pudo cargar feature_names con pickle: {exc}")
    if isinstance(obj, (list, tuple)):
        features = [str(x) for x in obj]
    elif hasattr(obj, "tolist"):
        try:
            features = [str(x) for x in obj.tolist()]
        except Exception:
            pass
    if not features:
        warnings.append("feature_names_v2.pkl existe pero no se pudo interpretar como lista de features")
    return features, warnings


def _detect_target_column(columns: List[str]) -> Optional[str]:
    candidates = ["target", "label", "y", "outcome", "signal", "result", "win"]
    lower_map = {c.lower(): c for c in columns}
    for c in candidates:
        if c in lower_map:
            return lower_map[c]
    return None


def _detect_time_column(columns: List[str]) -> Optional[str]:
    for c in columns:
        cl = c.lower()
        if any(k in cl for k in ["time", "timestamp", "date", "datetime", "fecha"]):
            return c
    return None


def summarize_dataset(dataset_path: Optional[Path], feature_names_path: Optional[Path]) -> Tuple[Dict[str, Any], Dict[str, Any], List[str]]:
    summary: Dict[str, Any] = {"exists": bool(dataset_path), "path": str(dataset_path) if dataset_path else None}
    consistency: Dict[str, Any] = {}
    warnings: List[str] = []

    feature_names: List[str] = []
    if feature_names_path and feature_names_path.exists():
        feature_names, wn = _load_feature_names(feature_names_path)
        warnings.extend(wn)

    if not dataset_path or not dataset_path.exists():
        warnings.append("dataset_incremental.csv no encontrado")
        if feature_names:
            consistency = {
                "feature_names_count": len(feature_names),
                "present_in_dataset": [],
                "missing_in_dataset": feature_names,
                "extra_in_dataset": [],
            }
        return summary, consistency, warnings

    try:
        if pd is not None:
            df = pd.read_csv(dataset_path)
            summary["rows"] = int(df.shape[0])
            summary["columns_count"] = int(df.shape[1])
            summary["columns"] = [str(c) for c in df.columns.tolist()]
            summary["nan_per_column"] = {str(k): int(v) for k, v in df.isna().sum().to_dict().items()}

            target_col = _detect_target_column(summary["columns"])
            summary["detected_target"] = target_col
            if target_col:
                vc = df[target_col].value_counts(dropna=False).to_dict()
                summary["target_distribution"] = {str(k): int(v) for k, v in vc.items()}

            tcol = _detect_time_column(summary["columns"])
            summary["detected_time_column"] = tcol
            if tcol:
                parsed = pd.to_datetime(df[tcol], errors="coerce")
                if parsed.notna().any():
                    summary["time_min"] = str(parsed.min())
                    summary["time_max"] = str(parsed.max())

            if feature_names:
                cols = set(summary["columns"])
                fset = set(feature_names)
                consistency = {
                    "feature_names_count": len(feature_names),
                    "dataset_columns_count": len(cols),
                    "present_in_dataset": sorted(fset & cols),
                    "missing_in_dataset": sorted(fset - cols),
                    "extra_in_dataset": sorted(cols - fset),
                }
        else:
            with dataset_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                cols = reader.fieldnames or []
            summary["rows"] = len(rows)
            summary["columns_count"] = len(cols)
            summary["columns"] = cols
            nan_per_col = {c: 0 for c in cols}
            for r in rows:
                for c in cols:
                    if r.get(c) in (None, "", "NaN", "nan", "null", "NULL"):
                        nan_per_col[c] += 1
            summary["nan_per_column"] = nan_per_col
            if feature_names:
                cset = set(cols)
                fset = set(feature_names)
                consistency = {
                    "feature_names_count": len(feature_names),
                    "dataset_columns_count": len(cset),
                    "present_in_dataset": sorted(fset & cset),
                    "missing_in_dataset": sorted(fset - cset),
                    "extra_in_dataset": sorted(cset - fset),
                }
            warnings.append("pandas no disponible; resumen CSV generado en modo básico")
    except Exception as exc:
        warnings.append(f"Error resumiendo dataset_incremental.csv: {exc}")
        summary["error"] = traceback.format_exc(limit=2)

    return summary, consistency, warnings


def summarize_signals_log(signals_path: Optional[Path]) -> Tuple[Dict[str, Any], List[str]]:
    summary: Dict[str, Any] = {"exists": bool(signals_path), "path": str(signals_path) if signals_path else None}
    warnings: List[str] = []

    if not signals_path or not signals_path.exists():
        warnings.append("ia_signals_log.csv no encontrado")
        return summary, warnings

    try:
        if pd is not None:
            df = pd.read_csv(signals_path)
            summary["rows"] = int(df.shape[0])
            summary["is_empty"] = bool(df.empty)
            summary["columns"] = [str(c) for c in df.columns.tolist()]
            if df.empty:
                warnings.append("ia_signals_log.csv existe pero está vacío")

            tcol = _detect_time_column(summary["columns"])
            summary["detected_time_column"] = tcol
            if tcol and not df.empty:
                parsed = pd.to_datetime(df[tcol], errors="coerce")
                if parsed.notna().any():
                    summary["time_min"] = str(parsed.min())
                    summary["time_max"] = str(parsed.max())

            signal_col = None
            for c in summary["columns"]:
                if any(k in c.lower() for k in ["outcome", "signal", "result", "action"]):
                    signal_col = c
                    break
            summary["detected_signal_column"] = signal_col
            if signal_col and not df.empty:
                vc = df[signal_col].value_counts(dropna=False).to_dict()
                summary["counts_by_signal_or_outcome"] = {str(k): int(v) for k, v in vc.items()}
        else:
            with signals_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                cols = reader.fieldnames or []
            summary["rows"] = len(rows)
            summary["is_empty"] = len(rows) == 0
            summary["columns"] = cols
            if len(rows) == 0:
                warnings.append("ia_signals_log.csv existe pero está vacío")
            warnings.append("pandas no disponible; signals resumen en modo básico")
    except Exception as exc:
        warnings.append(f"Error resumiendo ia_signals_log.csv: {exc}")
        summary["error"] = traceback.format_exc(limit=2)

    return summary, warnings


def summarize_model_meta(meta_path: Optional[Path]) -> Tuple[Dict[str, Any], List[str]]:
    summary: Dict[str, Any] = {"exists": bool(meta_path), "path": str(meta_path) if meta_path else None}
    warnings: List[str] = []

    if not meta_path or not meta_path.exists():
        warnings.append("model_meta_v2.json no encontrado")
        return summary, warnings

    try:
        raw = json.loads(meta_path.read_text(encoding="utf-8", errors="replace"))
        keys_of_interest = [
            "n_samples",
            "pos",
            "neg",
            "auc",
            "reliable",
            "warmup_mode",
            "model_family",
            "thresholds",
        ]
        for k in keys_of_interest:
            if k in raw:
                summary[k] = raw[k]
        summary["all_keys"] = sorted(list(raw.keys()))
        if "auc" in summary:
            try:
                auc = float(summary["auc"])
                if auc < 0.5:
                    warnings.append("AUC en model_meta_v2.json < 0.5")
            except Exception:
                warnings.append("No se pudo interpretar auc como float")
    except Exception as exc:
        warnings.append(f"Error leyendo model_meta_v2.json: {exc}")
        summary["error"] = traceback.format_exc(limit=2)

    return summary, warnings


def summarize_environment(root: Path) -> Dict[str, Any]:
    env = {
        "python_version": sys.version,
        "platform": platform.platform(),
        "cwd": str(root.resolve()),
        "locale": locale.getpreferredencoding(False),
        "packages": {
            "pandas": None,
            "joblib": None,
            "sklearn": None,
        },
    }
    for pkg in ["pandas", "joblib", "sklearn"]:
        try:
            mod = __import__(pkg)
            env["packages"][pkg] = getattr(mod, "__version__", "unknown")
        except Exception:
            env["packages"][pkg] = "not_installed"
    return env


def check_meta_vs_dataset(model_summary: Dict[str, Any], dataset_summary: Dict[str, Any]) -> List[str]:
    warnings: List[str] = []
    try:
        meta_n = model_summary.get("n_samples")
        data_n = dataset_summary.get("rows")
        if meta_n is None or data_n is None:
            return warnings
        meta_n = int(meta_n)
        data_n = int(data_n)
        if meta_n <= 0:
            return warnings
        diff = abs(data_n - meta_n)
        ratio = diff / max(meta_n, 1)
        if ratio > 0.5 and diff > 100:
            warnings.append(
                f"Diferencia grande meta vs dataset: meta n_samples={meta_n} vs dataset rows={data_n}"
            )
    except Exception:
        warnings.append("No se pudo validar consistencia meta vs dataset")
    return warnings


def build_manifest(
    root: Path,
    copied_records: List[Dict[str, Any]],
    missing: List[str],
    warnings: List[str],
    timestamp: str,
) -> Dict[str, Any]:
    return {
        "timestamp": timestamp,
        "inspected_root": str(root.resolve()),
        "found_files": copied_records,
        "missing_expected": missing,
        "warnings": warnings,
    }


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def write_markdown_summary(
    path: Path,
    copied_records: List[Dict[str, Any]],
    missing: List[str],
    dataset_summary: Dict[str, Any],
    signals_summary: Dict[str, Any],
    model_summary: Dict[str, Any],
    feature_consistency: Dict[str, Any],
    warnings: List[str],
) -> None:
    principales = [r for r in copied_records if Path(r["src"]).name in KEY_GROUPS["principal"] + KEY_GROUPS["boardgate_modulos"]]
    lines = [
        "# Resumen de diagnóstico 5R6M",
        "",
        "## Archivos principales encontrados",
    ]
    if principales:
        lines.extend([f"- `{Path(r['src']).name}` ({r['size_bytes']} bytes)" for r in principales])
    else:
        lines.append("- Ninguno")

    lines.extend(["", "## Archivos faltantes", *(f"- `{m}`" for m in missing)] if missing else ["", "## Archivos faltantes", "- Ninguno"])

    lines.extend([
        "",
        "## Resumen del dataset incremental",
        f"- Existe: `{dataset_summary.get('exists', False)}`",
        f"- Filas: `{dataset_summary.get('rows', 'N/A')}`",
        f"- Columnas: `{dataset_summary.get('columns_count', 'N/A')}`",
        f"- Target detectado: `{dataset_summary.get('detected_target', 'N/A')}`",
    ])

    lines.extend([
        "",
        "## Resumen de ia_signals_log",
        f"- Existe: `{signals_summary.get('exists', False)}`",
        f"- Filas: `{signals_summary.get('rows', 'N/A')}`",
        f"- Vacío: `{signals_summary.get('is_empty', 'N/A')}`",
    ])

    lines.extend([
        "",
        "## Resumen de model_meta_v2.json",
        f"- Existe: `{model_summary.get('exists', False)}`",
        f"- n_samples: `{model_summary.get('n_samples', 'N/A')}`",
        f"- auc: `{model_summary.get('auc', 'N/A')}`",
        f"- reliable: `{model_summary.get('reliable', 'N/A')}`",
        f"- model_family: `{model_summary.get('model_family', 'N/A')}`",
    ])

    lines.extend([
        "",
        "## Coincidencia entre feature_names y columnas del dataset",
        f"- features en PKL: `{feature_consistency.get('feature_names_count', 'N/A')}`",
        f"- presentes en dataset: `{len(feature_consistency.get('present_in_dataset', [])) if feature_consistency else 'N/A'}`",
        f"- faltantes en dataset: `{len(feature_consistency.get('missing_in_dataset', [])) if feature_consistency else 'N/A'}`",
        f"- extras en dataset: `{len(feature_consistency.get('extra_in_dataset', [])) if feature_consistency else 'N/A'}`",
    ])

    lines.append("")
    lines.append("## Observaciones de consistencia")
    if feature_consistency.get("missing_in_dataset"):
        lines.append("- Hay features esperadas ausentes en dataset_incremental.csv")
    if signals_summary.get("is_empty"):
        lines.append("- ia_signals_log.csv está vacío")
    if model_summary.get("n_samples") and dataset_summary.get("rows"):
        lines.append(
            f"- Comparado n_samples(meta)={model_summary.get('n_samples')} vs rows(dataset)={dataset_summary.get('rows')}"
        )
    if lines[-1] == "## Observaciones de consistencia":
        lines.append("- Sin observaciones críticas")

    lines.extend(["", "## Warnings importantes"])
    if warnings:
        lines.extend([f"- {w}" for w in warnings])
    else:
        lines.append("- Ninguno")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_zip(export_dir: Path) -> Path:
    zip_path = export_dir.with_suffix(".zip")
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in export_dir.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(export_dir.parent))
    return zip_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Exportador de diagnóstico 5R6M")
    parser.add_argument("--root", default=".", help="Ruta raíz a inspeccionar")
    parser.add_argument("--out", default=".", help="Ruta base de salida")
    parser.add_argument("--no-zip", action="store_true", help="No generar ZIP final")
    parser.add_argument("--verbose", action="store_true", help="Logs detallados")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = Path(args.root).resolve()
    out_base = Path(args.out).resolve()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    export_dir = out_base / f"diagnostico_5R6M_export_{timestamp}"
    files_dir = export_dir / "files"
    reports_dir = export_dir / "reports"

    warnings: List[str] = []
    copied_records: List[Dict[str, Any]] = []

    found = find_candidate_files(root)

    all_selected: List[Path] = []
    for k, vals in found.items():
        if k == "_pattern":
            all_selected.extend(vals)
        else:
            all_selected.extend(vals)

    # dedupe preserving order
    seen = set()
    unique_selected = []
    for p in all_selected:
        rp = p.resolve()
        if rp in seen:
            continue
        seen.add(rp)
        unique_selected.append(p)

    for src in unique_selected:
        rel = safe_relative(src, root)
        dst = files_dir / rel
        redacted, err = copy_with_redaction_if_needed(src, dst)
        if err:
            warnings.append(err)
            continue
        stat = src.stat()
        copied_records.append(
            {
                "src": str(src),
                "dst": str(dst),
                "relative": str(rel),
                "size_bytes": int(stat.st_size),
                "modified_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                "sha256": sha256_file(src) if src.name in IMPORTANT_EXACT else None,
                "redacted_copy": redacted,
            }
        )

    # localizar archivos clave para reportes (preferir exact match más corto)
    def pick(name: str) -> Optional[Path]:
        candidates = found.get(name, [])
        if not candidates:
            return None
        return sorted(candidates, key=lambda p: len(str(safe_relative(p, root))))[0]

    dataset_path = pick("dataset_incremental.csv")
    signals_path = pick("ia_signals_log.csv")
    meta_path = pick("model_meta_v2.json")
    feature_names_path = pick("feature_names_v2.pkl")

    dataset_summary, feature_consistency, w1 = summarize_dataset(dataset_path, feature_names_path)
    signals_summary, w2 = summarize_signals_log(signals_path)
    model_summary, w3 = summarize_model_meta(meta_path)
    env_summary = summarize_environment(root)

    warnings.extend(w1)
    warnings.extend(w2)
    warnings.extend(w3)
    warnings.extend(check_meta_vs_dataset(model_summary, dataset_summary))

    missing_expected: List[str] = []
    for req in IMPORTANT_EXACT:
        if not found.get(req):
            missing_expected.append(req)

    boardgate_missing = [x for x in KEY_GROUPS["boardgate_modulos"] if x in missing_expected]
    if boardgate_missing:
        warnings.append(f"Faltan módulos BoardGate: {', '.join(boardgate_missing)}")

    model_critical = [x for x in ["modelo_xgb_v2.pkl", "scaler_v2.pkl", "feature_names_v2.pkl"] if x in missing_expected]
    if model_critical:
        warnings.append(f"Faltan artefactos críticos de modelo: {', '.join(model_critical)}")

    manifest = build_manifest(root, copied_records, missing_expected, warnings, timestamp)

    write_json(reports_dir / "manifest.json", manifest)
    write_json(reports_dir / "dataset_summary.json", dataset_summary)
    write_json(reports_dir / "signals_summary.json", signals_summary)
    write_json(reports_dir / "model_summary.json", model_summary)
    write_json(reports_dir / "environment_summary.json", env_summary)

    write_markdown_summary(
        reports_dir / "resumen_diagnostico.md",
        copied_records,
        missing_expected,
        dataset_summary,
        signals_summary,
        model_summary,
        feature_consistency,
        warnings,
    )

    zip_path = None
    if not args.no_zip:
        zip_path = make_zip(export_dir)

    print("\n=== Exportación diagnóstico 5R6M ===")
    print(f"Root inspeccionado: {root}")
    print(f"Salida: {export_dir}")
    print(f"Archivos exportados: {len(copied_records)}")
    print(f"Faltantes esperados: {len(missing_expected)}")
    if missing_expected:
        for m in missing_expected:
            print(f"  - {m}")
    print(f"Warnings: {len(warnings)}")
    if args.verbose and warnings:
        for w in warnings:
            print(f"  ! {w}")
    if zip_path:
        print(f"ZIP final: {zip_path}")
    else:
        print("ZIP final: omitido por --no-zip")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
