# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.5.0 (Shadow Ranking & Darwinismo Algorítmico)
**Última Actualización**: 22 de Febrero, 2026 (20:58)

---

## 📈 ROADMAP ESTRATÉGICO (Próximos Hitos)

### 🎨 MILESTONE 5.5: Visualización Premium Intelligence Terminal (EDGE Hub Refactor)
*Completado ✅*

**Objetivo**: Rediseñar la UI para visualizar el "Darwinismo Algorítmico" (rankings dinámicos por régimen) en un estilo Premium Intelligence Terminal.

- [x] **Backend: Endpoint `/api/regime_configs`** - Exponer pesos de regime_configs para visualización frontend
- [x] **RegimeBadge Component** - Indicador visual animado del régimen actual (TREND/RANGE/VOLATILE) con heartbeat
- [x] **WeightedMetricsVisualizer** - Gráfico de pesos dinámicos que responde a cambios de régimen (CSS dinamico)
- [x] **AlphaSignals Refactor** - Agregar `execution_mode` (LIVE/SHADOW/QUARANTINE) + `ranking_score` a cada señal
- [x] **EdgeHub Integration** - Incorporar nuevos componentes manteniendo flujo WebSocket en tiempo real
- [x] **Estilo Premium**: Negro (#050505) + Aethelgard Green / Neon Red + Outfit/Inter tipografía

### ⚡ MILESTONE 6: Alpha Institucional (Ineficiencias Pro)
*Próximo Hito (después de 5.5)*

- [ ] **Detección de FVG (Fair Value Gaps)**: Algoritmo de búsqueda de desequilibrios institucionales.
- [ ] **Arbitraje de Volatilidad**: Detección de desconexión entre Volatilidad Implícita y Realizada.

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).
