# Dominio 05: IDENTITY_SECURITY (Gatekeeper y Aislamiento SaaS)

**ID de Transacción:** JOB-05-IDENTITY-SECURITY-SaaS-2026-04-10
**Fecha:** 10 de abril de 2026

## 🎯 Propósito
Este dominio conforma el bastión final del ecosistema Aethelgard. Actuando como la "llave" para los otros cuatro dominios, garantiza que sin una identidad validada matemáticamente, el Cerebro Adaptativo no procesa, el Ejecutor no dispara y los datos no se exponen. Establece anillos de seguridad concéntricos que blindan el capital y la privacidad de múltiples inversores dentro de una arquitectura SaaS (Multitenancy).

---

## 🛡️ Primer Anillo: Auth Gateway (Gatekeeper)

El middleware de autenticación es el punto de entrada exclusivo. Ninguna solicitud atraviesa hacia la lógica de negocio sin superar este perímetro.

*   **Validación de JWT**: Inspección estricta de firmas mediante secretos criptográficos rotados periódicamente.
*   **Extracción de Identidad**: Desempaquetado del `tenant_id` directamente desde el payload validado, ignorando cualquier identificador que el cliente intente enviar por parámetros o cuerpo de la petición.
*   **Rechazo Explícito**: Tolerancia cero (Fail-Fast) arrojando excepciones inmediatas ante tokens expirados, malformados o revocados.

---

## 🧱 Segundo Anillo: Blindaje Multi-tenant (Soberanía de Datos)

El `tenant_id` seguro extraído por el Auth Gateway se convierte en una muralla infranqueable a nivel de infraestructura.

*   **TenantDBFactory**: Factory que intercepta el `tenant_id` para instanciar una conexión *exclusiva* a la base de datos física del inquilino (`data_vault/tenants/{tenant_id}/aethelgard.db`).
*   **Privacidad por Diseño**: Es matemáticamente imposible que una consulta SQL de un usuario alcance o contamine los datos (ej. `usr_trades`) de otro. Incluso si la capa de API fallara, la capa de persistencia está separada por la ruta del archivo en disco.
*   **Invisibilidad Administrativa**: Los operadores del sistema gestionan instancias a través de la Capa 0 (Global), pero no poseen llaves automáticas para descifrar las métricas operativas individuales almacenadas en las BD aisladas de la Capa 1.

---

## ⚖️ Tercer Anillo: RBAC y Membership Shield 

El control de acceso no solo define *quién* entra, sino *qué* capacidades tiene autorizadas.

*   **Jerarquía de Roles (RBAC)**: Distinción estricta mediante decoradores (ej. `@require_admin`, `@require_trader`) que segregan las capacidades de configuración global frente a la operación de cuentas. Un Admin gestiona infraestructura y facturación; un Trader gestiona su propio riesgo.
*   **Membership Engine (Tiering)**: Control de capacidad operativa. Funciones avanzadas del *Adaptive Brain* (Dominio 01) o tipos de estrategias algorítmicas se desbloquean dependiendo del nivel de suscripción (Basic, Premium, Institutional).

---

## 🔍 Cuarto Anillo: Audit & Compliance

El sistema audita sus propias barreras continuamente para asegurar cumplimiento institucional continuo.

*   **Tenant Isolation Scanner**: Un bot de cumplimiento estático (`scripts/tenant_isolation_audit.py`) que audita en tiempo real que el 100% de los endpoints protegidos inyecten el factor de aislamiento de la BD y jamás usen métodos genéricos de `StorageManager` compartidos.
*   **Registro de Auditoría (sys_audit_logs)**: Inmutabilidad absoluta para eventos críticos (creación de usuarios, cambios de roles, soft-deletes). Todo evento queda sellado con un `trace_id` en la base global (Capa 0).

---

## 🚨 Manual de Respuesta a Brechas (Emergency Protocol)

En caso de sospecha de compromiso de credenciales o brecha perimetral, Aethelgard reacciona sin dudar:

1.  **Revocación Inmediata de Tokens**: Invalidación del secreto JWT activo, forzando la desconexión de todas las sesiones.
2.  **Soft-Delete / Quarantine de Cuenta**: Modificación del estado del usuario a `SUSPENDED` en `sys_users`, lo que revoca automáticamente el paso a través del Auth Gateway.
3.  **Veto de Ejecución**: Al perder la validación de identidad, el Executor (Dominio 02) aborta cualquier ciclo del orquestador asociado a ese tenant, induciendo el cierre seguro de operaciones bajo reglas de resiliencia (Dominio 04).

---
**Nota del Documentador:** *La culminación de este dominio asegura que la genialidad del análisis y la precisión de la ejecución operen dentro de una bóveda inviolable. La seguridad no es una característica de Aethelgard; es la plataforma sobre la que el sistema existe.*