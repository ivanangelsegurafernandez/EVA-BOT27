# MVRX xc==2 patch validation

| case | sel_col | raw | gr | prev_gr | x | x_rows | cand | target | mismatch | streak | pattern | rank | tier | reason | block |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| c1_symmetric_real_ambiguous | 2 | G:6|R:2|N:0 | 0.75 | 0.75 | 2 | [0, 1] | 0 | 0 | False | 2 | GR | 9 | NONE | p2_ambiguous | p2_ambiguous |
| c2_quasi_tie_candidate_tiebreak | 2 | G:6|R:2|N:0 | 0.75 | 0.75 | 2 | [0, 1] | 1 | 1 | False | 2 | GR | 9 | NONE | p2_ambiguous | p2_ambiguous |
| c3_strong_streak56_prevgr | 5 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 0 | 0 | False | 6 | RRRRR | 9 | P2 | p2_selective |  |
| c4_mismatch_avoidable_rescued | 2 | G:6|R:2|N:0 | 0.75 | 0.75 | 2 | [0, 1] | 1 | 1 | False | 2 | GR | 9 | NONE | p2_ambiguous | p2_ambiguous |
| c5_mismatch_real_kept | 5 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 1 | 0 | True | 6 | RRRRR | 9 | NONE | target=0!=candidate=1 | target_idx_mismatch |
| c6_positive_stable | 5 | G:6|R:2|N:0 | 0.75 | 0.875 | 2 | [0, 1] | 0 | 0 | False | 6 | RRRRR | 9 | P2 | p2_selective |  |
