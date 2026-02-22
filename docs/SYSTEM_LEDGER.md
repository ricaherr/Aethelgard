# AETHELGARD: SYSTEM LEDGER

**Version**: 1.0.0
**Status**: ACTIVE
**Description**: Historial cronológico de implementación, refactorizaciones y ajustes técnicos.

---

## 📜 Historial de Versiones (Manifesto Logs)

> [!NOTE]
> Esta sección contiene el registro de cambios extraído del Manifiesto original.

render_diffs(file:///c:/Users/Jose Herrera/Documents/Proyectos/Aethelgard/AETHELGARD_MANIFESTO.md)

---

## 📅 Hitos Completados (Historic Roadmap)

> [!NOTE]
> Registro detallado de milestones finalizados migrados desde el Roadmap.

render_diffs(file:///c:/Users/Jose Herrera/Documents/Proyectos/Aethelgard/ROADMAP.md)

---

## 🛠️ Detalles Técnicos Históricos

> [!NOTE]
> Detalles de implementación de módulos base (Executor, Deduplication, etc.) migrados para limpieza del Manifiesto.

### 📅 Registro: 2026-02-21
- **Fase 5 y 6: Revitalización Cerebro Hub**
    - Refactorización de `CerebroConsole.tsx` con estilos premium e iconos dinámicos.
    - Transformación del "Monitor" de un Drawer a una página primaria (`MonitorPage.tsx`).
    - Corrección del error de renderizado #31 de React mediante filtrado de heartbeats.
    - Aumento de verbosidad en `MainOrchestrator` para flujos en tiempo real.
- **Monitor de Integridad & Diagnóstico L3**
    - Implementación de `AuditLiveMonitor.tsx` con captura de excepciones en tiempo real.
    - Soporte para metadatos `DEBUG_FAIL` en el backend para reportes detallados.
    - Creación del puente para Auto-Gestión (EDGE) L1 (Endpoint `/api/system/audit/repair`).
    - Inactivación preventiva del protocolo de reparación hasta validación de efectividad técnica.
- **Resolución de Inconsistencias Críticas (Fuga de Estabilidad)**
    - **MT5Connector**: Corrección de `modify_position` (+ implementado `order_send` y métodos auxiliares de validación).
    - **Orquestación**: Corrección de inyección de dependencias en `SignalFactory` dentro de `main_orchestrator.py`.
    - **API Integration**: Exposición de `scanner` y `orchestrator` como globales para acceso real del servidor API.
    - **Validación Final**: Sistema verificado al 100% de integridad tras correcciones estructurales.

#### 🌐 MILESTONE 3: Universal Trading Foundation (Agnosticismo & Normalización)
**Timestamp**: 2026-02-21 18:25  
**Estado Final**: ✅ COMPLETADO

**Implementación**:
1. **Infraestructura SSOT (`asset_profiles` table)**
   - Ubicación: `data_vault/market_db.py` (método `_seed_asset_profiles()`)
   - Normalización centralizada: Tick Size, Contract Size, Lot Step, Pip Value
   - Datos iniciales: EURUSD, GBPUSD, USDJPY, GOLD, BTCUSD
   - Lectura: `StorageManager.get_asset_profile(symbol, trace_id)`

2. **Cálculo Agnóstico Universal**
   - Método: `RiskManager.calculate_position_size(symbol, risk_amount_usd, stop_loss_dist)`
   - Aritmética: `Decimal` (IEEE 754 → Decimal para precisión institucional)
   - Fórmula: `Lots = Risk_USD / (SL_Dist * Contract_Size)`
   - Redondeo: `ROUND_DOWN` según `lot_step` del activo
   - Seguridad: `AssetNotNormalizedError` si símbolo no normalizado
   - Trazabilidad: Trace_ID único para auditoría (ej: `NORM-0a9dfe65`)

3. **Actualización de Tests**
   - Archivo: `tests/test_risk_manager.py`
   - Cambios: Eliminación de argumentos legacy (`account_balance`, `point_value`, `current_regime`)
   - Firma agnóstica: Todos los tests usan `(symbol, risk_amount_usd, stop_loss_dist)`
   - Resultado: 289/289 tests pass (6/6 validaciones agnósticas OK)

4. **Documentación & Validación**
   - Script de validación: `scripts/utilities/test_asset_normalization.py`
   - Salida: ✅ TODOS LOS TESTS PASARON
   - Precisión: Downward rounding 0.303030 → 0.3 validado
   - Cobertura: Forex majors, exóticos, metals, crypto

**Archivos Modificados**:
- `core_brain/risk_manager.py`: Nueva firma agnóstica + Decimal + ROUND_DOWN
- `data_vault/market_db.py`: Tabla `asset_profiles` + seeding inicial
- `data_vault/storage.py`: Método `get_asset_profile()` + lectura SSOT
- `tests/test_risk_manager.py`: Actualización de tests a firma agnóstica
- `docs/02_RISK_CONTROL.md`: Documentación de Agnosticismo & Filosofía
- `docs/05_INFRASTRUCTURE.md`: Esquema de `asset_profiles` + Datos iniciales
- `ROADMAP.md`: Milestone 3 marcado como COMPLETADO
- `AETHELGARD_MANIFESTO.md`: Entrada de Milestone 3 con estado COMPLETADO

**Impacto**:
- ✅ Riesgo uniforme en USD independientemente del instrumento
- ✅ Comparabilidad real entre estrategias (habilita Shadow Ranking)
- ✅ Seguridad: Bloqueo de trades sin normalización
- ✅ Auditoría: Trace_ID completo para cada cálculo
- ✅ Escalabilidad: Fácil agregar nuevos símbolos via DB
