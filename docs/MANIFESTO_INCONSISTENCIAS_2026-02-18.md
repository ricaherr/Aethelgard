# Informe de Inconsistencias (Manifesto vs Código)

Fecha: 2026-02-18
Proyecto: Aethelgard

## Resumen
- Estado real de tests: 201 passed, 81 failed, 7 errors (289 total).
- La documentación reporta múltiples estados de 100% validación que no reflejan el estado actual.
- Existen violaciones de SSOT/DI detectadas por `validate_all.py` (Manifesto Enforcer + Pattern Enforcer fallando).

## Hallazgos Críticos
1. Bug en modificación de posiciones MT5
- Archivo: connectors/mt5_connector.py:1306-1319
- Se construye `request` pero se usa `modify_request` (variable inexistente) para log y `order_send`.
- Impacto: potencial fallo al ajustar SL/TP en vivo.

2. API scanner en server desacoplada del orchestrator real
- Archivo: core_brain/server.py:248-250
- Importa `scanner` desde `core_brain.main_orchestrator`, pero no existe un scanner global exportado.
- Resultado: fallback permanente a `scanner = None` en runtime.

3. Constructor wiring desactualizado en `main_orchestrator.main()`
- Archivo: core_brain/main_orchestrator.py:896
- `SignalFactory(storage_manager=storage)` se instancia sin dependencias obligatorias actuales (`strategies`, `confluence_analyzer`, `trifecta_analyzer`).
- Riesgo: entrypoint interno obsoleto/inconsistente.

## Inconsistencias Documentales
1. Claims de validación total vs realidad
- ROADMAP.md:3636-3641 (`SISTEMA VALIDADO 100%`, `validate_all 100% PASS`)
- ROADMAP.md:3942 (`177/177 PASAN`)
- ROADMAP.md:4166 (`159/159 (100%)`)
- AETHELGARD_MANIFESTO.md:5136-5138 (`Suite 134/134 passing`, `100% funcionalidades críticas`)
- Estado actual observado: 201/289 pass, 81 fail, 7 error.

2. SSOT/DI “100% unificada” no cumplida
- AETHELGARD_MANIFESTO.md:1317 indica arquitectura 100% DB-first.
- `validate_all.py` detecta violaciones SSOT y falla en Manifesto Enforcer.
- Ejemplos detectados:
  - core_brain/analysis_service.py:64 (`config/modules.json`)
  - core_brain/main_orchestrator.py:902 (`config/dynamic_params.json`)
  - core_brain/risk_manager.py:123-124 (`config/risk_settings.json`, `config/dynamic_params.json`)

3. Regla Trifecta estricta vs tests legacy
- AETHELGARD_MANIFESTO.md:36-37: “Eliminación del modo degradado”.
- core_brain/strategies/trifecta_logic.py:75-89 rechaza datos incompletos (`valid=False`).
- tests/test_trifecta_logic.py:242,267-268 espera modo degradado válido (`valid=True`, `degraded_mode=True`).
- Conclusión: tests y política actual no están sincronizados.

## Recomendaciones Prioritarias
1. Corregir inmediatamente `modify_position` en MT5Connector.
2. Definir fuente única del scanner para API (`server.py`) y remover import frágil.
3. Unificar firmas de constructores y actualizar tests/entrypoints legacy en bloque.
4. Separar en documentación: “estado histórico” vs “estado vigente” para evitar falsos 100%.
5. Hacer bloqueante en CI la suite completa y publicar pass rate real por fecha.
