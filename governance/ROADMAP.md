# AETHELGARD: ESTRATEGIC ROADMAP

"ESTÁNDAR DE EDICIÓN: El Roadmap se organiza en Vectores de Valor (V1, V2...). Cada hito debe estar vinculado a uno de los 10 dominios del BACKLOG."

**Versión Log**: 3.4.0 (V1: Cimientos SaaS - ACTIVO)
**Última Actualización**: 26 de Febrero, 2026 (16:49)

<!-- REGLA DE ARCHIVADO: Cuando TODOS los items de un milestone estén [x], -->
<!-- migrar automáticamente a docs/SYSTEM_LEDGER.md con el formato existente -->
<!-- y eliminar el bloque del ROADMAP. Actualizar la Versión Log. -->

---

## 📈 ROADMAP ESTRATÉGICO (Vectores de Valor)

### 🚀 V1 (Vector de Cimientos SaaS) — ACTIVO (Dominios 01 y 08)
**Prioridad Máxima**  
**Trace_ID**: SAAS-GENESIS-2026-001  
**Objetivo**: Evolucionar el sistema de un solo usuario a una arquitectura multi-tenant con autenticación JWT y aislamiento de datos por tenant.

- [x] **Manifesto Transformation**: Restructuración del `AETHELGARD_MANIFESTO.md` hacia una Constitución Estratégica.
- [x] **Auth Gateway & JWT Protection**: Implementación de middleware de seguridad y login premium (HU 1.1).
- [ ] **Tenant Isolation Protocol**: Aislamiento total de datos por cliente vía TenantDBFactory (HU 1.2).
- [ ] **SaaS Membership Hierarchy**: Definición de roles (Admin, Pro, Basic) y niveles de acceso (HU 1.3).
- [ ] **Validación E2E**: Tests de integración para flujo auth completo + aislamiento de datos.
- [ ] **Sovereignty Gateway**: Habilitación de control y matriz de permisos autónomos (HU 4.4). *Nota: Dependencia técnica clave para V1.*
- [ ] **Infrastructure Health Monitoring**: Telemetría básica de salud del servidor para estabilidad multi-tenant (HU 5.3 preliminar).
- [ ] **Multi-Tenant Strategy Ranking**: Clasificación darwinista de estrategias por usuario (HU 6.2).
- [/] **Multi-Tenant Schema Migration**: Motor de consistencia de datos aislados — TenantDBFactory implementada (HU 8.1).
- [x] **Refactorización Quirúrgica de Persistencia**: De-fragmentación de StorageManager para cumplimiento de Regla de Masa (HU 8.2).
- [ ] **Intelligence Terminal UI**: Estandarización de componentes Premium Dark (HU 9.1).

**Dependencias**: Requiere SSOT 100% SQLite (✅ completado) y server.py modular (✅ completado).

---

### 🧠 V2 (Vector de Inteligencia) — PLANIFICADO (Dominios 02 y 03)
**Objetivo**: Optimización de Alpha y detección de regímenes de mercado multi-escalares.

- [ ] **Multi-Scale Regime Vectorizer**: Unificación de temporalidades para decisión coherente (HU 2.1 - Base Vector V2).
- [ ] **Contextual Alpha Scoring**: Motor de puntuación dinámica ponderada y dashboard Alpha Radar (HU 3.1).
- [ ] **Dynamic Alpha Thresholding**: Mecanismo de defensa proactiva y auto-ajuste de umbrales según equidad (HU 3.5).
- [ ] **Shadow Reality Engine (F-001)**: Inyección de penalizaciones reales (Latencia/Slippage) para fidelidad crítica (HU 6.1).
- [ ] **Confidence Threshold Optimization**: Ajuste dinámico de umbrales por desempeño histórico (HU 7.1).

---

### 👁️ V3 (Vector de Dominio Sensorial) — PLANIFICADO (Dominios 04 y 10)
**Objetivo**: Establecer la supremacía analítica mediante la detección de huella institucional y meta-aprendizaje de infraestructura.

- [ ] **Safety Governance**: Implementación de Unidades R y Veto granular (Dominio 04).
- [ ] **Exposure & Drawdown Monitor**: Supervisión de riesgo multi-tenant en tiempo real (HU 4.5).
- [ ] **Anomaly Sentinel**: Detección de cisnes negros y antifragilidad (HU 4.6).
- [ ] **Institutional Footprint**: Detección avanzada de huellas institucionales y zonas de liquidez (HU 3.2).
- [ ] **Multi-Market Correlation**: Scanner de confluencia inter-mercado (HU 3.3).
- [ ] **Depredación de Contexto**: Scanner de divergencia inter-mercado para validación de fuerza de régimen (HU 2.2).
- [ ] **Ejecución Depredadora (FIX)**: Conectividad FIX de alta fidelidad y control adaptativo de slippage (HU 5.1 & HU 5.2).
- [ ] **The Pulse (Advanced Feedback)**: Lazo de retroalimentación de infraestructura avanzado para veto técnico (HU 5.3 final).
- [ ] **Coherence Drift Monitoring**: Detección de divergencia entre modelo y ejecución en vivo (HU 6.3).
- [ ] **Autonomous Heartbeat & Self-Healing**: Monitoreo vital y auto-recuperación (HU 10.1).
- [ ] **Infrastructure Resiliency**: Integración de métricas de salud y auto-curación (HU 10.2).

---

### 🌐 EXPANSIÓN DE EJECUCIÓN (Dominio 05)
- [ ] **Capa Institutional (FIX API)**: Conexión directa vía FIX para baja latencia en brokers institucionales (Dominio 05).

> [!NOTE]
> El historial completo de hitos completados ha sido migrado a [SYSTEM_LEDGER.md](docs/SYSTEM_LEDGER.md).

