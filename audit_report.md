# Audit report (current pass)

## Files located
- present: 5R6M-1-2-4-8-16.py, dataset_incremental.csv, ia_signals_log.csv, mvrx_debug_log.csv, mvrx_board_audit_log.csv, feature_names_v2.pkl, modelo_xgb_v2.pkl, scaler_v2.pkl
- missing: runtime_log_ia.txt

## Dataset numbers
- rows: 3528
- cols: 14
- exact_duplicates: 409
- ret_1m_non_numeric: 0

## Runtime counts (runtime_log_ia.txt)
- runtime_exists: False
- ret_1m=no numérico: None
- P_oper=0.0: None
- confirm_pending: None
- trigger_no: None
- sin_candidatos: None
- reliable=no: None
- reliable=false: None
- features_ok_bajas: None

## Fallback log counts in available files
- mvrx_debug_log.csv_text_counts: {'ret_1m=no numérico': 0, 'P_oper=0.0': 0, 'confirm_pending': 0, 'trigger_no': 0, 'sin_candidatos': 27264, 'reliable=no': 0, 'reliable=false': 0, 'features_ok_bajas': 0}
- mvrx_board_audit_log.csv_text_counts: {'ret_1m=no numérico': 0, 'P_oper=0.0': 0, 'confirm_pending': 0, 'trigger_no': 0, 'sin_candidatos': 23976, 'reliable=no': 0, 'reliable=false': 0, 'features_ok_bajas': 0}
- ia_signals_log.csv_text_counts: {'ret_1m=no numérico': 0, 'P_oper=0.0': 0, 'confirm_pending': 0, 'trigger_no': 0, 'sin_candidatos': 0, 'reliable=no': 0, 'reliable=false': 0, 'features_ok_bajas': 0}

## mem_ready vs no_signal evidence
- mem_ready_evidence: {'mem_ready_rows': 4591, 'mem_ready_x0': 365, 'mem_ready_tier_none': 4561, 'mem_ready_xeq0': 365}
- no_signal_evidence: {'no_signal': 13632, 'no_signal_tier_none': 13632, 'no_signal_g0': 13632, 'no_signal_x0': 13632}

## Contradiction resolution
- `validar_fila_incremental` runs before writing incremental rows; invalid rows are discarded and logged, so runtime can show many `ret_1m=no numérico` while persisted dataset remains clean.
- `_anexar_incremental_desde_bot_CANON` logs discard reason and returns without appending when validation fails.
- backfill path also validates and discards invalid rows before append.
