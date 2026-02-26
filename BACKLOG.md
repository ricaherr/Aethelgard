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
* **HU 3.1: Detector de Absorción Institucional**: Algoritmo para identificar zonas de alta liquidez donde el precio es retenido/absorbido por órdenes iceberg o muros institucionales. (Anteriormente 4.1)

## 04_RISK_GOVERNANCE (Unidades R, Safety Governor, Veto)
* *(Sin tareas asignadas actualmente)*

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
