# AETHELGARD: MASTER BACKLOG

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

## 🌐 ÉPICA 01: Infraestructura SaaS & Multi-Tenancy
**ID**: EP-SaaS | **Alineación**: ROADMAP FASE 1
**Descripción**: Evolucionar el sistema de un solo usuario a una arquitectura multi-tenant.

* **HU 1.1: Aislamiento de Persistencia** `[TODO]`: Implementar `TenantDBFactory` para que cada tenant tenga su propia base de datos SQLite.
* **HU 1.2: Gateway de Autenticación** `[TODO]`: Implementar middleware de validación JWT por perfil de usuario.

## ⚡ ÉPICA 02: Conectividad FIX Institutional
**ID**: EP-FIX | **Alineación**: ROADMAP Expansión Comercial
**Descripción**: Implementar la capa de baja latencia para brokers institucionales.

* **HU 2.1: Abstracción de FIX Engine**: Crear `connectors/fix_connector.py` basado en QuickFIX.
* **HU 2.2: Normalización de Mensajes FIX**: Mapear el protocolo FIX a las entidades de dominio de Aethelgard.

## 👁️ ÉPICA 04: Advanced Sensory Engine
**ID**: EP-SENSE | **Alineación**: ROADMAP FASE 4
**Descripción**: Desarrollo de capacidades de detección micro-estructural y conciencia infraestructural.

* **HU 4.1: Detector de Absorción Institucional**: Algoritmo para identificar zonas de alta liquidez donde el precio es retenido/absorbido por órdenes iceberg o muros institucionales.
* **HU 4.2: Meta-Aprendizaje de Infraestructura**: Registro y análisis de latencia y slippage real como variables críticas de decisión en el motor de ejecución.
* **HU 4.3: Conciencia de Correlación Inter-Mercado**: Scanner especializado que detecta divergencias en tiempo real entre activos altamente correlacionados (ej. EURUSD vs DXY).