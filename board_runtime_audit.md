# Auditoría runtime del puente board (BoardGate/MVRX)

## Método
- Se ejecutó un harness fiel por extracción AST de funciones reales de `5R6M-1-2-4-8-16.py` para evitar dependencias no instaladas del entorno.
- Se simularon 4 ticks de interés + una validación explícita de fallback `memory` puro.

## Evidencia de ticks

| tick_id | bot | board_source_used | board_source_reason | board_ready_bots | board_rows | board_cols | board_partial | boardgate_ready | boardgate_reason | mvrx_board_source_used | mvrx_board_source_reason | mvrx_board_available | mvrx_green_ratio | mvrx_x_count | mvrx_tier | mvrx_reason | mvrx_block_reason | embudo_decision | embudo_reason_final | final_block_reason |
|---:|---|---|---|---:|---:|---:|---|---|---|---|---|---|---:|---:|---|---|---|---|---|---|
| 1 | fulll45 | csv | csv_ready | 6 | 6 | 6 | false | true | ok | csv | csv_ready | true | 1.00 | 0 | NONE | x_count_0 | x_count_0 | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 2 | fulll45 | hybrid | mem_bridge_low_csv | 4 | 6 | 6 | true | true | ok | hybrid | mem_bridge_low_csv | true | 0.00 | 2 | NONE | green_ratio_low | green_ratio_low | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 3 | fulll45 | hybrid | mem_bridge_low_csv | 4 | 6 | 6 | true | true | ok | hybrid | mem_bridge_low_csv | true | 0.00 | 2 | NONE | green_ratio_low | green_ratio_low | WAIT_SOFT | sin_candidatos | sin_candidatos |
| 4 | fulll45 | none | board_unavailable | 0 | 0 | 0 | true | false | low_data | none |  | false | 0.00 | 0 | NONE | board_unavailable | board_unavailable | WAIT_SOFT | sin_candidatos | sin_candidatos |

## Validación explícita `memory` puro
- Escenario: `board_state.build_board_state -> None` + memoria con 5 bots listos.
- Resultado selector: `source_used=memory`, `source_reason=mem_ready`, `ready_bots=5`.

