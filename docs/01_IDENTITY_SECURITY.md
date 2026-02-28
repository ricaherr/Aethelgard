# Dominio 01: IDENTITY_SECURITY (SaaS, Auth, Isolation)

## 🎯 Propósito
Garantizar la integridad, privacidad y seguridad del ecosistema Aethelgard mediante protocolos de autenticación de nivel bancario y un aislamiento total de datos (Multitenancy).

## 🚀 Componentes Críticos
*   **Auth Gateway**: Middleware centralizado con protección JWT.
*   **Tenant Isolation Protocol**: Factoría de bases de datos que garantiza que el `tenant_id` sea inyectado en cada consulta.
*   **Membership Engine**: Control de acceso granular basado en niveles (Basic, Pro, Institutional).

## 🖥️ UI/UX REPRESENTATION
*   **Auth Terminal**: Interfaz de acceso "Premium Dark" con visualización de handshake técnico.
*   **Tenant Badge**: Indicador persistente en el header con el `tenant_id` activo y estado de cifrado de la sesión.
*   **Membership Shield**: Menú de perfil que muestra las capacidades desbloqueadas según el rango del usuario.

## 📈 Roadmap del Dominio
- [x] Implementación de JWT y rotación de secretos.
- [x] Despliegue de esquemas SQLite aislados.
- [ ] Lógica de filtrado de módulos por suscripción.
