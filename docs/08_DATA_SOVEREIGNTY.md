# Dominio 08: DATA_SOVEREIGNTY (SSOT, Persistence)

## 🎯 Propósito
Garantizar que la información sea el activo más fiable y protegido del sistema, eliminando redundancias y asegurando la persistencia inmutable bajo el dogma de Single Source of Truth (SSOT).

## ⚠️ Regla de oro: creación y evolución de la DB

*   **La base de datos por tenant se crea UNA SOLA VEZ.** El archivo `data_vault/tenants/{tenant_id}/aethelgard.db` solo se crea cuando no existe (`provision_tenant_db` se invoca únicamente si `not os.path.isfile(db_path)`). No se vuelve a "crear" en cada petición ni en cada arranque.
*   **Las migraciones son solo aditivas.** `run_migrations()` añade columnas o filas faltantes (por ejemplo `ALTER TABLE ... ADD COLUMN`, `INSERT ... WHERE NOT EXISTS`). Nunca se borran datos existentes ni se reemplazan claves de `system_state` que ya tienen valor. Así se preservan operaciones, señales y configuración del usuario.
*   **Nunca sobrescribir datos existentes con defaults.** Si una clave existe en la DB (p. ej. `instruments_config`), no se debe reemplazar por un catálogo por defecto. Solo se siembra cuando la clave falta. Los defaults se usan en memoria para respuestas de API si hay error de lectura, pero no se persisten encima de datos ya guardados.

## 🚀 Componentes Críticos
*   **SSOT Orchestrator**: Garantiza que toda configuración resida exclusivamente en la DB.
*   **Multi-tenant Migrator**: Motor de evolución de esquemas que mantiene la consistencia entre bases de datos de clientes.
*   **Data Vault Architecture**: Estructura de persistencia segmentada para alta velocidad de lectura/escritura.

## 🖥️ UI/UX REPRESENTATION
*   **Sync Status Badge**: Indicador en tiempo real de la integridad y sincronización de la base de datos local vs nube orquestadora.
*   **Schema Evolution Map**: Log visual de migraciones y cambios estructurales aplicados al sistema.

## 📈 Roadmap del Dominio
- [x] Migración total de archivos JSON restantes a DB.
- [x] Implementación de protocolos de auditoría de hash para integridad de datos.
- [ ] Despliegue de redundancia geográfica para el modo SaaS.
