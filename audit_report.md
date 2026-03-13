# Auditoría final (entorno actual)

## 1) Archivos y rutas usadas
| archivo | ruta usada | existe | observación |
|---|---|---:|---|
| 5R6M-1-2-4-8-16.py | /workspace/EVA-BOT27/5R6M-1-2-4-8-16.py | sí | fuente principal (no existe /mnt/data) |
| runtime_log_ia.txt | /workspace/EVA-BOT27/runtime_log_ia.txt | no | no existe en entorno actual |
| dataset_incremental.csv | /workspace/EVA-BOT27/dataset_incremental.csv | sí | fuente principal |
| ia_signals_log.csv | /workspace/EVA-BOT27/ia_signals_log.csv | sí | fuente principal |
| mvrx_debug_log.csv | /workspace/EVA-BOT27/mvrx_debug_log.csv | sí | fuente principal |
| mvrx_board_audit_log.csv | /workspace/EVA-BOT27/mvrx_board_audit_log.csv | sí | fuente principal |
| feature_names_v2.pkl | /workspace/EVA-BOT27/feature_names_v2.pkl | sí | fuente principal |
| modelo_xgb_v2.pkl | /workspace/EVA-BOT27/modelo_xgb_v2.pkl | sí | fuente principal |
| scaler_v2.pkl | /workspace/EVA-BOT27/scaler_v2.pkl | sí | fuente principal |

- `/mnt/data` no existe en este entorno.
- Búsqueda global de `runtime_log_ia.txt`: sin resultados.

## 2) Dataset real
- rows = 3528
- cols = 14
- duplicados exactos = 409
- `ret_1m` existe = sí
- `ret_1m` no numérico = 0
- ejemplos no numéricos `ret_1m` = []
- otras columnas numéricas problemáticas = {}
- columnas constantes = []
- columnas casi constantes = []
- columnas con nulos = {}
- columnas mezcla string/número = []

## 3) Runtime real
- `runtime_log_ia.txt` no existe en la ruta exigida ni en el filesystem del entorno.
- Conteos solicitados en runtime real: no aplicable por ausencia del archivo.

## 4) Evidencia equivalente en logs disponibles
- `mvrx_board_audit_log.csv`:
  - `mem_ready_rows` = 4591
  - `mem_ready_x_count_0` = 365
  - `mem_ready_tier_NONE` = 4561
- `mvrx_debug_log.csv`:
  - `no_signal_rows` = 13632
  - `no_signal_tier_NONE` = 13632
  - `no_signal_g0` = 13632
  - `no_signal_x0` = 13632
- `sin_candidatos` (texto):
  - `mvrx_debug_log.csv` = 13632
  - `mvrx_board_audit_log.csv` = 11988
- Ventanas horarias con más `no_signal` (top): 2026-03-13 00 (906), 01 (886), 02 (885), 2026-03-12 23 (868), 03 (831).

## 5) Reconciliación de contradicción `ret_1m`
- `validar_fila_incremental` devuelve `False, "{k}=no numérico"` cuando falla coerción.
- `_anexar_incremental_desde_bot_CANON` valida antes de persistir; si falla, descarta la fila y retorna sin escribir.
- El flujo de backfill también valida y descarta antes de append.
- Por diseño, puede existir historial runtime con errores de validación y CSV actual limpio porque las filas inválidas no se persisten.

## 6) Validación del parche MVRX en archivo final
En `mvrx_eval_candidate`, bloque `if xc == 0`:
- condición específica: `board_src == 'memory'` y `board_src_reason == 'mem_ready'` + `gr >= MVRX_GREEN_RATIO_P1` + `active_rows >= BOARD_MATRIX_MIN_READY_BOTS_MEMORY`.
- fallback aplicado con razón explícita: `x_count_0_mem_ready_fallback`.
- salida conservadora exploratoria:
  - `mvrx_tier = 'P3'`
  - `mvrx_real_eligible = False`
  - `mvrx_micro_only = True`
- si no cumple, mantiene bloqueo original `x_count_0`.

## 7) Alineación dataset/modelo/scaler/features
- `feature_names_v2.pkl` = 13 features.
- Header dataset contiene esas 13 + `result_bin`.
- `missing=[]`, `order_match=True`.
- `model_meta_v2.json` reporta `model_family=sklearn_logreg_fallback` y 13 features.

## 8) Decisión binaria final
1. ¿dataset sucio actual causa principal? **NO**.
2. ¿desalineación dataset/modelo/scaler/features causa principal? **NO**.
3. ¿starvation MVRX + embudo operativo causa principal? **SÍ**.
4. ¿parche MVRX actual correcto? **SÍ** (acotado y no-REAL).
5. ¿otro parche inmediato de código necesario? **NO** (con evidencia actual).
6. Lo que falta observar fuera de código: `runtime_log_ia.txt` real del entorno que reportaste para cuantificar exactamente `ret_1m=no numérico`, `P_oper=0.0`, `confirm_pending`, `trigger_no`, `reliable=*`, `features_ok_bajas` en esa corrida histórica.
