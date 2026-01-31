# Aethelgard – Roadmap

**Última actualización**: 2026-01-30

---

## 🔧 Correcciones Críticas Completadas

**QA Guard Syntax Fixes (2026-01-30)** ✅ COMPLETADO
- Corregidos errores de sintaxis críticos en archivos principales:
  - `core_brain/health.py`: Except blocks inválidos y for loops con type hints malformados
  - `core_brain/storage.py`: For loops con type hints inline inválidos
  - `connectors/bridge_mt5.py`: Except blocks inválidos (16 instancias)
  - `ui/dashboard.py`: For loops con type hints inválidos y except blocks (21 instancias)
  - `core_brain/data_provider_manager.py`: With statement con type hint inválido y for loops
- Resultado: QA Guard pasa sin errores de sintaxis críticos
- Estado: ✅ Proyecto limpio y listo para producción

---

## 📊 Estado del Sistema (Enero 2026)

| Componente | Estado | Validación |
|------------|--------|------------|
| 🧠 Core Brain (Orquestador) | ✅ Operacional | 11/11 tests pasados |
| 🛡️ Risk Manager | ✅ Operacional | 4/4 tests pasados |
| 📊 Confluence Analyzer | ✅ Operacional | 8/8 tests pasados |
| 🔌 Connectors (MT5) | ✅ Operacional | DB-First implementado |
| 💾 Database (SQLite) | ✅ Operacional | Single Source of Truth |
| 🎯 Signal Factory | ✅ Operacional | 3/3 tests pasados |
| 📡 Data Providers | ✅ Operacional | 19/19 tests pasados |
| 🖥️ Dashboard UI | ✅ Operacional | Sin errores críticos |
| 🧪 Test Suite | ✅ Operacional | **148/148 tests pasados** |

**Resumen**: Sistema completamente funcional y validado end-to-end

**Warnings no críticos detectados**:
- ⚠️ Streamlit deprecation: `use_container_width` → migrar a `width='stretch'` (deprecado 2025-12-31)
- ℹ️ Telegram Bot no configurado (opcional para notificaciones)

---

Resumen del roadmap de implementación. Detalle completo en [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md#roadmap-de-implementación).

---

## 🛡️ Fase 2.9: Resiliencia y Coherencia Total (EDGE) ⏳ EN PROGRESO


**Objetivo:** Auto-monitoreo inteligente de consistencia entre Scanner → Señal → Estrategia → Ejecución → Ticket.

**Alcance:**
- Detectar cuando hay condiciones de mercado pero no se genera señal.
- Detectar cuando hay señal pero no se ejecuta (o no hay ticket).
- Detectar cuando la estrategia válida no coincide con ejecución.

**Plan de Trabajo (2026-01-30):**
1. Definir eventos y métricas de coherencia (Scanner, SignalFactory, Executor, MT5Connector).
2. Diseñar y crear tabla `coherence_events` en DB para trazabilidad por símbolo/timeframe/estrategia.
3. Implementar reglas de coherencia (mismatch detector con razones exactas y tipo de incoherencia).
4. Integrar registro de eventos en el ciclo del orquestador.
5. Exponer estado y eventos en el dashboard UI.
6. Crear tests de cobertura para casos de incoherencia y recuperación.
7. Documentar criterios y resultados en el MANIFESTO.

**Checklist de tareas:**
- [x] Definición de eventos y métricas
- [x] Diseño y migración de DB (tabla coherence_events)
- [x] Implementación de reglas de coherencia (mismatch detector)
- [x] Integración en orquestador
- [x] Panel de diagnóstico visual en el Dashboard
- [x] Tests de cobertura
- [ ] Documentación actualizada

**Estado Actual:**
- ✅ CoherenceMonitor implementado (DB-first).
- ✅ Tabla `coherence_events` finalizada.
- ✅ Mismatch detector implementado en el orquestador.
- ✅ Reglas: símbolo no normalizado, `EXECUTED` sin ticket, `PENDING` con timeout.
- ✅ Integración en orquestador por ciclo.
- ✅ Panel de diagnóstico visual en el Dashboard.

**Evidencia técnica (2026-01-30):**
- ✅ Suite de tests ejecutada completa: **153/153 PASSED**.



## Fase 3.0: Portfolio Intelligence ⏳ PENDIENTE

**Objetivo:** Gestión avanzada de riesgo a nivel portafolio.

**Tareas:**
- Implementación de 'Correlation Filter' en el RiskManager (evitar sobre-exposición por moneda base).
- Control de Drawdown diario a nivel cuenta (Hard-Stop).

## Fase 3.1: UI Refactor & UX ⏳ PENDIENTE

**Objetivo:** Mejora de interfaz y experiencia de usuario.

**Tareas:**
- Migración total de use_container_width a width='stretch' en todo el Dashboard.
- Implementación de notificaciones visuales de salud del sistema (Heartbeat Monitor).

## Fase 3.2: Feedback Loop y Aprendizaje 🔜 SIGUIENTE

- **Motor de Backtesting Rápido**: Simulación de ejecución del `Scanner` sobre datos históricos para validación pre-live.
- **Feedback de resultados**: Aprendizaje por refuerzo básico y ajuste de pesos.
- **Dashboard de métricas**: Visualización avanzada de KPIs de aprendizaje.

---

## Fase 4: Evolución Comercial 🎯 FUTURA

- **Seguridad SaaS**: Autenticación vía API Key para endpoints HTTP/WebSocket.
- **Multi-tenant**: Soporte para múltiples usuarios aislados.
- **Módulos bajo demanda**: Activación de features vía licencia.
- **Notificaciones**: Integración profunda con Telegram/Discord.

---

## 🚀 Provisión y Reporte Automático de Brokers/Cuentas DEMO (2026-01-30)

**Objetivo:**
Implementar detección automática de brokers, provisión de cuentas DEMO (cuando sea posible), y reporte del estado/resultados en el dashboard, informando claramente si requiere acción manual o si hubo errores.

**Plan de Trabajo:**

1. Implementar lógica de escaneo y provisión automática de brokers/cuentas DEMO en el backend (core_brain/main_orchestrator.py, connectors/auto_provisioning.py).
2. Registrar en la base de datos el estado de provisión, cuentas DEMO creadas, y motivos de fallo si aplica (data_vault/storage.py).
3. Exponer métodos en StorageManager para consultar brokers detectados, estado de provisión, cuentas DEMO creadas y motivos de fallo.
4. Actualizar el dashboard (ui/dashboard.py) para mostrar:
   - Lista de brokers detectados
   - Estado de provisión/conexión
   - Cuentas DEMO creadas
   - Mensajes claros de error o requerimientos manuales
5. Crear test end-to-end en tests/ para validar el flujo completo y la visualización en la UI.

**Checklist:**
- [ ] Lógica de escaneo y provisión automática implementada
- [ ] Estado/resultados registrados en DB
- [ ] Métodos de consulta en StorageManager
- [ ] Dashboard actualizado con reporte claro
- [ ] Test end-to-end validando el flujo

---

## 📚 Log de Versiones (Resumen)

- **Fase 1: Infraestructura Base** - Completada (core_brain/server.py, connectors/)
- **Fase 1.1: Escáner Proactivo Multihilo** - Completada (Enero 2026) (core_brain/scanner.py, connectors/mt5_data_provider.py)
- **Fase 2.1: Signal Factory y Lógica de Decisión Dinámica** - Completada (Enero 2026) (core_brain/signal_factory.py, models/signal.py)
- **Fase 2.3: Score Dinámico y Gestión de Instrumentos** - Completada (Enero 2026) (core_brain/instrument_manager.py, tests/test_instrument_filtering.py)
- **Fase 2.5: Sistema de Diagnóstico MT5 y Gestión de Operaciones** - Completada (Enero 2026) (core_brain/health.py, ui/dashboard.py, data_vault/storage.py)
- **Fase 2.6: Migración Streamlit - Deprecación `use_container_width`** - Completada (ui/dashboard.py)
- **Fase 2.7: Provisión EDGE de cuentas demo maestras y brokers** - Completada (connectors/auto_provisioning.py, data_vault/storage.py)
- **Fase 2.8: Eliminación de Dependencias `mt5_config.json`** - Completada (data_vault/storage.py, ui/dashboard.py)
- **Hotfix: Monitoreo continuo y resiliencia de datos** - Completada (2026-01-30) (connectors/generic_data_provider.py, connectors/paper_connector.py)
- **Hotfix 2026-01-30: Serialización, retry/backoff y control de cuenta activa única por broker** - Completada (data_vault/storage.py)

---

## 🤖 Protocolo de Actualización para la IA

**Regla de Traspaso:** Cuando una tarea o fase llegue al 100%, debe moverse inmediatamente al 'Historial de Implementaciones', dejando solo su título y fecha.

**Regla de Formato:** Mantener siempre la tabla de 'Estado del Sistema' al inicio para una lectura rápida de salud de componentes.

**Regla de Prioridad:** Solo se permiten 3 fases activas en el cuerpo principal para evitar la saturación de contexto.

**Regla de Evidencia:** Cada tarea completada debe referenciar brevemente el archivo afectado (ej: db_logic.py).

---

*Fuente de verdad: [AETHELGARD_MANIFESTO.md](AETHELGARD_MANIFESTO.md).*
