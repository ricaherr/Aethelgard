# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 3.2.0 (Micro-ETI 3.1: Trading Service Extraction - COMPLETADO)
**Última Actualización**: 25 de Febrero, 2026 (00:00)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### ✅ MICRO-ETI 3.1: TRADING SERVICE EXTRACTION (Completado)
**Trace_ID**: ARCH-PURIFY-2026-001-A  
**Duración**: ~15 minutos  
**Reducción Monolito**: 835 líneas (1107 → 272, -75.4%)

- [x] **Creación de TradingService**: `core_brain/services/trading_service.py` (407 líneas)
  - [x] `process_signal()` migrado desde server.py
  - [x] `get_open_positions()` con StorageManager.get_position_metadata() (sin raw SQL)
  - [x] Balance helpers: `get_account_balance()`, `get_balance_metadata()`, `get_max_account_risk_pct()`
  - [x] MT5 connector lazy-loading
- [x] **Utilities centralizadas**: `classify_asset_type()` y `calculate_r_multiple()` en `utils/market_ops.py`
- [x] **Refactor trading.py**: Delegación a TradingService, eliminación de raw SQL
- [x] **Refactor risk.py**: Delegación a TradingService, eliminación de 6 helper wrappers
- [x] **Purge server.py**: Eliminados ~15 endpoints duplicados, helpers de balance, process_signal
- [x] **Validación PASSED**: `validate_all.py` 11/11 stages OK (5.99s)
- [x] **Server boot verificado**: MT5 conectado, scanner operativo, shutdown limpio

**Resultado**: Server.py minimal (272 líneas), lógica de trading 100% encapsulada en TradingService 🚀

### ✅ MICRO-ETI 2.3: EXTRACCIÓN CAPA CONTROL & NOTIFICACIONES (Completado)
**Trace_ID**: ARCH-DISSECT-2026-003-C  
**Duración**: ~8 minutos  
**Reducción Monolito**: 453 líneas (1564 → 1111, -28.9%)

- [x] **Creación de router Sistema**: `core_brain/api/routers/system.py` (385 líneas)
- [x] **Creación de router Notificaciones**: `core_brain/api/routers/notifications.py` (217 líneas)
- [x] **Migración de 15 endpoints de Auditoría & Configuración**:
  - [x] GET/POST `/api/config/{category}` (configuración agnóstica)
  - [x] GET/POST `/api/backup/settings` (políticas de backup)
  - [x] GET/POST `/api/system/status` & `/health`
  - [x] POST `/api/system/audit` (auditoría de integridad)
  - [x] POST `/api/system/audit/repair` (Auto-Gestión EDGE)
  - [x] GET `/api/edge/tuning-logs` (historial EdgeTuner)
- [x] **Migración de 11 endpoints de Telegram & Notificaciones**:
  - [x] POST `/api/telegram/validate` (validación token)
  - [x] POST `/api/telegram/get-chat-id` (auto-detección)
  - [x] POST `/api/telegram/test` (mensaje de prueba)
  - [x] POST `/api/telegram/save` (persistencia configuración)
  - [x] GET `/api/telegram/instructions` (instrucciones setup)
  - [x] GET/POST `/api/notifications/settings` (config proveedores)
  - [x] GET/POST `/api/notifications/{id}/mark-read` (notificaciones)
- [x] **Integración en create_app()**: `app.include_router(system_router, prefix="/api")` + `app.include_router(notifications_router, prefix="/api")`
- [x] **Validación PASSED**: `validate_all.py` 11/11 stages OK (6.84s)
- [x] **Server boot verificado**: Todos los routers lazy-loaded sin errores
- [x] **Funcionalidad operativa**: Botón "Run Integrity Audit" + Notificaciones Telegram 100% funcionales ✅

**Resultado**: Server.py modular y limpio (1111 líneas), capa de control extraída, Fase 3 de purificación lista 🚀

### ✅ MICRO-ETI 2.2: MIGRACIÓN DE DATOS DE MERCADO & RÉGIMEN (Completado)

**Trace_ID**: ARCH-DISSECT-2026-003-B  
**Duración**: ~7 minutos  
**Reducción Monolito**: 408 líneas (1901 → 1493, -21.5%)

- [x] **Creación de router de Mercado**: `core_brain/api/routers/market.py` (370 líneas)
- [x] **Migración de 8 endpoints críticos**:
  - [x] GET `/api/instrument/{symbol}/analysis` (análisis completo)+ 8 de Market
  - [x] GET `/api/chart/{symbol}/{timeframe}` (datos OHLC)
  - [x] GET `/api/regime/{symbol}` (régimen actual)
  - [x] GET `/api/regime_configs` (pesos dinámicos)
  - [x] GET `/api/instruments` (lectura de configuración)
  - [x] POST `/api/instruments` (actualización DRY)
- [x] **Lógica de Resilencia Preservada**: Heatmap mantiene fallback BD + scanner local
- [x] **Integración en create_app()**: `app.include_router(market_router, prefix="/api")`
- [x] **Validación PASSED**: `validate_all.py` 11/11 stages OK
- [x] **Sistema funcional**: Server startup exitoso, todas las dependencias lazy-loaded
- [x] **Panel Heatmap & Regime Change**: Cargan instantáneamente desde router

**Resultado**: Server.py limpio, endpoints agnósticos, arquitectura modular consolidada ✨

### ✅ MICRO-ETI 2.1: MIGRACIÓN DE ROUTERS DE OPERACIONES (Completado)
- [x] **Creación de estructura modular**: `core_brain/api/routers/`
- [x] **Migración de 5 endpoints de Trading**: `/api/signals`, `/api/signals/execute`, `/api/positions/open`, `/api/edge/history`, `/api/auto-trading/toggle`
- [x] **Migración de 5 endpoints de Riesgo**: `/api/risk/status`, `/api/risk/summary`, `/api/satellite/status`, `/api/satellite/toggle`, `/api/edge/tuning-logs`
- [x] **Integración en create_app()**: `app.include_router(trading_router, prefix="/api")` y `app.include_router(risk_router, prefix="/api")`
- [x] **Validación PASSED**: `validate_all.py` 11/11 stages OK (10.51s)
- [x] **Server startup verificado**: Todos los módulos inicializados correctamente
- [x] **Routers funcionales**: 9 rutas de Trading + 7 rutas de Riesgo (con duplicados únicamente en legacy)

**Nota**: Los 10 endpoints migrados coexisten temporalmente en `server.py` (legacy) y en los routers nuevos. Próxima fase: eliminar endpoints legacy en cleanup phase.

### 🏗️ CONSOLIDACIÓN ESTRUCTURAL (ETI: RECTIFICACIÓN_ARQUITECTÓNICA_V1)
- [x] **Fase 1 — Higiene Sistémica**: Eliminación de `system_state.json`, hardening de log rotation, script `workspace_cleanup.py`.
- [x] **Fase 2 — Desacoplamiento de Utilidades**: `normalize_price`/`normalize_volume`/`calculate_pip_size` → `utils/market_ops.py`.
- [ ] **Fase 3 — Higiene de Conectores**: Extraer `calculate_margin()` a `core_brain/risk_calculator.py`.
- [x] **Fase 4 — Refactor de server.py (Micro-ETI 2.1)**: Router de Trading & Riesgo separados exitosamente.

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD & 2.2)**: Routers de Trading, Riesgo & Mercad
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

