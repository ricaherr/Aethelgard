# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 3.0.0 (Micro-ETI 2.2: Migración de Datos de Mercado - COMPLETADO)
**Última Actualización**: 24 de Febrero, 2026 (23:30)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

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

