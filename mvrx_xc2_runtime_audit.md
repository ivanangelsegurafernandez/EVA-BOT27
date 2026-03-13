# MVRX xc==2 runtime audit

| tick_id | class | bot | board_source_used | mvrx_selected_col_idx | mvrx_selected_col_raw | mvrx_green_ratio | mvrx_prev_green_ratio | mvrx_x_count | x_rows | mvrx_candidate_idx | mvrx_target_idx | mvrx_target_idx_mismatch | mvrx_streak | mvrx_pattern | mvrx_pattern_rank | mvrx_tier | mvrx_reason | mvrx_block_reason | mvrx_real_eligible | embudo_decision | embudo_reason_final | final_block_reason |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | xc2_p2_ambiguous | b0 | csv | 2 | G:6|R:2|N:0 | 0.75 | 0.75 | 2 | [0, 1] | 0 | -1 | False | 0 |  | 9 | NONE | p2_ambiguous | p2_ambiguous | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 2 | xc2_target_mismatch | b0 | csv | 3 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 0 | 1 | True | 1 | GGG | 9 | NONE | target=1!=candidate=0 | target_idx_mismatch | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 3 | xc2_p2_clean | b0 | csv | 5 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 0 | 0 | False | 6 | RRRRR | 9 | P2 | p2_selective |  | True | WAIT_SOFT | embudo_err | embudo_err |
| 4 | xc2_highgr_none | b0 | memory | 3 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 1 | 1 | False | 1 | GGG | 9 | NONE | p2_ambiguous | p2_ambiguous | False | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 5 | xc2_prevgr_preference | b0 | memory | 5 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 0 | 0 | False | 6 | RRRRR | 9 | P2 | p2_selective |  | True | WAIT_SOFT | embudo_err | embudo_err |
