# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.4.1 (Universal Asset Normalization)
**Última Actualización**: 21 de Febrero, 2026 (18:25)

---

## 🏗️ MILESTONE: Auditoría, Limpieza & Cerebro Console (2026-02-21)
**Estado: ✅ COMPLETADO**
**Resumen**: Refactorización profunda de documentación (`docs/`), revitalización de la Cerebro Console (UI/UX), implementación de Monitor a pantalla completa y corrección de errores de renderizado críticos (Error #31).
- **Monitor de Integridad L3**: Diagnóstico profundo de fallos con captura de excepciones.
- **Protocolo de Auto-Gestión L1**: Puente para reparaciones autónomas (Inactivado para validación).

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### ✅ MILESTONE 3: Universal Trading Foundation (Agnosticismo & Normalización)
*Estado: ✅ COMPLETADO (2026-02-21) | Timestamp: 18:25*

- [x] **Tabla `asset_profiles` (SSOT)**: Creación de la base de datos maestra para normalizar Tick Size, Contract Size, Lot Step y Comisiones por activo.
  - Implementación: `data_vault/market_db.py` & `data_vault/storage.py`
  - Datos iniciales: EURUSD, GBPUSD, USDJPY, GOLD, BTCUSD
  - Validación: ✅ Test suite completo (289/289 tests pass)

- [x] **Cálculo Universal (Unidades R)**: Refactorización agnóstica del `RiskManager.calculate_position_size()` con precisión institucional.
  - Aritmética: `Decimal` para evitar errores de punto flotante
  - Redondeo: Downward rounding (ROUND_DOWN) según `lot_step` del activo
  - Trazabilidad: Cada cálculo genera Trace_ID único (ej: NORM-0a9dfe65)
  - Seguridad: `AssetNotNormalizedError` si símbolo no existe en `asset_profiles`

- [x] **Normalización SSOT & Testing**: Validación completa con precisión decimal.
  - Script: `scripts/utilities/test_asset_normalization.py`
  - Resultado: TODOS LOS TESTS PASARON (6/6 validaciones OK)

### 🧠 MILESTONE 4: Estratega Evolutivo (Darwinismo Algorítmico)
*Próximo Hito - Habilitado por Normalización de Unidades R*

### 🧠 MILESTONE 4: Estratega Evolutivo (Darwinismo Algorítmico)
- [ ] **Shadow Ranking System**: Sistema de puntuación interna. Solo el Top 3 de estrategias con Profit Factor > 1.5 en simulación pasan a real.
- [ ] **Weighted Signal Composite (The Jury)**: El `SignalFactory` ahora promedia votos de múltiples estrategias según el Régimen de Mercado.
- [ ] **Feedback Loop 2.0 (Edge Discovery)**: Análisis automático de "Lo que pudo ser" (Price action 20 velas después) para ajustar los pesos del Jurado.

### ⚡ MILESTONE 5: Alpha Institucional (Ineficiencias Pro)
- [ ] **Detección de FVG (Fair Value Gaps)**: Algoritmo de búsqueda de desequilibrios institucionales.
- [ ] **Arbitraje de Volatilidad**: Detección de desconexión entre Volatilidad Implícita y Realizada.

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).
