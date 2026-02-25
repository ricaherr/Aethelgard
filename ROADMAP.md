# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.9.0 (Micro-ETI 2.1: Migración de Routers de Operaciones)
**Última Actualización**: 24 de Febrero, 2026 (23:20)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

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

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

