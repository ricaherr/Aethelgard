# AETHELGARD: ESTRATEGIC ROADMAP

**Versión Log**: 2.5.5 (Diagnostic Shield)
**Última Actualización**: 22 de Febrero, 2026 (21:50)

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

### 🛡️ MILESTONE 5.6: UI Shield & Diagnostic Verbosity
*En Progreso 🚧*

**Objetivo**: Blindar la integridad del sistema con validaciones profundas de UI y reportes detallados en el orquestador de validación.

- [ ] **Diagnostic Verbosity**: Refactor de `validate_all.py` para reportar detalles técnicos (fichero/línea) en fallos.
- [ ] **UI Smoke Tests**: Script `ui_health_check.py` para validar accesibilidad de build y componentes críticos.
- [ ] **API UI Health**: Verificación de endpoints críticos que alimentan la interfaz.
- [ ] **Integridad en Cascada**: Reporte detallado sin interrupción del flujo de auditoría.

### ⚡ MILESTONE 6: Alpha Institucional (Ineficiencias Pro)
*Próximo Hito (después de 5.6)*

- [ ] **Detección de FVG (Fair Value Gaps)**: Algoritmo de búsqueda de desequilibrios institucionales.
- [ ] **Arbitraje de Volatilidad**: Detección de desconexión entre Volatilidad Implícita y Realizada.

### 🌐 EXPANSIÓN COMERCIAL & CONECTIVIDAD
- [ ] **Fase SaaS & Multi-Tenancy**: Perfiles de usuario, gestión de suscripciones y aislamiento de DB por cliente.
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales.

> [!NOTE]
> El historial completo de hitos anteriores ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).
