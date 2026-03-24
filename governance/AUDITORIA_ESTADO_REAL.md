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
