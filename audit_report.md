# Audit report

## File location search
- Found in repo: 5R6M-1-2-4-8-16.py, dataset_incremental.csv, ia_signals_log.csv, mvrx_debug_log.csv, mvrx_board_audit_log.csv, feature_names_v2.pkl, modelo_xgb_v2.pkl, scaler_v2.pkl.
- Missing after absolute search: runtime_log_ia.txt.

## Dataset
- rows_total: 3528
- cols_total: 14
- ret_1m exists: True
- ret_1m non numeric: 0
- ret_1m breakdown: {}
- ret_1m examples: {}
- duplicate_exact_rows: 409
- constant_columns: []
- almost_constant_columns: []
- extreme_dominance: {}
- high_null_columns: {}
- mixed_columns: []
- recoverable_columns: {}

## Features/model/scaler alignment
- dataset columns: ['racha_actual', 'puntaje_estrategia', 'payout', 'ret_1m', 'ret_3m', 'ret_5m', 'slope_5m', 'rv_20', 'range_norm', 'bb_z', 'body_ratio', 'wick_imbalance', 'micro_trend_persist', 'result_bin']
- feature_names length: 13
- scaler expects feature_names_in_ token: True
- scaler contains all 13 feature names in binary payload: True
- model n_features_in_: 13
- meta model_family: sklearn_logreg_fallback
- meta feature_names length: 13
- feature columns missing in dataset: []
- dataset extra columns vs feature_names: ['result_bin']
- order exact match (without label): True

## Logs evidence
- mvrx_debug no_signal rows: 13632
- mvrx_debug sin_candidatos rows: 1644
- mvrx_debug trigger_no rows (trigger_ok=false): 13911
- mvrx_debug confirm_pending rows: 13911
- mvrx_debug reliable=false rows: 13911
- mvrx_debug tier=NONE rows: 13881
- mvrx_debug g=0 rows: 13632
- mvrx_debug x=0 rows: 13632
- sin_candidatos by bot top5: [('EMPTY', 1644)]
- sin_candidatos by hour top5: [('2026-03-12 20', 686), ('2026-03-12 19', 606), ('2026-03-12 21', 352)]
- sin_candidatos by funnel_state: {'WAIT_SOFT': 1644}
- board mvrx_mode=mem_ready rows: 4591
- board mem_ready with ready>0 rows: 4591
- board mem_ready and x_count_0 rows: 365
- board mem_ready with tier NONE rows: 4561
- board mem_ready by bot top5: [('fulll50', 467), ('fulll46', 467), ('fulll51', 465), ('fulll49', 464), ('fulll53', 464)]
- board mem_ready by hour top5: [('2026-03-13 14', 2391), ('2026-03-13 15', 1539), ('2026-03-13 16', 537), ('2026-03-13 13', 124)]

## Patch impact estimate
- Dataset reparable-format failures before patch: 0.
- Dataset reparable-format failures after patch: 0 (no dataset parse change applied).
- Rows that match new mem_ready+x_count_0 conservative fallback condition in board audit: 365.
