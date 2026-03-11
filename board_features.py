# -*- coding: utf-8 -*-
"""BoardGate-V1: extracción de features contextuales del tablero."""

from __future__ import annotations


def _flatten(mat):
    return [v for row in (mat or []) for v in (row or [])]


def _ratio(vals, target):
    den = len(vals)
    if den <= 0:
        return 0.0
    return sum(1 for x in vals if x == target) / float(den)


def _coherence_ratio(seq):
    if not seq or len(seq) < 2:
        return 0.0
    same = 0
    pairs = 0
    for i in range(1, len(seq)):
        a, b = seq[i - 1], seq[i]
        if a == 0 or b == 0:
            continue
        pairs += 1
        if a == b:
            same += 1
    return float(same / max(1, pairs))


def _zebra_score(seq):
    if not seq or len(seq) < 2:
        return 0.0
    changes = 0
    denom = 0
    for i in range(1, len(seq)):
        a, b = seq[i - 1], seq[i]
        if a == 0 or b == 0:
            continue
        denom += 1
        if a != b:
            changes += 1
    return float(changes / max(1, denom))


def _max_run(seq, target):
    best = 0
    cur = 0
    for x in seq:
        if x == target:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def _current_run(seq):
    seq_nz = [x for x in seq if x != 0]
    if not seq_nz:
        return 0
    last = seq_nz[-1]
    run = 0
    for x in reversed(seq_nz):
        if x == last:
            run += 1
        else:
            break
    return run if last > 0 else -run


def _age_last(seq, target):
    for i, x in enumerate(reversed(seq)):
        if x == target:
            return i
    return len(seq)


def extract_board_features(board_matrix, candidate_row, right_edge_cols=4, right_edge_cols_wide=6):
    mat = [list(r or []) for r in (board_matrix or [])]
    if not mat:
        return {"board_valid": 0.0}

    cols = max(len(r) for r in mat)
    for row in mat:
        if len(row) < cols:
            row[:0] = [0] * (cols - len(row))

    flat = _flatten(mat)
    nz = [x for x in flat if x != 0]
    edge_n = max(1, min(int(right_edge_cols), cols))
    edge_w = max(edge_n, min(int(right_edge_cols_wide), cols))
    edge = _flatten([r[-edge_n:] for r in mat])
    edge_wide = _flatten([r[-edge_w:] for r in mat])

    cand = list(candidate_row or [0] * cols)
    if len(cand) < cols:
        cand[:0] = [0] * (cols - len(cand))

    # coherencias
    vertical_vals = []
    diag_vals = []
    for c in range(cols):
        col = [mat[r][c] for r in range(len(mat))]
        vertical_vals.append(_coherence_ratio(col))
        if c > 0:
            diag_a, diag_b = [], []
            lim = min(len(mat), cols - c)
            for r in range(lim):
                diag_a.append(mat[r][c + r])
            lim2 = min(len(mat), c + 1)
            for r in range(lim2):
                diag_b.append(mat[r][c - r])
            diag_vals.append(_coherence_ratio(diag_a))
            diag_vals.append(_coherence_ratio(diag_b))

    row_coh = [_coherence_ratio(r) for r in mat]

    # sincronía candidato vs resto (signo columna)
    sync_hits = 0
    sync_den = 0
    for c in range(cols):
        v = cand[c]
        if v == 0:
            continue
        others = [mat[r][c] for r in range(len(mat)) if mat[r] is not cand and mat[r][c] != 0]
        if not others:
            continue
        maj = 1 if sum(1 for x in others if x > 0) >= sum(1 for x in others if x < 0) else -1
        sync_den += 1
        if v == maj:
            sync_hits += 1

    zebra = _zebra_score(nz)
    red_comp = _max_run(nz, -1) / float(max(1, len(nz)))
    green_comp = _max_run(nz, 1) / float(max(1, len(nz)))

    feats = {
        "board_valid": 1.0,
        "board_ratio_green": _ratio(nz, 1),
        "board_ratio_red": _ratio(nz, -1),
        "board_right4_green": _ratio([x for x in edge if x != 0], 1),
        "board_right4_red": _ratio([x for x in edge if x != 0], -1),
        "board_right6_green": _ratio([x for x in edge_wide if x != 0], 1),
        "board_right6_red": _ratio([x for x in edge_wide if x != 0], -1),
        "board_zebra_score": zebra,
        "board_red_compaction": red_comp,
        "board_green_compaction": green_comp,
        "board_vertical_coherence": sum(vertical_vals) / max(1, len(vertical_vals)),
        "board_horizontal_coherence": sum(row_coh) / max(1, len(row_coh)),
        "board_diagonal_coherence": sum(diag_vals) / max(1, len(diag_vals)),
        "candidate_current_streak": float(_current_run(cand)),
        "candidate_age_last_green": float(_age_last(cand, 1)),
        "candidate_age_last_red": float(_age_last(cand, -1)),
        "candidate_recent_changes": float(_zebra_score([x for x in cand if x != 0])),
        "candidate_sync_ratio": float(sync_hits / max(1, sync_den)),
        "candidate_desync_ratio": float(1.0 - (sync_hits / max(1, sync_den))),
    }

    # Riesgos interpretable V1
    feats["mine_risk_red_wall"] = max(0.0, min(1.0, feats["board_right6_red"] * 0.7 + red_comp * 0.6))
    feats["mine_risk_zebra"] = max(0.0, min(1.0, zebra))
    feats["mine_risk_late_green"] = max(0.0, min(1.0, feats["candidate_age_last_green"] / max(1.0, float(cols))))
    false_rebound = feats["board_right4_green"] * feats["board_right6_red"]
    feats["mine_risk_false_rebound"] = max(0.0, min(1.0, false_rebound + feats["candidate_desync_ratio"] * 0.2))

    return feats
