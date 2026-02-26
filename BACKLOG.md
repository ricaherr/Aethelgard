# AETHELGARD: MASTER BACKLOG

"ESTÁNDAR DE EDICIÓN: Este documento se rige por una jerarquía de 10 Dominios Críticos. Toda nueva tarea o Historia de Usuario (HU) debe ser numerada según su dominio (ej. Tarea 4.1 para Riesgo). No se permiten cambios en esta nomenclatura para garantizar la trazabilidad del sistema."

> [!NOTE]
> **Convenciones de Estado de HU:**
> | Estado | Significado |
> |---|---|
> | *(vacío)* | HU no seleccionada para ningún Sprint |
> | `[TODO]` | Seleccionada para el Sprint activo |
> | `[DEV]` | En desarrollo activo |
> | `[QA]` | En fase de pruebas/validación |
> | `[DONE]` | Completada — eliminar del backlog y actualizar SPRINT |

---

## 01_IDENTITY_SECURITY (SaaS, Auth, Isolation)
* **HU 1.1: Auth Gateway & JWT Protection** `[TODO]`
    * **Qué**: Implementar el middleware de seguridad para todas las rutas del API.
    * **Para qué**: Garantizar que solo usuarios autenticados accedan al cerebro de Aethelgard.
    * **🖥️ UI Representation**: Pantalla de Login (Premium Dark) con feedback de error en tiempo real. Redirección automática al dashboard tras handshake exitoso.
* **HU 1.2: Tenant Isolation Protocol (Multi-tenancy)** `[TODO]`
    * **Qué**: Configurar el TenantDBFactory para aislar los datos por cliente.
    * **Para qué**: Evitar fugas de datos entre usuarios (Principio de Aislamiento).
    * **🖥️ UI Representation**: Badge persistente en el header que indique Tenant_ID activo y estado de la conexión a su base de datos privada.
* **HU 1.3: User Role & Membership Level** `[TODO]`
    * **Qué**: Definir jerarquías de acceso (Admin, Pro, Basic).
    * **Para qué**: Comercialización SaaS basada en niveles de membresía.
    * **🖥️ UI Representation**: Menú de perfil donde el usuario vea su rango actual y las funcionalidades bloqueadas/desbloqueadas según su plan.

## 02_CONTEXT_INTELLIGENCE (Regime, Multi-Scale)
* **HU 2.1: Conciencia de Correlación Inter-Mercado**: Scanner especializado que detecta divergencias en tiempo real entre activos altamente correlacionados (ej. EURUSD vs DXY). (Anteriormente 4.3)

## 03_ALPHA_GENERATION (Signal Factory, Indicators)
* **HU 3.1: Contextual Alpha Scoring System**
    * **Prioridad**: Alta (Vector V2)
    * **Descripción**: Desarrollo del motor de puntuación dinámica ponderada por el Regime Classifier y métricas del Shadow Portfolio.
    * **🖥️ UI Representation**: Dashboard "Alpha Radar" con medidores de confianza (0-100%) y etiquetas de régimen activo.
* **HU 3.2: Institutional Footprint Core**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Lógica de detección de huella institucional basada en micro-estructura de precios y volumen.
    * **🖥️ UI Representation**: Superposición visual de "Liquidity Zones" y clústeres de volumen en el visor de estrategias.
* **HU 3.3: Multi-Market Alpha Correlator**
    * **Prioridad**: Baja (Vector V3)
    * **Descripción**: Scanner de confluencia inter-mercado para validación cruzada de señales de alta fidelidad.
    * **🖥️ UI Representation**: Widget de "Correlación Sistémica" con indicadores de fuerza y dirección multi-activo.
* **HU 3.4: Signal Post-Mortem Analytics**
    * **Prioridad**: Media (Vector V2)
    * **Descripción**: Motor de auditoría post-trade que vincula resultados con datos de micro-estructura para alimentar el Meta-Aprendizaje.
    * **🖥️ UI Representation**: Vista "Post-Mortem" con visualización de velas de tick y marcadores de anomalías detectadas.
* **HU 3.5: Dynamic Alpha Thresholding**
    * **Prioridad**: Alta (Vector V2)
    * **Descripción**: Lógica de auto-ajuste de barreras de entrada basada en la equidad de la cuenta y el régimen de volatilidad.
    * **🖥️ UI Representation**: Dial de "Exigencia Algorítmica" en el header, mostrando el umbral de entrada activo.

## 04_RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)
* **HU 4.4: Sovereignty Gateway Manager** `[TODO]`
    * **Prioridad**: Alta (Dependencia V1)
    * **Descripción**: Desarrollo del motor de reglas para la matriz de permisos de autonomía granular (Mercados/Componentes).
    * **🖥️ UI Representation**: Panel de control "Master Veto" con indicadores de estado (Autónomo/Manual) y Toggles de seguridad institucional.
* **HU 4.5: Drawdown & Exposure Monitor (Multi-tenant)**
    * **Prioridad**: Media
    * **Descripción**: Sistema de monitoreo de riesgo agregado basado en Unidades R para entornos SaaS, garantizando que el riesgo de un cliente no desborde sus límites.
    * **🖥️ UI Representation**: Dashboard de "Heatmap de Exposición" con alertas visuales de proximidad al Hard Drawdown.
* **HU 4.6: Anomaly Sentinel (Antifragility Engine)**
    * **Prioridad**: Baja (Fase 4)
    * **Descripción**: Monitor de eventos de baja probabilidad (Cisnes Negros) para activar protocolos de defensa o captura de volatilidad extrema.
    * **🖥️ UI Representation**: Consola de "Thought" con tag [ANOMALY_DETECTED] y sugerencias proactivas de intervención.

## 05_UNIVERSAL_EXECUTION (EMS, Conectores FIX)
* **HU 5.1: Abstracción de FIX Engine**: Crear `connectors/fix_connector.py` basado en QuickFIX. (Anteriormente 2.1)
* **HU 5.2: Normalización de Mensajes FIX**: Mapear el protocolo FIX a las entidades de dominio de Aethelgard. (Anteriormente 2.2)

## 06_PORTFOLIO_INTELLIGENCE (Shadow, Performance)
* *(Sin tareas asignadas actualmente)*

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
* *(Sin tareas asignadas actualmente)*

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)
* *(Tareas integradas en 01_IDENTITY_SECURITY para esta fase inicial)*

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)
* *(Sin tareas asignadas actualmente)*

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.1: Meta-Aprendizaje de Infraestructura**: Registro y análisis de latencia y slippage real como variables críticas de decisión en el motor de ejecución. (Anteriormente 4.2)
