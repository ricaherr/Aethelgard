# AETHELGARD: MASTER BACKLOG

## 🌐 ÉPICA 01: Infraestructura SaaS & Multi-Tenancy
**ID**: EP-SaaS | **Alineación**: ROADMAP Item 1
**Descripción**: Evolucionar el sistema de un solo usuario a una arquitectura multi-tenant.

* **HU 1.1: Aislamiento de Persistencia**: Implementar lógica de conexión dinámica para que cada tenant tenga su propia base de datos SQLite (o esquema aislado). 
    * *Nota del CTO*: Requiere eliminar primero los JSONs de configuración para que el aislamiento sea efectivo.
* **HU 1.2: Gateway de Autenticación**: Refactorizar `server.py` para incluir middleware de validación de JWT por perfil de usuario.

## ⚡ ÉPICA 02: Conectividad FIX Institutional
**ID**: EP-FIX | **Alineación**: ROADMAP Item 2
**Descripción**: Implementar la capa de baja latencia para brokers institucionales.

* **HU 2.1: Abstracción de FIX Engine**: Crear `connectors/fix_connector.py` basado en QuickFIX.
* **HU 2.2: Normalización de Mensajes FIX**: Mapear el protocolo FIX a las entidades de dominio de Aethelgard.

## 🛠️ ÉPICA 03: Consolidación Estructural (Habilitador Técnico)
**ID**: EP-TECH | **Prioridad**: ALTA
**Descripción**: Tareas necesarias para que las Épicas 01 y 02 no degraden el sistema.

* **HU 3.1: Segmentación del API Gateway**: Dividir `server.py` (99KB) para permitir que la lógica SaaS sea escalable.
* **HU 3.2: Unificación de Verdad (SSOT)**: Migrar `dynamic_params.json` a la DB para que los perfiles SaaS puedan ser editados en tiempo real.