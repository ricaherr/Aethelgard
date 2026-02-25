# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.8.0 (Consolidación Estructural)
**Última Actualización**: 24 de Febrero, 2026 (21:40)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### 🏗️ CONSOLIDACIÓN ESTRUCTURAL (ETI: RECTIFICACIÓN_ARQUITECTÓNICA_V1)
- [x] **Fase 1 — Higiene Sistémica**: Eliminación de `system_state.json`, hardening de log rotation, script `workspace_cleanup.py`.
- [x] **Fase 2 — Desacoplamiento de Utilidades**: `normalize_price`/`normalize_volume`/`calculate_pip_size` → `utils/market_ops.py`.
- [ ] **Fase 3 — Higiene de Conectores**: Extraer `calculate_margin()` a `core_brain/risk_calculator.py`.
- [ ] **Fase 4 — Refactor de server.py**: ETI de alta complejidad (4 sub-fases).

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

