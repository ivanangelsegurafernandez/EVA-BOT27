# MVRX streak/pattern/target runtime audit

| tick_id | class | bot | board_source_used | mvrx_selected_col_idx | mvrx_selected_col_raw | mvrx_green_ratio | mvrx_x_count | mvrx_candidate_idx | mvrx_target_idx | mvrx_target_idx_mismatch | mvrx_streak | mvrx_pattern | mvrx_pattern_rank | mvrx_tier | mvrx_mode | mvrx_priority_class | mvrx_reason | mvrx_block_reason | mvrx_real_eligible | embudo_decision | embudo_reason_final | final_block_reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | x1_high_no_rule | b0 | memory | 2 | G:7|R:1|N:0 | 0.875 | 1 | 0 | 0 | False | 1 | GG | 9 | NONE | NONE | NONE | streak_1_no_pattern | streak_1_no_pattern | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 2 | x1_streak1_no_pattern | b0 | memory | 1 | G:7|R:1|N:0 | 0.875 | 1 | 0 | 0 | False | 1 | G | 9 | NONE | NONE | NONE | streak_1_no_pattern | streak_1_no_pattern | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 3 | x1_p1_strict | b0 | csv | 3 | G:7|R:1|N:0 | 0.875 | 1 | 0 | 0 | False | 3 | GRR | 9 | P1 | STRICT | P1 | p1_core |  | True | WAIT_SOFT | embudo_err | embudo_err |
| 4 | x1_relaxed_A_hit | b0 | csv | 5 | G:7|R:1|N:0 | 0.875 | 1 | 0 | 0 | False | 2 | RGRGR | 1 | P1 | RELAXED | P1 | relaxed_streak2_pattern+pattern |  | True | WAIT_SOFT | embudo_err | embudo_err |
| 5 | x1_relaxed_B_hit | b0 | csv | 3 | G:6|R:2|N:0 | 0.75 | 2 | 0 | 1 | True | 1 | GGG | 9 | NONE | NONE | NONE | target=1!=candidate=0 | target_idx_mismatch | False | WAIT_SOFT | mvrx_block | target_idx_mismatch |
| 6 | x2_p2_ambiguous | b0 | csv | 2 | G:6|R:2|N:0 | 0.75 | 2 | 0 | -1 | False | 0 |  | 9 | NONE | NONE | NONE | p2_ambiguous | p2_ambiguous | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 7 | x2_target_mismatch | b0 | csv | 3 | G:6|R:2|N:0 | 0.75 | 2 | 0 | 1 | True | 1 | GGG | 9 | NONE | NONE | NONE | target=1!=candidate=0 | target_idx_mismatch | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
