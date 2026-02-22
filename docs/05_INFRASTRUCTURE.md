# AETHELGARD: 05 INFRASTRUCTURE

## 🛠️ Núcleo Técnico y Persistencia
Capa de cimientos, servidores y Single Source of Truth (SSOT).

---

### 🗄️ Capa de Datos (Data Vault)
- **StorageManager**: Persistencia segmentada mediante Mixins.
- **SSOT Policy**: Prohibición de archivos JSON volátiles para lógica de negocio.

#### 🌐 Asset Profiles (Universal Trading Foundation)
**Propósito**: Normalización agnóstica de símbolos, permitiendo cálculo de riesgo uniforme a través de todos los instrumentos (Forex, Crypto, Metals).

**Ubicación**: `data_vault/market_db.py` (tabla `asset_profiles`)

**Esquema**:
```sql
CREATE TABLE asset_profiles (
  symbol TEXT PRIMARY KEY,           -- ej: "EURUSD"
  tick_size REAL,                    -- ej: 0.00001 (5 decimales)
  contract_size INTEGER,             -- ej: 100000 (Forex standard)
  lot_step REAL,                     -- ej: 0.01 (miniaturización)
  pip_value REAL,                    -- ej: 10.0 USD/pip
  commission_pct REAL,               -- ej: 0.0002 (0.02%)
  point_value REAL                   -- ej: 100.0 (Forex point = pip)
);
```

**Datos Iniciales Sembrados**:
| Symbol | Tick Size | Contract Size | Lot Step | Uso |
|--------|-----------|---------------|----------|-----|
| EURUSD | 0.00001   | 100000        | 0.01     | Forex Major |
| GBPUSD | 0.00001   | 100000        | 0.01     | Forex Major |
| USDJPY | 0.001     | 100000        | 0.01     | Forex (JPY) |
| GOLD   | 0.01      | 100           | 0.1      | Metal Commodity |
| BTCUSD | 0.01      | 1             | 0.001    | Crypto |

**Lectura en Tiempo Real**:
- `RiskManager.calculate_position_size()` consulta `storage.get_asset_profile(symbol)` cada ejecución.
- Si el símbolo no existe → `AssetNotNormalizedError` (trade bloqueado).
- Fórmula: `Lots = Risk_USD / (SL_Dist * Contract_Size)`

- **Database Self-Healing**: Reparación automática de esquemas en startup.

---

### 🌐 Servicios de Red
- **FastAPI / WebSockets**: Infraestructura asíncrona de alta concurrencia.
- **Orquestador Resiliente**: Bucle de control con reconstrucción de estado tras crashes.
- **API Unified Endpoints**: Interfaz única para UI y servicios externos.

---

### 🏥 Salud y Mantenimiento (Protocolo EDGE Autónomo)
Aethelgard ha evolucionado de un mantenimiento manual PAS a una gestión **EDGE Autónoma** para garantizar operatividad 24/7 sin intervención humana.

#### 🤖 Autonomous Health Service
Un servicio centinela (`core_brain/health_service.py`) supervisa la integridad del sistema:
- **Auto-Auditoría**: Ejecuta validaciones de salud cada hora.
- **Vigía de Recursos**: Monitorea el tamaño de logs y uso de CPU.
- **Propuestas de Gestión**: Detecta problemas y los reporta vía "Thoughts" en la UI, preparando el camino para la auto-reparación autorizada.

#### 📂 Gestión de Logs (Linux Style)
Para evitar archivos masivos que degraden el rendimiento:
- **Base Name**: `logs/main.log`.
- **Rotación Diaria**: Se crea un nuevo archivo cada medianoche (format: `main.log.YYYY-MM-DD`).
- **Retención Estricta**: Mantiene solo los últimos 15 días de logs para optimizar el espacio en disco.
