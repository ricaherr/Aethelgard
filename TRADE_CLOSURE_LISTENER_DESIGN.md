# TradeClosureListener - Arquitectura de Diseño

## 🎯 Propósito

Conectar el feedback loop: cuando un broker cierra una operación, el sistema automáticamente:
1. Persiste el resultado en BD
2. Actualiza RiskManager (contador de pérdidas, lockdown)
3. Ajusta parámetros dinámicos (EdgeTuner)
4. Mantiene auditoría completa

## 🏗️ Arquitectura

### Interfaz Estándar (Broker-Agnostic)

```python
# Todas las cuentas de broker adaptan sus eventos a esta estructura:
BrokerTradeClosedEvent(
    ticket: str,              # ID único del trade
    symbol: str,              # EURUSD (normalizado)
    entry_price: float,
    exit_price: float,
    entry_time: datetime,
    exit_time: datetime,
    pips: float,
    profit_loss: float,       # En divisa de cuenta
    result: TradeResult,      # WIN, LOSS, BREAKEVEN
    exit_reason: str,         # "take_profit_hit", "stop_loss_hit", etc.
    broker_id: str,           # "MT5", "NT8", "POLYGON", etc.
    signal_id: str,           # Link a la señal que generó la operación
    metadata: dict            # Datos específicos del broker
)
```

### Ventajas del Diseño

| Aspecto | Beneficio |
|---------|-----------|
| **Agnosticismo** | Cambia de MT5 a NT8 sin tocar el Listener |
| **Extensibilidad** | Nuevo broker = crear adapter que genere BrokerTradeClosedEvent |
| **Testing** | Tests inyectan eventos mock directamente |
| **Auditabilidad** | Todos los eventos pasan por la misma ruta |

## 🔄 Flujo de Procesamiento

```
BrokerEvent (from MT5 connector)
         │
         ▼
TradeClosureListener.handle_trade_closed_event()
         │
         ├─ [1] Save to DB (with retry on lock)
         │       ├─ Attempt 1: save
         │       ├─ DB Locked? Wait 0.5s, retry
         │       ├─ DB Locked? Wait 1.0s, retry
         │       └─ DB Locked? Wait 1.5s, fail if max_retries exceeded
         │
         ├─ [2] Update RiskManager
         │       ├─ record_trade_result(is_win, pnl)
         │       ├─ consecutive_losses++
         │       └─ if consecutive_losses >= 3: LOCKDOWN ACTIVATED
         │
         ├─ [3] Trigger Tuner (every 5 trades or on consecutive_losses >= 3)
         │       ├─ get_recent_trades()
         │       ├─ calculate_stats()
         │       └─ adjust_parameters() if needed
         │
         └─ [4] Audit Log
                 [TRADE_CLOSED] Symbol: EURUSD | Result: LOSS | ExitReason: stop_loss_hit

         ▼
    DB Updated + RiskManager State + Parameters Adjusted
```

## 🛡️ Retry Logic

```python
for attempt in range(max_retries):  # 3 attempts
    try:
        storage.save_trade_result(trade_data)
        return True  # Success
    except DBLockError:
        wait_time = retry_backoff * (attempt + 1)
        # 0.5s, 1.0s, 1.5s exponential backoff
        await asyncio.sleep(wait_time)
        continue
```

**Garantía**: Si la BD está ocupada, reintentos antes de fallar. NO se pierden registros.

## 📊 Logging de Auditoría

```
[TRADE_CLOSED] Symbol: EURUSD | Ticket: 123456 | Result: LOSS | PnL: -100.00 | ExitReason: stop_loss_hit | Broker: MT5

[LOCKDOWN] RiskManager entered LOCKDOWN: consecutive_losses=3

[TUNER] Parameters adjusted: trigger=consecutive_losses | adjustment_factor=1.7

[DB] DB locked (attempt 1/3). Retrying in 0.5s... | Ticket: 123456
```

## 🔌 Integración con MainOrchestrator

**Paso 1**: Crear Listener en MainOrchestrator.__init__
```python
self.trade_listener = TradeClosureListener(
    storage=self.storage,
    risk_manager=self.risk_manager,
    edge_tuner=self.edge_tuner
)
```

**Paso 2**: Pasar eventos al Listener
```python
# Cuando el broker envía un evento:
event = BrokerTradeClosedEvent(...)
await self.trade_listener.handle_trade_closed_event(event)
```

**Paso 3**: Monitoreo de métricas
```python
metrics = self.trade_listener.get_metrics()
print(f"Success Rate: {metrics['success_rate']:.1%}")
```

## 🧪 Testing Strategy

```python
async def test_listener_saves_and_updates_risk():
    # 1. Create temp storage, risk_manager, tuner
    storage = StorageManager(db_path=':memory:')
    risk_mgr = RiskManager(storage=storage, initial_capital=10000)
    tuner = EdgeTuner(storage=storage)
    
    # 2. Create listener
    listener = TradeClosureListener(storage, risk_mgr, tuner)
    
    # 3. Create mock event
    event = BrokerEvent.from_trade_closed(
        BrokerTradeClosedEvent(
            ticket="123",
            symbol="EURUSD",
            ...
            result=TradeResult.LOSS
        )
    )
    
    # 4. Handle event
    await listener.handle_trade_closed_event(event)
    
    # 5. Assert
    assert storage.get_recent_trades(limit=1)[0]['ticket'] == "123"
    assert risk_mgr.consecutive_losses == 1
```

## ⚙️ Configuración

Via `config/trade_closure_listener.json` (Single Source of Truth):
```json
{
  "max_retries": 3,
  "retry_backoff": 0.5,
  "tuner_trigger_frequency": 5,
  "enabled": true
}
```

## 📋 Checklist de Integración

- [ ] TradeClosureListener creado ✅
- [ ] BrokerEvent/BrokerTradeClosedEvent interfaces ✅
- [ ] Retry logic con exponential backoff ✅
- [ ] Logging de auditoría ✅
- [ ] Inyección de dependencias ✅
- [ ] Tests de integración listos
- [ ] Integración en MainOrchestrator (PRÓXIMO)
- [ ] MT5Connector adapter para generar eventos (PRÓXIMO)

---

**Status**: Diseño completado. Listo para integración.
