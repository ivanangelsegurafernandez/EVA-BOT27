# -*- coding: utf-8 -*-
"""BoardGate-V1: fusión futura entre IA técnica y contexto de tablero."""

from __future__ import annotations


def fuse_technical_with_board(
    prob_ia: float | None,
    board_pred: dict | None,
    ctt_state: dict | None = None,
    fusion_enable: bool = False,
    shadow_mode: bool = True,
) -> dict:
    p_ia = float(prob_ia) if isinstance(prob_ia, (int, float)) else None
    board_pred = board_pred or {}
    p_board = board_pred.get("p_pattern_win", None)
    risk = float(board_pred.get("mine_risk", 0.0) or 0.0)
    regime = str(board_pred.get("regime_tag", "UNKNOWN") or "UNKNOWN")
    model_ready = bool(board_pred.get("model_ready", False))

    if p_ia is None:
        if isinstance(p_board, (int, float)):
            p_base = max(0.0, min(1.0, float(p_board)))
        else:
            p_base = 0.5
    else:
        p_base = max(0.0, min(1.0, float(p_ia)))

    p_mix = p_base
    mode = "shadow"
    block_reason = ""

    if isinstance(p_board, (int, float)) and model_ready:
        p_board = max(0.0, min(1.0, float(p_board)))
        bonus = (p_board - 0.5) * 0.20
        penal = max(0.0, risk - 0.35) * 0.18
        p_mix = max(0.0, min(1.0, p_base + bonus - penal))

    ctt_gate = str((ctt_state or {}).get("gate", "")).upper()
    if ctt_gate == "BLOCK":
        block_reason = "ctt_block"
    elif risk >= 0.85:
        block_reason = "board_mine_risk"

    if not fusion_enable or shadow_mode:
        mode = "shadow_preview"
        return {
            "prob_final": float(p_base),
            "allow_soft": True,
            "allow_hard": True,
            "block_reason": "",
            "fusion_mode": mode,
            "preview_prob_final": float(p_mix),
            "preview_block_reason": block_reason,
            "regime_tag": regime,
        }

    mode = "soft_live"
    allow_soft = (block_reason == "")
    allow_hard = allow_soft and (p_mix >= 0.50)
    return {
        "prob_final": float(p_mix),
        "allow_soft": bool(allow_soft),
        "allow_hard": bool(allow_hard),
        "block_reason": block_reason,
        "fusion_mode": mode,
        "preview_prob_final": float(p_mix),
        "preview_block_reason": block_reason,
        "regime_tag": regime,
    }
