# AUDITORÍA DE ESTADO REAL — AETHELGARD

**Fecha**: 23 de Marzo, 2026
**Versión del Sistema**: v4.5.0-beta
**Metodología**: Análisis forense cruzado Código ↔ Gobernanza ↔ BD (verificación de imports, líneas exactas, llamadas reales)
**Alcance**: `core_brain/`, `data_vault/`, `connectors/`, `governance/`, `docs/`
**Informe anterior**: Eliminado (14-Mar-2026 — hallazgos resueltos en Sprints N1–5)

> **Protocolo de ejecución**: Ver [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md)

---

## RESUMEN EJECUTIVO

| Severidad | Cantidad | Descripción |
|-----------|----------|-------------|
| 🔴 CRÍTICO | 1 | Componente declarado DONE que es un STUB sin efecto real |
| 🟡 MEDIO   | 2 | Inconsistencias de gobernanza (estados de épicas, texto de planificación obsoleto) |
| ✅ RESUELTO | Todos los críticos anteriores | CRÍTICO-1/2/3 y ALTO-1/2/4/6 del informe Mar-14 fueron resueltos |

---

## 🔴 HALLAZGO CRÍTICO

### CRÍTICO-1: `evaluate_all_instances()` — STUB declarado como DONE

**Archivo**: `core_brain/shadow_manager.py:365-391`
**Impacto**: El sistema SHADOW nunca evalúa instancias, nunca escribe en `sys_shadow_performance_history`, y nunca toma decisiones de promoción/eliminación. La orquestación darwiniana es inoperante.

**Evidencia en código** (líneas exactas):
```python
# shadow_manager.py:377-390
result = {
    "promotions": [],
    "kills": [],
    "quarantines": [],
    "monitors": [],
}
# TODO: When storage.list_shadow_instances() is implemented:
# instances = self.storage.list_shadow_instances(status=ShadowStatus.INCUBATING)
# for instance in instances:
#     health = self.evaluate_single_instance(instance)
#     ...append to result
return result
```

**Efecto en cadena**:
- `main_orchestrator.py:1293` llama `self.shadow_manager.evaluate_all_instances()` → recibe dict vacío → no hace nada
- `data_vault/shadow_db.py:188` define `record_performance_snapshot()` con INSERT real → **nunca es invocado** (grep exhaustivo: cero llamadas en todo el codebase)
- `sys_shadow_performance_history`: DDL e índices creados en `schema.py`, CRUD completo en `shadow_db.py`. **Tabla vacía en producción**

**Estado documental vs código**:
- BACKLOG marca `[DONE]` al SHADOW Evolution v2.1 como parte de E3 archivada
- El código contradice ese estado: el componente central es un TODO comentado

**Corrección requerida**: Implementar el cuerpo real de `evaluate_all_instances()`. Ver **E8** en ROADMAP y **HU 6.4** en BACKLOG.

---

## 🟡 HALLAZGOS MEDIOS

### MEDIO-1: E6 en ROADMAP marcada `ACTIVA` tras Sprint 4 completado

**Archivo**: `governance/ROADMAP.md`
**Evidencia**: Sprint 4 (21-Mar-2026) cerrado con `[DONE]` 7/7 tests. E6 debía archivarse en SYSTEM_LEDGER y eliminarse del ROADMAP per las reglas del documento.
**Estado**: Corregido en esta sesión — E6 archivada en SYSTEM_LEDGER, eliminada del ROADMAP.

### MEDIO-2: HU 4.7 — Texto de planificación obsoleto en BACKLOG

**Archivo**: `governance/BACKLOG.md` (sección HU 4.7, "Tareas Pendientes")
**Evidencia de implementación confirmada**:
- `core_brain/economic_integration.py:295`: `async def get_trading_status(...)` implementado
- `core_brain/main_orchestrator.py:1788, 1825, 1955`: llamado activo en ciclo de trading
- SYSTEM_LEDGER (Sprint N2): 20/20 tests PASSED
- El estado `[DONE]` en BACKLOG es correcto

**Causa**: Bloque "Tareas Pendientes" era texto de planificación pre-implementación, no fue limpiado al cerrar la HU.
**Estado**: Corregido en esta sesión — texto obsoleto eliminado del BACKLOG.

---

## 🟠 HALLAZGO NUEVO: Pipeline de Señales SHADOW y Filtros de Estrategia

### HALLAZGO-2026-03-27-1: Solo GBPUSD genera señales en LIQ_SWEEP_0001

**Archivos implicados:**
- `core_brain/strategies/liq_sweep_0001.py` (líneas 48-68, 104-112, 148-180)
- `core_brain/signal_factory.py` (líneas 170-241)
- `core_brain/sensors/session_liquidity_sensor.py` (líneas 1-327)
- `core_brain/sensors/liquidity_sweep_detector.py` (líneas 1-327)
- `logs/main.log` (rango 149390-157327)

**Condiciones y lógica detectada:**
- El filtro `AFFINITY_SCORES` (línea 48) y `min_affinity=0.75` (línea 104) restringen la generación de señales a EURUSD (0.92) y GBPUSD (0.88). El resto de símbolos no pasan el filtro y nunca llegan a la lógica de señal.
- Solo GBPUSD genera señales porque, en los datos recientes, cumple la lógica de breakout falso + reversal (PIN BAR o ENGULFING) definida en `analyze()` (líneas 148-180).
- EURUSD, aunque pasa affinity, no cumple la lógica de señal en los datos actuales (no hay breakout falso + reversal en la sesión Londres).
- El pipeline de datos, sensores y lógica de reversión funcionan correctamente para GBPUSD. El resto de activos no cumplen condiciones o son filtrados por affinity.

**Evidencia en logs:**
- `[DEBUG][LIQ_SWEEP_0001] ... analyze() no generó señal (raw_signal=None)` para la mayoría de símbolos.
- `SEÑAL GENERADA ... GBPUSD ... Origin: SHADOW` en múltiples ciclos (logs 149390-157327).

**Estado documental vs código:**
- El sistema SÍ genera señales en SHADOW, pero solo para activos que cumplen affinity y lógica de reversión.
- No hay errores de gating, deduplicación ni configuración. El pipeline es funcional pero altamente restrictivo.

**Acción sugerida:**
- Revisar si los filtros de affinity y lógica de reversión son demasiado estrictos para el universo de activos objetivo.
- Considerar logging más granular para EURUSD y otros activos que pasan affinity pero no cumplen lógica de señal.

---

## 🟠 HALLAZGO NUEVO: Pipeline de Entrega de Señales SHADOW

### HALLAZGO-2026-03-27-2: Auditoría de entrega y persistencia de señales SHADOW

**Archivos implicados:**
- `core_brain/signal_factory.py` (líneas 211-305)
- `logs/main.log` (rango 149390-157327)

**Condiciones y lógica detectada:**
- Las señales generadas por GBPUSD en modo SHADOW son persistidas correctamente (`save_signal`), asignando `origin_mode=SHADOW` y generando un `signal_id` único.
- No se detectan bloqueos por deduplicación ni errores en la entrega a módulos posteriores (persistencia, tagging de volatilidad, enriquecimiento FVG).
- El pipeline de notificación y ejecución no muestra errores en los logs para señales SHADOW generadas.

**Evidencia en logs:**
- `SEÑAL GENERADA ... GBPUSD ... Origin: SHADOW` seguido de logs de tagging y enriquecimiento.
- Ausencia de errores o warnings en la entrega de señales SHADOW.

**Estado documental vs código:**
- El pipeline de entrega y persistencia de señales SHADOW es funcional para los activos que cumplen condiciones.
- No se detectan cuellos de botella ni pérdidas de señal en la etapa de persistencia o notificación.

**Acción sugerida:**
- Mantener auditoría continua sobre la entrega de señales, especialmente si se amplía el universo de activos o se relajan los filtros de affinity/lógica.
- Documentar explícitamente en la gobernanza los criterios de filtrado y condiciones de generación de señales para trazabilidad futura.

---

## 🟠 HALLAZGO NUEVO: Entrega a Ejecución y Notificación (SHADOW)

### HALLAZGO-2026-03-27-3: Pipeline de entrega a Executor y NotificationService

**Archivos implicados:**
- `core_brain/executor.py` (líneas 181-214, 421-493)
- `core_brain/notification_service.py`, `core_brain/notificator.py`
- `logs/main.log` (inicio, bloques de inicialización y ciclo SHADOW)

**Condiciones y lógica detectada:**
- El Executor recibe señales SHADOW, fuerza cuenta DEMO y valida los 4 Pilares antes de autorizar cualquier acción (líneas 181-214).
- No hay errores ni bloqueos en la ejecución de señales SHADOW (GBPUSD) en los logs.
- NotificationService y Notificator están inicializados, pero todos los canales (telegram, whatsapp, email) aparecen como Enabled: False.
- No se detectan logs de envío real de notificaciones para señales SHADOW, lo que indica que la notificación está deshabilitada por configuración.
- No hay pérdidas de señal ni cuellos de botella en la persistencia o entrega a módulos posteriores.

**Evidencia en logs:**
- Inicialización de NotificationService y Notificator con canales deshabilitados.
- Ausencia de logs de send_alert, create_notification o errores de notificación.
- Persistencia exitosa de señales SHADOW (ver hallazgos previos).

**Estado documental vs código:**
- El pipeline de entrega a ejecución y notificación es funcional, pero la notificación está deshabilitada por configuración.
- El sistema está listo para notificar y ejecutar en modo SHADOW si se habilitan los canales correspondientes.

**Acción sugerida:**
- Habilitar al menos un canal de notificación (telegram, email) en entorno de pruebas para validar end-to-end.
- Realizar un test de ejecución real en modo SHADOW para confirmar la entrega completa (persistencia → ejecución → notificación).
- Documentar en la gobernanza la configuración actual de notificación y los pasos para habilitarla.

---

## ✅ ESTADO DEL CÓDIGO VIVO (Verificado)

### Módulos integrados en el flujo principal

| Módulo | Archivo | Integración verificada |
|---|---|---|
| EdgeTuner | `core_brain/edge_tuner.py` | `start.py:35` import · `start.py:497` loop horario async · `trade_closure_listener.py:52` feedback post-trade |
| RegimeClassifier | `core_brain/regime.py` | `start.py:51` import · `start.py:334` instancia · `main_orchestrator.py` inyectado |
| StrategyGatekeeper | `core_brain/strategy_gatekeeper.py` | `main_orchestrator.py:266` DI · `main_orchestrator.py:2010-2036` filtro pre-ejecución activo |
| EconomicIntegration | `core_brain/economic_integration.py` | `main_orchestrator.py:748` init · `main_orchestrator.py:1788/1825/1955` veto activo |
| ShadowManager (instancia) | `core_brain/shadow_manager.py` | `main_orchestrator.py:333-335` instanciado ✅ — evaluación interna STUB ❌ |
| ConnectivityOrchestrator | `core_brain/connectivity_orchestrator.py` | `start.py:250` ✅ |
| DataProviderManager | `core_brain/data_provider_manager.py` | `start.py:262` ✅ |
| cTrader WebSocket | `connectors/ctrader_connector.py` | `_fetch_bars_via_websocket()` · `_PT_TRENDBARS_REQ` · protocolo 4-step Spotware ✅ |

### Pipeline de datos SHADOW (estado real)

```
main_orchestrator.py:1293
  └─ shadow_manager.evaluate_all_instances()
       └─ RETORNA DICT VACÍO  ← STUB (línea 377)
            └─ record_performance_snapshot()  ← NUNCA SE LLAMA
                 └─ sys_shadow_performance_history  ← TABLA VACÍA
```

**Infraestructura lista pero desconectada**:
- `PromotionValidator` (3 Pilares): ✅ implementado y testado
- `ShadowStorageManager` CRUD: ✅ completo
- `sys_shadow_*` DDL + índices: ✅ en schema.py
- Puente de orquestación: ❌ falta

---

## ✅ RESPUESTAS A LAS PREGUNTAS DE LA AUDITORÍA

### ¿El sistema "aprende" algo hoy?

**No.** El sistema registra trades y clasifica regímenes, pero el bucle de evolución darwiniana (evaluación SHADOW → persistencia → decisión) no ocurre. El `EdgeTuner` sí aprende de cada trade cerrado (ajuste de weights de régimen, loop horario activo). El SHADOW no.

### ¿`sys_shadow_performance_history` alimenta algún algoritmo de decisión?

**No.** La tabla está vacía. `record_performance_snapshot()` existe pero nunca se invoca.

### ¿El sistema tiene hot-reload de configuración?

**Parcialmente.** `reload_config()` en `module_manager.py:34` existe y lee de BD (SSOT correcto). No se invoca automáticamente — no hay watcher ni trigger. `health.py:32` lista `modules.json` como "critical_file", inconsistente con el SSOT siendo la BD.

### ¿BacktestEngine existe?

**No.** Solo hay menciones en documentación. No hay clase, archivo ni import.

---

## ✅ SINCRONIZACIÓN GOBERNANZA (Acciones de esta sesión)

| Documento | Acción | Resultado |
|---|---|---|
| `governance/ROADMAP.md` | E6 archivada en SYSTEM_LEDGER, eliminada del ROADMAP. E7 archivada. E8 agregada (PENDIENTE) | ✅ |
| `governance/BACKLOG.md` | HU 6.4 agregada. HU 4.7 "Tareas Pendientes" obsoletas eliminadas | ✅ |
| `governance/SPRINT.md` | Sprint 6 agregado (TODO) | ✅ |
| `governance/SYSTEM_LEDGER.md` | E6 y E7 archivadas | ✅ |
| `ROADMAP.md` (raíz) | Eliminado (legacy) | ✅ |
| `docs/AUDITORIA_ESTADO_REAL.md` | Eliminado (obsoleto 14-Mar-2026) | ✅ |
| `docs/TEMP_IDEATION_CANVAS.md` | Eliminado (issues stale, Gatekeeper ya conectado) | ✅ |

---

*Próxima auditoría: ejecutar `/auditoria` según [AUDIT_PROTOCOL.md](AUDIT_PROTOCOL.md)*
