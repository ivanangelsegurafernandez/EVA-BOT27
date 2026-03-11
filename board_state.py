# -*- coding: utf-8 -*-
"""BoardGate-V1: reconstrucción de tablero 10xN desde cierres reales."""

from __future__ import annotations

import csv
import os
from collections import deque
from typing import Callable


def _to_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _norm_status(raw: str, normalizer: Callable[[str], str] | None = None) -> str:
    txt = str(raw or "").strip()
    if normalizer is not None:
        try:
            return str(normalizer(txt) or "").strip().upper()
        except Exception:
            pass
    up = txt.upper()
    if up in {"CERRADO", "CERRADA", "CLOSED", "SETTLED"}:
        return "CERRADO"
    if up in {"PRE_TRADE", "PRETRADE", "PENDING", "OPEN", "ABIERTO"}:
        return "PRE_TRADE"
    return up


def _norm_result(raw: str, normalizer: Callable[[str], str] | None = None) -> str:
    txt = str(raw or "").strip()
    if normalizer is not None:
        try:
            txt = str(normalizer(txt) or txt)
        except Exception:
            pass
    up = txt.upper()
    if up in {"GANANCIA", "WIN", "W"}:
        return "GANANCIA"
    if up in {"PÉRDIDA", "PERDIDA", "LOSS", "L"}:
        return "PÉRDIDA"
    return up


def _load_recent_closes(path: str, lookback_cols: int, status_normalizer=None, result_normalizer=None) -> tuple[list[int], dict]:
    out: list[int] = []
    meta = {"rows": 0, "closed_rows": 0, "status_prioritized": 0}
    if not os.path.exists(path):
        return out, meta

    def _iter_rows(enc: str):
        with open(path, "r", encoding=enc, newline="") as f:
            for row in csv.DictReader(f):
                yield row

    rows_iter = None
    for enc in ("utf-8", "latin-1"):
        try:
            rows_iter = _iter_rows(enc)
            first = next(rows_iter, None)
            if first is None:
                return out, meta
            # reconstruir iterador incluyendo primera fila
            def _chain_first(fr, it):
                yield fr
                for r in it:
                    yield r
            rows_iter = _chain_first(first, rows_iter)
            break
        except Exception:
            rows_iter = None
            continue

    if rows_iter is None:
        return out, meta

    # Mantener buffer chico de cierres válidos; evita cargar CSV completo en memoria.
    recent = deque(maxlen=max(8, int(lookback_cols)))
    for row in rows_iter:
        meta["rows"] += 1
        res = _norm_result(row.get("resultado", ""), result_normalizer)
        if res not in {"GANANCIA", "PÉRDIDA"}:
            continue

        ts = _norm_status(row.get("trade_status", ""), status_normalizer)
        if ts == "CERRADO":
            meta["status_prioritized"] += 1
            recent.append(1 if res == "GANANCIA" else -1)
        elif ts in {"", "NONE", "NULL"}:
            # fallback legacy: resultado válido pero status vacío
            recent.append(1 if res == "GANANCIA" else -1)
        else:
            continue
        meta["closed_rows"] += 1

    if recent:
        out = list(recent)[-int(lookback_cols):]
    return out, meta


def build_board_state(
    bot_names: list[str],
    candidate_bot: str | None,
    lookback_cols: int = 16,
    csv_dir: str = ".",
    status_normalizer: Callable[[str], str] | None = None,
    result_normalizer: Callable[[str], str] | None = None,
) -> dict:
    lookback_cols = max(4, int(lookback_cols))
    matrix: list[list[int]] = []
    row_meta: dict[str, dict] = {}

    for bot in list(bot_names or []):
        path = os.path.join(csv_dir, f"registro_enriquecido_{bot}.csv")
        closes, meta = _load_recent_closes(path, lookback_cols, status_normalizer, result_normalizer)
        row = [0] * lookback_cols
        if closes:
            row[-len(closes):] = closes[-lookback_cols:]
        matrix.append(row)
        row_meta[str(bot)] = {
            "path": path,
            "available": len(closes),
            "holes": max(0, lookback_cols - len(closes)),
            "rows": meta.get("rows", 0),
            "closed_rows": meta.get("closed_rows", 0),
            "status_prioritized": meta.get("status_prioritized", 0),
        }

    candidate_idx = -1
    if candidate_bot in bot_names:
        candidate_idx = int(bot_names.index(candidate_bot))

    ready_bots = sum(1 for b in bot_names if row_meta.get(b, {}).get("available", 0) > 0)
    holes = sum(int(row_meta.get(b, {}).get("holes", 0)) for b in bot_names)
    total_cells = len(bot_names) * lookback_cols
    completeness = 1.0 - (holes / float(max(1, total_cells)))

    return {
        "board_matrix": matrix,
        "board_meta": {
            "lookback_cols": lookback_cols,
            "ready_bots": int(ready_bots),
            "total_bots": len(bot_names),
            "holes": int(holes),
            "total_cells": int(total_cells),
            "completeness": float(max(0.0, min(1.0, completeness))),
            "row_meta": row_meta,
            "candidate_bot": candidate_bot,
            "candidate_idx": int(candidate_idx),
        },
        "candidate_row": matrix[candidate_idx] if candidate_idx >= 0 and candidate_idx < len(matrix) else [0] * lookback_cols,
    }
