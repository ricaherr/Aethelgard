# Dominio 04: DATA_SOVEREIGNTY_INFRA (Inmutabilidad y Resiliencia)

**ID de Transacción:** JOB-04-DATA-INFRA-SOVEREIGNTY-2026-04-10
**Fecha:** 10 de abril de 2026

## 🎯 Propósito
Garantizar la inmutabilidad absoluta de la información operativa y la disponibilidad perpetua del sistema. Este dominio fusiona nuestra arquitectura de persistencia de datos (Multi-tenant SSOT) con el motor de auto-sanación de infraestructura, asegurando que un fallo local jamás comprometa el núcleo global ni cruce las fronteras entre entornos simulados y reales.

---

## 🏛️ Dogma SSOT & Convenciones Obligatorias (ARCH-SSOT-2026-006)
Para asegurar que los datos sean el activo más fiable, la base de datos actúa como la **Single Source of Truth (SSOT)**. No existen variables in-memory sin su espejo persistente. 

**Reglas de Nomenclatura y Aislamiento:**
*   `asset`: Todo instrumento financiero se llama así (prohibido usar *symbol* o *instrument*).
*   `sys_*`: Tablas de Capa 0 (Global/Sistema). Representan la verdad universal (ej. `sys_market_pulse`, `sys_trades`). Read-only para los tenants.
*   `usr_*`: Tablas de Capa 1 (Local/Tenant). Aíslan la gestión propia de cada usuario (ej. `usr_trades`, `usr_assets_cfg`). Full CRUD para el tenant correspondiente.
*   **Separación Absoluta:** Los datos de ejecución `SHADOW` y `BACKTEST` **jamás** se mezclan con `LIVE`. El motor rechaza (vía Trigger SQL) cualquier intento de insertar un trade `LIVE` en `sys_trades` o escenarios ficticios en `usr_trades`.

---

## 🗄️ Arquitectura de Persistencia Agnóstica
El `StorageManager` está diseñado para operar de forma agnóstica respecto al motor de persistencia, facilitando la viabilidad tanto de un SQLite local como de migraciones futuras a PostgreSQL/MySQL.

*   **SQLite Anti-Lock:** Para entornos SQLite, el adapter implementa mitigaciones como colas selectivas para métricas de alta frecuencia, políticas *busy_timeout*, y uso estricto del modo WAL (Write-Ahead Logging). Esto previene que concurrencia masiva (como telemetría o ticks en milisegundos) bloquee la ejecución de órdenes críticas.

---

## 🔐 Protocolo Multi-tenant 

El sistema garantiza soberanía de datos aislando físicamente a los usuarios.

*   **Aislamiento Físico:** Cada inquilino recibe su propio almacén de datos (ej. `data_vault/tenants/{tenant_id}/aethelgard.db`), orquestado al instante de su alta. No existen columnas `tenant_id` en las tablas `usr_*` mezclando realidades.
*   **Provisioning Idempotente:** El sistema utiliza una plantilla maestra (`usr_template.db`) para instanciar automáticamente cualquier nuevo tenant garantizando uniformidad funcional desde el primer segundo. La instanciación solo ocurre si la BD no existe.

### Ciclo de Migraciones
Toda la lógica estructural evoluciona mediante `run_migrations()`, asumiendo una política estrictamente aditiva (no destructiva). 

**Procedimiento de 3 Pasos (Ejemplo: Añadiendo Columna P&L):**
1.  **Documentador**: Se describe la alteración de esquema (Ej. `ALTER TABLE usr_trades ADD COLUMN pnl REAL`).
2.  **Runtime**: El motor de migraciones aplica la misma instrucción *SQL* en la Capa 0 y, si corresponde, itera sobre todos los tenants de la Capa 1 para replicarla.
3.  **Acceso**: La lógica en el Service actualiza sus *queries* para abarcar el nuevo esquema, respetando siempre los valores *default* preexistentes.

---

## ⚕️ Cerebro Inmunológico: ResilienceManager y Auto-healing

La infraestructura técnica adopta el principio de **Degradación Elegante**. Un fallo ligero (un broker caído o un socket intermitente) se procesa para evitar un efecto dominó que tumbe a todo el sistema.

*   **Manejo Granular (Niveles L0 a L3)**: 
    *   **L0 (ASSET)**: Mitigación a nivel de activo. Ej. Si Spread > 300% en EURUSD, se silencia (`MUTE`) momentáneamente el activo, sin alertar al resto del portafolio.
    *   **L1 (STRATEGY)**: Si ocurren tres rechazos consecutivos, se lanza `QUARANTINE` a una estrategia específica.
    *   **L2 (SERVICE)**: Pérdida o descongelamiento de conexión (socket timeout). Inicia procedimiento `SELF_HEAL` reiniciando solo ese hilo o conector.
    *   **L3 (GLOBAL)**: Evento de proporciones orgánicas. Dispara un `LOCKDOWN` apagando toda ejecución e induciendo a breakeven las posiciones.
*   **Contrato ResilienceInterface**: Los monitores comunican obligatoriamente reportes uniformes (como `EdgeEventReport`) hacia el `ResilienceManager`, el cual actualiza el la postura del sistema (`NORMAL`, `CAUTION`, `DEGRADED`, `STRESSED`).
*   **Agnosticismo de Broker**: La continuidad no depende de presuponer MT5 como única fuente activa. Si un proveedor alternativo inyecta datos recientes (ej. cTrader o Polygon), la salud global sigue certificándose como óptima.