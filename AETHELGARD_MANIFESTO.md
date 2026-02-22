# AETHELGARD MANIFESTO
## Misión, Visión y Principios Filosóficos

**Versión**: 1.3
**Última Actualización**: Febrero 2026
**Estado del Proyecto**: Fase 2 - Universal Asset Normalization (v2.4.1)

---

## 🎯 Visión General

### ¿Qué es Aethelgard?
**Aethelgard** es un sistema de trading algorítmico **autónomo**, **agnóstico** y **adaptativo** diseñado para operar múltiples estrategias de manera inteligente basándose en la clasificación de régimen de mercado.

### Principios Fundamentales

#### 1. Autonomía
Aethelgard opera de forma independiente, tomando decisiones basadas en la clasificación automática de régimen de mercado y auto-calibración de parámetros.

#### 2. Agnosticismo de Plataforma
El sistema es independiente de cualquier plataforma específica. El **Core Brain** nunca depende de librerías de brokers, utilizando conectores modulares para la ejecución.

#### 3. Adaptatividad
Evoluciona mediante un **Feedback Loop** constante y un proceso de **Auto-Tune** sobre datos históricos.

---

## 🧠 Misión del Sistema
Crear un cerebro centralizado que:
- Clasifique el régimen de mercado en tiempo real.
- Active estrategias modulares según el contexto.
- Aprenda de sus resultados para mejorar continuamente.
- Proteja el capital mediante una guardia de riesgo inquebrantable.

---

## 🏗️ MILESTONE: Auditoría, Limpieza & Cerebro Console (2026-02-21)
**Estado: ✅ COMPLETADO**
**Resumen**: Refactorización profunda de documentación (`docs/`), revitalización de la Cerebro Console (UI/UX), implementación de Monitor a pantalla completa y corrección de errores de renderizado críticos (Error #31).
- **Monitor de Integridad & Diagnóstico L3**: Captura de errores profundos y puente de Auto-Gestión (EDGE) desactivable.

---

### 🌐 MILESTONE 3: Universal Trading Foundation (2026-02-21)
**Estado: ✅ COMPLETADO**
**Timestamp**: 18:25 | Versión: 2.5.0

**Resumen**: Implementación del Módulo de Normalización de Activos. Agnosticismo total de instrumentos mediante `asset_profiles` y cálculos de precisión con la librería `decimal`. Este milestone habilita operación real agnóstica sin depender de pips abstractos.

**Alcance Completado**:
- [x] **Tabla `asset_profiles` (SSOT)**: Base de datos maestra con normalización centralizada.
- [x] **Cálculo Universal (Unidades R)**: `RiskManager.calculate_position_size(symbol, risk_amount_usd, stop_loss_dist)` agnóstico.
- [x] **Aritmética Institucional**: Decimal + Downward Rounding para precisión.
- [x] **Test Suite Completa**: 289/289 tests pass (6/6 validaciones agnósticas).
- [x] **Documentación Técnica**: Esquema DB, fórmulas, ejemplos en `docs/02_RISK_CONTROL.md` & `docs/05_INFRASTRUCTURE.md`.

**Características Principales**:
- **Riesgo Uniforme**: $USD constante independientemente de Forex/Crypto/Metals.
- **Trazabilidad Completa**: Trace_ID único (NORM-XXXXXXXX) para auditoría.
- **Seguridad Integrada**: `AssetNotNormalizedError` si símbolo no normalizado → Trade bloqueado.
- **Escalabilidad**: Agregar nuevos símbolos solo requiere inserción en DB (sin código).

**Habilita**:
- ✅ Shadow Ranking (Milestone 4): Comparabilidad real de estrategias.
- ✅ Multi-Asset Trading: Forex, Crypto, Metals con lógica idéntica.
- ✅ Operación Institucional: Precisión decimal para auditoría regulatoria.

---

> [!IMPORTANT]
> Los detalles técnicos, diagramas de arquitectura y el historial de implementación han sido modularizados en la carpeta `docs/`.
> - Para detalles técnicos por dominio, ver `docs/01_ALPHA_ENGINE.md`, `docs/02_RISK_CONTROL.md`, etc.
> - Para el historial completo de cambios, ver `docs/SYSTEM_LEDGER.md`.
> - Para validación técnica, ejecutar: `python scripts/utilities/test_asset_normalization.py`
