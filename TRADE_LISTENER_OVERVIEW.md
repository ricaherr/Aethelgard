# 📊 DISEÑO: TradeClosureListener - Visión General

## Sistema Autónomo Completo

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    AETHELGARD FEEDBACK LOOP AUTÓNOMO                    │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│ BROKER (Any: MT5, NT8, Polygon, etc.)                                   │
│                                                                          │
│  Closes Trade EURUSD: entry=1.0850, exit=1.0840, profit=-100 (LOSS)    │
└────────────────────────────┬──────────────────────────────────────────────┘
                             │
                             │ (1) Raw broker data
                             │
┌────────────────────────────▼──────────────────────────────────────────────┐
│ ADAPTER (connectors/mt5_event_adapter.py)                                │
│                                                                          │
│ Converts MT5-specific format → BrokerTradeClosedEvent (standard)        │
│                                                                          │
│ MT5 Data ─────────────────────────► BrokerTradeClosedEvent             │
│ ticket=123456789               ticket="123456789"                       │
│ symbol=EURUSD                  symbol="EURUSD"                          │
│ profit=-100.0                  profit_loss=-100.0                       │
│ comment="SL"                   exit_reason="stop_loss_hit"              │
│                                result=TradeResult.LOSS                  │
│                                broker_id="MT5"                          │
└────────────────────────────┬──────────────────────────────────────────────┘
                             │
                             │ (2) Standardized BrokerEvent
                             │
┌────────────────────────────▼──────────────────────────────────────────────┐
│ TradeClosureListener (core_brain/trade_closure_listener.py)              │
│                                                                          │
│ async handle_trade_closed_event(event)                                  │
│                                                                          │
│ ├─ [STEP 1] Save to DB with retry logic                                │
│ │   └─ storage.save_trade_result(trade_data)                           │
│ │      if DB locked: wait 0.5s, retry                                  │
│ │      if DB locked: wait 1.0s, retry                                  │
│ │      if DB locked: wait 1.5s, fail if max_retries exceeded           │
│ │                                                                       │
│ │   LOG: [TRADE_CLOSED] Symbol: EURUSD | Result: LOSS | ...           │
│ │                                                                       │
│ ├─ [STEP 2] Update RiskManager                                         │
│ │   └─ risk_manager.record_trade_result(is_win=False, pnl=-100)       │
│ │      consecutive_losses = 1                                          │
│ │                                                                       │
│ │   (if consecutive_losses >= 3):                                      │
│ │      LOG: [LOCKDOWN] RiskManager entered LOCKDOWN                   │
│ │                                                                       │
│ ├─ [STEP 3] Trigger Tuner (every 5 trades or on lockdown)             │
│ │   └─ edge_tuner.adjust_parameters()                                  │
│ │      - Read recent trades                                            │
│ │      - Calculate win_rate                                            │
│ │      - if low_win_rate: adjustment_factor = 1.5-1.7                 │
│ │      - Update dynamic_params.json                                    │
│ │                                                                       │
│ │   LOG: [TUNER] Parameters adjusted: trigger=low_win_rate             │
│ │                                                                       │
│ └─ [STEP 4] Metrics (for monitoring)                                   │
│    └─ trades_processed++, trades_saved++                               │
└────────────────────────────┬──────────────────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
        ▼                    ▼                    ▼
    ┌────────┐          ┌──────────┐        ┌─────────┐
    │ Storage│          │RiskMgr   │        │EdgeTuner│
    │ (BD)   │          │(Lockdown)│        │(Params) │
    └────────┘          └──────────┘        └─────────┘
```

## Características del Diseño

### 1. **Agnosticismo del Broker**

```python
# MT5 connector generates:
event = BrokerTradeClosedEvent(
    ticket="123",
    symbol="EURUSD",
    ...
    broker_id="MT5"
)

# NT8 connector generates (same interface):
event = BrokerTradeClosedEvent(
    ticket="456",
    symbol="EURUSD",
    ...
    broker_id="NT8"
)

# Listener doesn't care which broker - same code path!
await listener.handle_trade_closed_event(event)
```

### 2. **Retry Logic en BD**

```
Intento 1: save_trade_result()
           └─ DB Locked
              └─ Wait 0.5s

Intento 2: save_trade_result()
           └─ DB Locked
              └─ Wait 1.0s

Intento 3: save_trade_result()
           └─ DB Locked
              └─ Wait 1.5s
                 └─ FALLA: Alert + Log Error

GARANTÍA: Si DB se desbloqueó en algún intento, se guarda.
          No se pierden registros por locks temporales.
```

### 3. **Logging de Auditoría**

```
[TRADE_CLOSED] Symbol: EURUSD | Ticket: 123456789 | Result: LOSS | PnL: -100.00 | ExitReason: stop_loss_hit | Broker: MT5

[LOCKDOWN] RiskManager entered LOCKDOWN: consecutive_losses=3

[TUNER] Parameters adjusted: trigger=consecutive_losses | adjustment_factor=1.7

[DB] DB locked (attempt 1/3). Retrying in 0.5s... | Ticket: 123456789

[ERROR] Failed to save trade 123456789 after 3 retries: database is locked
```

## Flujo de Integración

### En MainOrchestrator.__init__:

```python
# Crear Listener con inyección de dependencias
self.trade_listener = TradeClosureListener(
    storage=self.storage,
    risk_manager=self.risk_manager,
    edge_tuner=self.edge_tuner,
    max_retries=3,
    retry_backoff=0.5
)
```

### Cuando MT5Connector cierra una operación:

```python
# En connectors/mt5_connector.py
trade_closed_event = adapt_mt5_trade_closed_to_event(mt5_raw_data)

# Pass to listener
await orchestrator.trade_listener.handle_trade_closed_event(
    BrokerEvent.from_trade_closed(trade_closed_event)
)
```

### Monitoreo:

```python
# En dashboard o logs periódicos
metrics = self.trade_listener.get_metrics()
print(f"""
Trades Processed: {metrics['trades_processed']}
Trades Saved: {metrics['trades_saved']}
Trades Failed: {metrics['trades_failed']}
Success Rate: {metrics['success_rate']:.1%}
Tuner Adjustments: {metrics['tuner_adjustments']}
""")
```

## Archivos Creados

| Archivo | Propósito |
|---------|-----------|
| `models/broker_event.py` | Interfaz estándar (BrokerTradeClosedEvent) |
| `core_brain/trade_closure_listener.py` | Listener principal con retry logic |
| `connectors/mt5_event_adapter.py` | Ejemplo: MT5 → evento estándar |
| `TRADE_CLOSURE_LISTENER_DESIGN.md` | Documentación completa |

## Principios Seguidos

✅ **Inyección de Dependencias**: Todos los componentes inyectados  
✅ **Agnosticismo**: Broker-agnostic via interfaz estándar  
✅ **Resiliencia**: Retry logic con exponential backoff  
✅ **Auditoría**: Logging detallado de cada evento  
✅ **Testing**: Fácil de testear (mock events)  
✅ **SSOT**: Configuración centralizada  

## Próximo Paso

✅ Diseño completado y documentado  
→ **Integración en MainOrchestrator** (cuando aprobado)

