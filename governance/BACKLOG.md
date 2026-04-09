# AETHELGARD: MASTER BACKLOG

> **📋 REGLAS DE EDICIÓN — Leer antes de modificar este documento**
> - **Propósito**: Catálogo oficial y único de todos los requerimientos PENDIENTES del sistema.
> - **Estructura**: 10 dominios fijos. Toda HU numerada como `HU X.Y` (X = dominio, Y = secuencia correlativa).
> - **Nuevo requerimiento**: SIEMPRE registrar aquí primero, sin estado, bajo el dominio correcto.
> - **Estados únicos permitidos**: *(sin estado)* · `[TODO]` · `[DEV]` · `[DONE]`
> - **`[DONE]`** solo si `validate_all.py` ✅ 100%. HUs completadas se **ELIMINAN** de este BACKLOG y se archivan en `SYSTEM_LEDGER.md`. Este archivo contiene únicamente trabajo pendiente.
> - **PROHIBIDO**: `[x]`, `[QA]`, `[IN_PROGRESS]`, `[COMPLETADA]`, `✅ DONE`, `[ACTIVO]`
> - **Framework completo**: `.ai_orchestration_protocol.md` Sección 4.

## 🛠️ ESTÁNDAR TÉCNICO DE CONSTRUCCIÓN
1. **Backend: La Fortaleza Asíncrona**
   * **Principio de Aislamiento (Multitenancy)**: El `tenant_id` es el átomo central. Ninguna función de base de datos o lógica de negocio puede ejecutarse sin la validación del contexto del usuario.
   * **Agnosticismo de Datos**: El Core Brain no debe conocer detalles del broker (MT5/FIX). Debe trabajar solo con Unidades R y estructuras normalizadas.
   * **Rigor de Tipado**: Uso estricto de Pydantic para esquemas y `Decimal` para cálculos financieros. Prohibido el uso de `float` en lógica de dinero.
   * **Feedback Inmediato**: Cada acción del backend debe emitir un evento vía WebSocket, incluso si es un fallo, para que la UI "sienta" el latido del sistema.

2. **Frontend: La Terminal de Inteligencia**
   * **Estética "Intelligence Terminal"**: Prohibido el uso de componentes de librerías comunes (como MUI o Bootstrap estándar) sin ser personalizados al estilo Bloomberg-Dark (#050505, acentos cian/neón).
   * **Densidad de Información**: Diseñar para el experto. La UI debe mostrar datos de alta fidelidad sin saturar, usando transparencias y capas (Glassmorphism).
   * **Micro-animaciones Funcionales**: Los cambios de estado no son instantáneos; deben "pulsar" o "deslizarse". La UI debe parecer un organismo vivo, no una página web estática.
   * **Estado Centralizado en el Servidor**: El frontend es "tonto". Solo renderiza lo que el cerebro (Backend) le dice. La lógica de trading nunca reside en React.

> [!NOTE]
> **Estados de HU** *(ver header de este documento y `.ai_orchestration_protocol.md` Sección 4)*:
> | Estado | Significado |
> |---|---|
> | *(sin estado)* | Identificada, sin Sprint asignado |
> | `[TODO]` | En Sprint activo, no iniciada |
> | `[DEV]` | En desarrollo activo |
> | `[DONE]` | Completada → se archiva en SYSTEM_LEDGER y se elimina de este archivo |
>
> **PROHIBIDO**: `[x]` · `[QA]` · `[IN_PROGRESS]` · `[COMPLETADA]` · `✅ DONE`

---

## 01_IDENTITY_SECURITY (SaaS, Auth, Isolation)
* **HU 1.3: User Role & Membership Level** `[TODO]` *(Deuda Técnica — Prioridad Máxima)*
    * **Qué**: Completar la jerarquía de acceso SaaS (Admin / Pro / Basic — 3 tiers).
    * **Estado actual**: `ModuleManager` existe con BASIC/PREMIUM (2 niveles). `tier` en `sys_users` con `update_user_tier()`. Pero: (1) spec requiere 3 niveles; (2) `ModuleManager` lee de `modules.json` violando SSOT (debe leer de DB); (3) UI de perfil con features bloqueadas/desbloqueadas no implementada.
    * **Para qué**: Comercialización SaaS basada en niveles de membresía.
    * **🖥️ UI Representation**: Menú de perfil donde el usuario vea su rango actual y las funcionalidades bloqueadas/desbloqueadas según su plan.

---

## 02_CONTEXT_INTELLIGENCE (Regime, Multi-Scale)
*(Sin HUs pendientes — ver SYSTEM_LEDGER E2: Trace_ID SAAS-GENESIS-2026-001)*

---

## 03_ALPHA_GENERATION (Signal Factory, Indicators)
* **HU 3.3: Multi-Market Alpha Correlator** `[TODO]`
    * **Prioridad**: Baja
    * **Descripción**: Scanner de confluencia inter-mercado para validación cruzada de señales de alta fidelidad.
    * **🖥️ UI Representation**: Widget de "Correlación Sistémica" con indicadores de fuerza y dirección multi-activo.


---

## 04_RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)
*(Sin HUs pendientes — todas archivadas en SYSTEM_LEDGER)*

---

## 05_UNIVERSAL_EXECUTION (EMS, Conectores FIX)
*(Sin HUs pendientes — todas archivadas en SYSTEM_LEDGER)*

---

## 06_PORTFOLIO_INTELLIGENCE (Shadow, Performance)
* **HU 6.1: Shadow Reality Engine (Penalty Injector)** `[TODO]`
    * **Prioridad**: Alta
    * **Descripción**: Desarrollo del motor de ajuste que inyecta latencia y slippage real en el rendimiento de estrategias Shadow (Lineamiento F-001).
    * **🖥️ UI Representation**: Gráfico de equity "Shadow vs Theory" con desglose de pips perdidos por ineficiencia.

* **HU 6.2: Multi-Tenant Strategy Ranker** `[TODO]`
    * **Descripción**: Sistema de clasificación darwinista para organizar estrategias por rendimiento ajustado al riesgo **por usuario (tenant)**. El `StrategyRanker` existente opera a nivel de sistema global (sin `user_id`). Brecha confirmada: falta `get_rankings_for_user(user_id)`, endpoint REST y UI de portafolio individual.
    * **Resolución de ambigüedad**: `core_brain/strategy_ranker.py` cubre el motor del sistema (SHADOW→LIVE transitioning). Esta HU añade la capa multi-tenant de visibilidad y ranking por trader.
    * **🖥️ UI Representation**: Dashboard "Strategy Darwinism" con rankings dinámicos y estados de cuarentena por usuario.


---

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
*(Sin HUs pendientes — todas archivadas en SYSTEM_LEDGER)*


---

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)

* **HU 8.8: SSOT Execution Mode Drift Fix** `[DONE]` *(✅ Verificado: tests 7/7 + validate_all 28/28)*
    * **Qué**: `sys_strategies.mode` (SSOT) = `'SHADOW'` para MOM_BIAS_0001, LIQ_SWEEP_0001 y STRUC_SHIFT_0001. Pero `sys_signal_ranking.execution_mode` = `'BACKTEST'` (congelado en lazy-init del 05-Apr). `StrategyEngineFactory._get_execution_mode()` lee el campo derivado en lugar del SSOT, lo que hace que `is_strategy_authorized_for_execution()` retorne `False` para las 3 estrategias. Ninguna señal ejecuta, ningún shadow trade ocurre — el sistema es un zombie.
    * **Causa raíz**: SSOT violation enmascarada — hay DOS campos almacenando el modo de ejecución. La factory lee el segundario (`sys_signal_ranking.execution_mode`) que quedó desactualizado; no hay mecanismo de sincronización ni reconciliación.
    * **Para qué**: Desbloquear el pipeline completo: señales → shadow trades → métricas → promoción.
    * **Archivos afectados**: `data_vault/sys_signal_ranking_db.py`, `core_brain/services/strategy_engine_factory.py`


---

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)

* **HU 9.9: UI Confidence Display Overflow Fix** `[TODO]`
    * **Qué**: El log muestra `[Conf: 558%]` para GBPUSD y `[Conf: 447%]` para XAGUSD en `_cycle_scan.py:466`. `market_structure_analyzer` retorna `confidence` como valor 0-100 (e.g. 55.8), pero en algún punto de la cadena se multiplica por 10x antes de llegar al formato `{:.0f}%`. Bug afecta logs de UI_MAPPING y potencialmente el widget de estructura en el front.
    * **Archivos afectados**: `core_brain/orchestrators/_cycle_scan.py`, `core_brain/sensors/market_structure_analyzer.py`


---

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
*(Sin HUs pendientes — HU 10.1 archivada en SYSTEM_LEDGER E3 + E14)*

* **HU 10.24: Shadow Pool Bootstrap Diagnostics** `[TODO]`
    * **Qué**: `initialize_shadow_pool_impl` reporta `"0 created, 0 skipped, 0 failed"` engañosamente. Cuando las 3 estrategias ya tienen 2 instancias activas, el branch `already_active >= variations_per_strategy` hace `continue` sin incrementar `skipped_count`. El operador no puede distinguir entre "no hay estrategias elegibles" y "todas ya tienen instancias máximas".
    * **Archivos afectados**: `core_brain/orchestrators/_discovery.py`

* **HU 10.25: Health Endpoint SRE** `[TODO]`
    * **Qué**: `GET /health` retorna 404. Un sistema de trading institucional sin healthcheck liviano no puede ser monitoreado por watchdog externo ni herramienta SRE. Endpoint debe exponer: heartbeat activo, modo operacional actual, última señal y último trade — sin autenticación (público, pero sin datos sensibles).
    * **Archivos afectados**: `core_brain/api/routers/system.py` o nuevo `health.py`

* **HU 10.26: Heartbeat Audit Trail Repair** `[TODO]`
    * **Qué**: `sys_audit_logs` no recibe entradas `HEARTBEAT` desde 2026-04-06 (>82h de gap detectado en auditoría SRE). `update_module_heartbeat()` en `data_vault/system_db.py:297` escribe en `sys_config` correctamente pero la escritura canónica en `sys_audit_logs` parece vetada por el throttle `heartbeat_audit_interval_s`. Investigar si el throttle está bloqueando la escritura inicial o si hay una condición silenciada.
    * **Archivos afectados**: `data_vault/system_db.py`, `core_brain/operational_edge_monitor.py`




