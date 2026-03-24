# PROTOCOLO DE AUDITORÍA DEL SISTEMA — AETHELGARD

> **Cuándo ejecutar**: Cuando el usuario mencione "auditoría del sistema", "auditar el código", "estado real del sistema" o invoque `/auditoria`.
>
> **Alcance**: Solo lectura + análisis. **No realizar cambios en código de producción.**
>
> **Output**: Generar `governance/AUDITORIA_ESTADO_REAL.md` (reemplaza el anterior).

---

## REGLAS DE EJECUCIÓN

1. **No codificar**: Este protocolo produce documentación, no modifica código fuente.
2. **Hechos únicamente**: Toda afirmación debe tener evidencia (archivo:línea). Prohibido inferir.
3. **Reemplazar informe anterior**: Eliminar `governance/AUDITORIA_ESTADO_REAL.md` existente y crear uno nuevo.
4. **Verificar antes de declarar DONE**: Si la gobernanza dice `[DONE]`, buscar la implementación en código antes de confirmarlo.

---

## PASOS DE LA AUDITORÍA

### PASO 1 — Mapeo de código vivo vs muerto

Para cada módulo en `core_brain/`, `connectors/`, `data_vault/`:

- [ ] ¿Tiene import activo desde `start.py` o `main_orchestrator.py`?
- [ ] ¿Sus métodos principales son llamados en algún flujo de producción?
- [ ] ¿Contiene `TODO`, `# ...`, `pass`, `return {}` donde debería haber lógica real?

**Buscar específicamente**:
```
grep -r "TODO\|STUB\|pass\|return {}\|return \[\]" core_brain/ --include="*.py"
```

**Resultado esperado**: Lista de módulos con estado VIVO / MUERTO / STUB.

---

### PASO 2 — Auditoría del pipeline de datos

Para cada tabla `sys_*` en `data_vault/schema.py`:

- [ ] ¿Tiene métodos INSERT activos en algún `*_db.py`?
- [ ] ¿Esos métodos INSERT son llamados desde algún módulo de producción?
- [ ] ¿Tiene métodos SELECT que alimenten algún algoritmo de decisión?

**Buscar específicamente**:
```
grep -r "INSERT INTO sys_shadow_performance_history" .
grep -r "reload_config\|hot_reload" core_brain/
```

**Resultado esperado**: Para cada tabla relevante: ACTIVA (lee/escribe) / PASIVA (solo escribe, no retroalimenta) / VACÍA (DDL existe, nadie escribe).

---

### PASO 3 — Verificación de feedback loops adaptativos

Confirmar que estos bucles de aprendizaje ocurren en código real:

| Bucle | Archivo esperado | Verificar |
|---|---|---|
| EdgeTuner loop horario | `start.py` | `asyncio.create_task(run_edge_tuner_loop(...))` activo |
| Feedback post-trade | `trade_closure_listener.py` | `edge_tuner.process_trade_feedback()` llamado al cerrar trade |
| SHADOW evaluation | `shadow_manager.py` | `evaluate_all_instances()` sin stub — cuerpo real con iteración |
| Regime classification | `regime.py` | `classify()` llamado antes de cada ciclo de scan |

---

### PASO 4 — Sincronización gobernanza vs código

Para cada HU marcada `[DONE]` en `governance/BACKLOG.md`:

- [ ] ¿El artefacto de código listado existe en disco?
- [ ] ¿La función/clase principal existe?
- [ ] ¿Está integrada en el flujo (no huérfana)?

Para cada Épica en `governance/ROADMAP.md`:

- [ ] Si `COMPLETADA` → ¿está archivada en `governance/SYSTEM_LEDGER.md`? ¿eliminada del ROADMAP?
- [ ] Si `ACTIVA` → ¿hay un Sprint en curso con `[DEV]`?
- [ ] Si `PENDIENTE` → OK, no requiere verificación de código

---

### PASO 5 — Detección de artefactos legacy o huérfanos

- [ ] ¿Existe más de un archivo `ROADMAP.md` (raíz vs `governance/`)?
- [ ] ¿Hay documentos en `docs/` que sean informes temporales o de planificación obsoletos?
- [ ] ¿Existen conectores o módulos en el repo que no aparezcan en `sys_data_providers` de la BD?

---

## FORMATO DEL INFORME GENERADO

El informe `governance/AUDITORIA_ESTADO_REAL.md` debe contener:

```markdown
# AUDITORÍA DE ESTADO REAL — AETHELGARD
**Fecha**: [fecha actual]
**Versión del Sistema**: [leer de governance/ROADMAP.md]
**Informe anterior**: Eliminado ([fecha anterior])

## RESUMEN EJECUTIVO
[tabla: Severidad | Cantidad | Descripción]

## 🔴 HALLAZGOS CRÍTICOS
[solo si existen — con archivo:línea y evidencia]

## 🟡 HALLAZGOS MEDIOS
[inconsistencias de gobernanza, texto obsoleto]

## ✅ ESTADO DEL CÓDIGO VIVO
[tabla de módulos verificados]

## ✅ RESPUESTAS A PREGUNTAS CLAVE
[feedback loops, hot-reload, tablas pasivas, etc.]

## ✅ SINCRONIZACIÓN GOBERNANZA
[tabla de acciones tomadas en esta sesión]
```

---

## ACCIONES PERMITIDAS EN UNA AUDITORÍA

| Acción | Permitida |
|---|---|
| Leer archivos de código | ✅ |
| Ejecutar grep/glob para verificar imports | ✅ |
| Actualizar estados en BACKLOG/ROADMAP/SPRINT/SYSTEM_LEDGER | ✅ |
| Eliminar informe anterior y crear nuevo | ✅ |
| Eliminar artefactos legacy confirmados (ROADMAP raíz, docs temporales) | ✅ |
| Modificar código de producción | ❌ |
| Crear nuevas funciones o clases | ❌ |
| Ejecutar migrations o scripts en BD | ❌ |

---

*Última actualización del protocolo: 23-Mar-2026*
