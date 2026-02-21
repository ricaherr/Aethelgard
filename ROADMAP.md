# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.4.0 (Autonomous Integrity Matrix)
**Última Actualización**: 21 de Febrero, 2026

---

## 🏗️ MILESTONE: Auditoría, Limpieza & Cerebro Console (2026-02-21)
**Estado: ✅ COMPLETADO**
**Resumen**: Refactorización profunda de documentación (`docs/`), revitalización de la Cerebro Console (UI/UX), implementación de Monitor a pantalla completa y corrección de errores de renderizado críticos (Error #31).
- **Monitor de Integridad L3**: Diagnóstico profundo de fallos con captura de excepciones.
- **Protocolo de Auto-Gestión L1**: Puente para reparaciones autónomas (Inactivado para validación).

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### MILESTONE 3: Universal Trading Foundation (Agnosticismo & Normalización)
*Estado: Pendiente | Prioridad: CRÍTICA (Habilita Forex Operativo)*

- [ ] **Tabla `asset_profiles` (SSOT)**: Creación de la base de datos maestra para normalizar Tick Size, Point Value y Comisiones por activo.
- [ ] **Agnosticismo de Tick (Unidades R)**: Refactorización del `RiskManager` para que el lotaje dependa del ATR y el Riesgo monetario, no de pips fijos.
- [ ] **Módulo de Sesiones (Golden Hours)**: Implementación de filtros horarios por mercado (Londres/NY/Tokyo) para evitar baja liquidez.

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
