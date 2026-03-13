# Auditoría final solicitada (fuente requerida /mnt/data)

## Verificación de fuente
- /mnt/data existe: False
- En esta sesión /mnt/data no existe, por lo que no hay archivos auditables en esa ruta.
- Se auditó la única copia disponible en /workspace/EVA-BOT27 para no inventar resultados.

## Dataset (copia disponible)
- filas: 3528
- columnas: 14
- duplicados exactos: 409
- ret_1m existe: True
- ret_1m no numérico actual: 0
- ejemplos ret_1m no numérico: []
- otras columnas numéricas problemáticas: {}
- columnas constantes: []
- columnas casi constantes: []
- columnas con nulos: {}
- columnas mezcla string/número: []

## Runtime (ruta requerida)
- runtime_log_ia.txt existe en copia disponible: False
- No hay conteos directos del runtime porque el archivo no existe en esta sesión.
- mvrx_debug_log.csv | sin_candidatos=27264 | ret_1m=no numérico=0 | P_oper=0.0=0 | features_ok_bajas=0
- mvrx_board_audit_log.csv | sin_candidatos=23976 | ret_1m=no numérico=0 | P_oper=0.0=0 | features_ok_bajas=0
- ia_signals_log.csv | sin_candidatos=0 | ret_1m=no numérico=0 | P_oper=0.0=0 | features_ok_bajas=0

## Evidencia MVRX/Embudo
- mem_ready evidence: {'mem_ready_rows': 4591, 'mem_ready_tier_NONE': 4561, 'mem_ready_x_count_0': 365}
- no_signal evidence: {'no_signal_rows': 13632, 'no_signal_tier_NONE': 13632, 'no_signal_g0': 13632, 'no_signal_x0': 13632}

## Alineación features/modelo
- feature_names len: 13
- missing en dataset: []
- extras dataset: ['result_bin']
- orden coincide (sin label): True
- model_meta family: sklearn_logreg_fallback
- model_meta feature_names len: 13
