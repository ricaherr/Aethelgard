# AETHELGARD: MASTER BACKLOG

"ESTÁNDAR DE EDICIÓN: Este documento se rige por una jerarquía de 10 Dominios Críticos. Toda nueva tarea o Historia de Usuario (HU) debe ser numerada según su dominio (ej. Tarea 4.1 para Riesgo). No se permiten cambios en esta nomenclatura para garantizar la trazabilidad del sistema."

## 🛠️ ESTÁNDAR TÉCNICO DE CONSTRUCCIÓN
1. **Backend: La Fortaleza Asíncrona**
   * **Principio de Aislamiento (Multitenancy)**: El `tenant_id` es el átomo central. Ninguna función de base de datos o lógica de negocio puede ejecutarse sin la validación del contexto del usuario.
   * **Agnosticismo de Datos**: El Core Brain no debe conocer detalles del broker (MT5/FIX). Debe trabajar solo con Unidades R y estructuras normalizadas.
   * **Rigor de Tipado**: Uso estricto de Pydantic para esquemas y `Decimal` para cálculos financieros. Prohibido el uso de `float` en lógica de dinero.
   * **Feedback Inmediato**: Cada acción del backend debe emitir un evento vía WebSocket, incluso si es un fallo, para que la UI "sienta" el latido del sistema.

2. **Frontend: La Terminal de Inteligencia**
   * **Estética "Intelligence Terminal"**: Prohibido el uso de componentes de librerías comunes (como MUI o Bootstrap estándar) sin ser personalizados al estilo Bloomberg-Dark (#050505, acentos cian/neón).
   * **Densidad de Información**: Diseñar para el experto. La UI debe mostrar datos de alta fidelidad sin saturar, usando transparencias y capas (Glassmorphism).
   * **Micro-animaciones Funcionales**: Los cambios de estado no son instantáneos; deben "pulsar" o "deslizarse". La UI debe parecer un organismo vivo, no una página web estática.
   * **Estado Centralizado en el Servidor**: El frontend es "tonto". Solo renderiza lo que el cerebro (Backend) le dice. La lógica de trading nunca reside en React.

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
* **HU 1.1: Auth Gateway & JWT Protection** `[DEV]`
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
* **HU 2.1: Multi-Scale Regime Vectorizer**
    * **Prioridad**: Alta (Vector V2 - Inteligencia)
    * **Descripción**: Desarrollo del motor que unifica la lectura de regímenes en múltiples temporalidades para una decisión coherente.
    * **🖥️ UI Representation**: Widget "Fractal Context Manager" con visualización de alineación de tendencias.
* **HU 2.2: Inter-Market Divergence Scanner**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Implementación del scanner de correlación inter-mercado para validación de fuerza de régimen.
    * **🖥️ UI Representation**: Matriz de correlación dinámica con alertas de divergencia "Alpha-Sync".
* **HU 2.3: Contextual Memory Calibration**
    * **Prioridad**: Baja (Vector V2)
    * **Descripción**: Lógica de lookback adaptativo para ajustar la profundidad del análisis según el ruido del mercado.
    * **🖥️ UI Representation**: Slider de "Profundidad Cognitiva" que muestra cuánta historia está procesando el cerebro en tiempo real.

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
* **HU 5.1: High-Fidelity FIX Connector Core**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Desarrollo de la capa de transporte FIX basada en QuickFIX para conectividad directa con Prime Brokers.
    * **🖥️ UI Representation**: Terminal de telemetría FIX con visualización de latencia ida y vuelta (RTT).
* **HU 5.2: Adaptive Slippage Controller**
    * **Prioridad**: Alta (Vector V3)
    * **Descripción**: Implementación del monitor de desviación de ejecución (Slippage) con integración en la lógica de riesgo.
    * **🖥️ UI Representation**: Badge de "Ejecución Eficiente %" en cada trade cerrado dentro del historial.
* **HU 5.3: Infrastructure Feedback Loop (The Pulse)**
    * **Prioridad**: Media (Vector V1 - Conexión básica / V3 - Feedback avanzado)
    * **Descripción**: Sistema de telemetría que informa al cerebro sobre el estado de los recursos y la red para decisiones de veto técnico.
    * **🖥️ UI Representation**: Widget de "System Vital Signs" con métricas de salud técnica y red.

## 06_PORTFOLIO_INTELLIGENCE (Shadow, Performance)
* **HU 6.1: Shadow Reality Engine (Penalty Injector)**
    * **Prioridad**: Alta (Vector V2 - Inteligencia)
    * **Descripción**: Desarrollo del motor de ajuste que inyecta latencia y slippage real en el rendimiento de estrategias Shadow (Lineamiento F-001).
    * **🖥️ UI Representation**: Gráfico de equity "Shadow vs Theory" con desglose de pips perdidos por ineficiencia.
* **HU 6.2: Multi-Tenant Strategy Ranker**
    * **Prioridad**: Media (Vector V1 - SaaS)
    * **Descripción**: Sistema de clasificación darwinista para organizar estrategias por rendimiento ajustado al riesgo para cada usuario.
    * **🖥️ UI Representation**: Dashboard "Strategy Darwinism" con rankings dinámicos y estados de cuarentena.
* **HU 6.3: Coherence Drift Monitor**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Algoritmo de detección de divergencia entre el comportamiento esperado del modelo y la ejecución en vivo.
    * **🖥️ UI Representation**: Medidor de "Coherencia de Modelo" con alertas visuales de deriva técnica.

## 07_ADAPTIVE_LEARNING (EdgeTuner, Feedback Loops)
* **HU 7.1: Confidence Threshold Optimizer**
    * **Prioridad**: Media (Vector V2)
    * **Descripción**: Optimización dinámica de umbrales de entrada basada en el desempeño histórico reciente.
    * **🖥️ UI**: Visualizador de "Curva de Exigencia Algorítmica".

## 08_DATA_SOVEREIGNTY (SSOT, Persistence)
* **HU 8.1: Multi-Tenant Schema Migrator** `[DONE]`
    * **Prioridad**: Alta (Vector V1)
    * **Descripción**: Motor de gestión de esquemas SQLite aislados para consistencia multi-usuario. Terminada en ETI SAAS-BACKBONE-2026-001.
    * **🖥️ UI**: Indicador de "Sync Status" de base de datos.
* **HU 8.2: De-fragmentación de StorageManager** `[TODO]`
    * **Prioridad**: CRÍTICA
    * **Descripción**: Dividir el archivo de 1,369 LOC en repositorios modulares por dominio.
    * **🖥️ UI**: Indicador de "Persistence Health" en dashboard técnico.

## 09_INSTITUTIONAL_INTERFACE (UI/UX, Terminal)
* **HU 9.1: Component Library "Intelligence Terminal"**
    * **Prioridad**: Alta (Vector V1)
    * **Descripción**: Estandarización de componentes visuales bajo la estética institucional Premium Dark.
    * **🖥️ UI**: Terminal centralizada con componentes reactivos de alta densidad.

## 10_INFRASTRUCTURE_RESILIENCY (Health, Self-Healing)
* **HU 10.1: Autonomous Heartbeat & Self-Healing**
    * **Prioridad**: Media (Vector V3)
    * **Descripción**: Sistema de monitoreo de signos vitales y auto-recuperación de servicios.
    * **🖥️ UI**: Widget de "Status Vital" con log de eventos técnicos.
* **HU 10.2: Meta-Aprendizaje de Infraestructura**: Registro y análisis de latencia y slippage real como variables críticas de decisión en el motor de ejecución. (Anteriormente 4.2)
