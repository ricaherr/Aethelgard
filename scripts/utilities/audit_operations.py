#!/usr/bin/env python3
"""
Audit Operations - Comprehensive trade execution quality check (CORRECTED SCHEMA)
Validates: SL/TP presence, volume calculation, timing, signal quality
Uses REAL schema: signals + trade_results tables
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
import json

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager

def audit_operations():
    """Run comprehensive audit of recent trades and active positions"""
    
    print("\n" + "="*100)
    print(" AETHELGARD - AUDIT DE OPERACIONES EJECUTADAS")
    print("="*100)
    
    storage = StorageManager()
    conn = storage._get_conn()
    
    try:
        # 1. OPERACIONES ACTIVAS (EJECUTADAS Y ABIERTAS)
        print("\n" + "="*100)
        print("1. OPERACIONES ACTIVAS (EJECUTADAS - SIN CERRAR):")
        print("="*100)
        
        active_trades = conn.execute("""
            SELECT id, symbol, signal_type, timeframe, price, direction, order_id, 
                   timestamp, metadata
            FROM signals 
            WHERE UPPER(status) = 'EXECUTED'
            AND id NOT IN (SELECT signal_id FROM trade_results WHERE signal_id IS NOT NULL)
            ORDER BY timestamp DESC 
            LIMIT 20
        """).fetchall()
        
        if not active_trades:
            print("\n   NO HAY OPERACIONES ACTIVAS (posiciones abiertas)\n")
        else:
            print(f"\n   TOTAL: {len(active_trades)} operaciones activas\n")
            print(f"{'Signal ID':<38} {'Symbol':<10} {'Type':<8} {'TF':<6} {'Dir':<6} {'Entry':<12} {'Order ID':<15} {'Time'}")
            print("-" * 120)
            
            missing_sl_count = 0
            missing_tp_count = 0
            missing_lots_count = 0
            missing_order_id_count = 0
            
            for trade in active_trades:
                signal_id = str(trade[0])[:36]
                symbol = trade[1] or "N/A"
                signal_type = (trade[2][:6]) if trade[2] else "N/A"
                timeframe = trade[3] or "N/A"
                entry = f"{trade[4]:.5f}" if trade[4] else "N/A"
                direction = trade[5] or "N/A"
                order_id = str(trade[6]) if trade[6] else None
                timestamp = str(trade[7])[:19] if trade[7] else "N/A"
                
                # Parse metadata JSON to check for SL/TP/Lots
                metadata_str = trade[8] or "{}"
                try:
                    metadata = json.loads(metadata_str)
                    sl = metadata.get('stop_loss')
                    tp = metadata.get('take_profit')
                    lot_size = metadata.get('lot_size') or metadata.get('volume')
                except:
                    sl = None
                    tp = None
                    lot_size = None
                
                # Count missing critical data
                if not sl:
                    missing_sl_count += 1
                if not tp:
                    missing_tp_count += 1
                if not lot_size:
                    missing_lots_count += 1
                if not order_id:
                    missing_order_id_count += 1
                
                # Display row
                order_display = order_id[:13] if order_id else "MISSING"
                print(f"{signal_id:<38} {symbol:<10} {signal_type:<8} {timeframe:<6} {direction:<6} {entry:<12} {order_display:<15} {timestamp}")
                
                # Display metadata details
                sl_display = f"{sl:.5f}" if sl else "MISSING"
                tp_display = f"{tp:.5f}" if tp else "MISSING"
                lots_display = f"{lot_size:.2f}" if lot_size else "MISSING"
                print(f"  └─ SL: {sl_display:12} | TP: {tp_display:12} | Lots: {lots_display}")
            
            # Summary of missing data
            print("\n" + "-" * 100)
            print("CALIDAD DE DATOS (Operaciones Activas):")
            print(f"   Operaciones sin SL:       {missing_sl_count:3} {'CRITICO' if missing_sl_count > 0 else 'OK'}")
            print(f"   Operaciones sin TP:       {missing_tp_count:3} {'WARNING' if missing_tp_count > 0 else 'OK'}")
            print(f"   Operaciones sin Lots:     {missing_lots_count:3} {'ERROR' if missing_lots_count > 0 else 'OK'}")
            print(f"   Operaciones sin Order ID: {missing_order_id_count:3} {'ERROR' if missing_order_id_count > 0 else 'OK'}")
        
        # 2. OPERACIONES CERRADAS RECIENTES
        print("\n" + "="*100)
        print("2. OPERACIONES CERRADAS (ULTIMAS 10):")
        print("="*100)
        
        closed_trades = conn.execute("""
            SELECT tr.id, tr.symbol, tr.entry_price, tr.exit_price, tr.profit, 
                   tr.exit_reason, tr.close_time, s.signal_type, s.timeframe
            FROM trade_results tr
            LEFT JOIN signals s ON tr.signal_id = s.id
            ORDER BY tr.close_time DESC
            LIMIT 10
        """).fetchall()
        
        if not closed_trades:
            print("\n   NO HAY OPERACIONES CERRADAS\n")
        else:
            print(f"\n   TOTAL: {len(closed_trades)} operaciones cerradas\n")
            print(f"{'ID':<15} {'Symbol':<10} {'Type':<8} {'TF':<6} {'Entry':<12} {'Exit':<12} {'Profit':<12} {'Reason':<15} {'Close Time'}")
            print("-" * 120)
            
            for trade in closed_trades:
                trade_id = str(trade[0])[:13]
                symbol = trade[1] or "N/A"
                entry = f"{trade[2]:.5f}" if trade[2] else "N/A"
                exit_price = f"{trade[3]:.5f}" if trade[3] else "N/A"
                profit = f"${trade[4]:.2f}" if trade[4] else "N/A"
                reason = (trade[5][:13]) if trade[5] else "N/A"
                close_time = str(trade[6])[:19] if trade[6] else "N/A"
                signal_type = (trade[7][:6]) if trade[7] else "N/A"
                timeframe = trade[8] or "N/A"
                
                print(f"{trade_id:<15} {symbol:<10} {signal_type:<8} {timeframe:<6} {entry:<12} {exit_price:<12} {profit:<12} {reason:<15} {close_time}")
        
        # 3. ANALISIS TEMPORAL
        print("\n" + "="*100)
        print("3. ANALISIS TEMPORAL:")
        print("="*100)
        
        now = datetime.now()
        last_5min = (now - timedelta(minutes=5)).isoformat()
        last_1h = (now - timedelta(hours=1)).isoformat()
        last_24h = (now - timedelta(hours=24)).isoformat()
        
        count_5min = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE UPPER(status) = 'EXECUTED' AND timestamp >= ?", 
            (last_5min,)
        ).fetchone()[0]
        count_1h = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE UPPER(status) = 'EXECUTED' AND timestamp >= ?", 
            (last_1h,)
        ).fetchone()[0]
        count_24h = conn.execute(
            "SELECT COUNT(*) FROM signals WHERE UPPER(status) = 'EXECUTED' AND timestamp >= ?", 
            (last_24h,)
        ).fetchone()[0]
        
        print(f"\n   Operaciones ejecutadas:")
        print(f"      Ultimos 5 minutos: {count_5min:3}")
        print(f"      Ultima 1 hora:     {count_1h:3}")
        print(f"      Ultimas 24 horas:  {count_24h:3}")
        
        if count_5min > 5:
            print(f"\n   ⚠ ALERTA: {count_5min} operaciones en 5 minutos - posible acumulacion de señales")
        
        # 4. SENALES PENDIENTES
        print("\n" + "="*100)
        print("4. SENALES PENDIENTES (NO EJECUTADAS):")
        print("="*100)
        
        pending_signals = conn.execute("""
            SELECT symbol, signal_type, timeframe, confidence, timestamp
            FROM signals
            WHERE UPPER(status) = 'PENDING'
            ORDER BY timestamp DESC
            LIMIT 10
        """).fetchall()
        
        if not pending_signals:
            print("\n   NO HAY SENALES PENDIENTES\n")
        else:
            total_pending = conn.execute("SELECT COUNT(*) FROM signals WHERE UPPER(status) = 'PENDING'").fetchone()[0]
            print(f"\n   TOTAL: {total_pending} señales pendientes (mostrando ultimas 10)\n")
            print(f"{'Symbol':<10} {'Type':<15} {'TF':<6} {'Confidence':<12} {'Timestamp'}")
            print("-" * 70)
            
            for sig in pending_signals:
                symbol = sig[0] or "N/A"
                sig_type = sig[1] or "N/A"
                timeframe = sig[2] or "N/A"
                confidence = f"{sig[3]:.2f}" if sig[3] else "N/A"
                timestamp = str(sig[4])[:19] if sig[4] else "N/A"
                
                print(f"{symbol:<10} {sig_type:<15} {timeframe:<6} {confidence:<12} {timestamp}")
        
        # 5. RESUMEN EJECUTIVO
        print("\n" + "="*100)
        print("5. RESUMEN EJECUTIVO:")
        print("="*100)
        
        total_executed = conn.execute("SELECT COUNT(*) FROM signals WHERE UPPER(status) = 'EXECUTED'").fetchone()[0]
        total_closed = conn.execute("SELECT COUNT(*) FROM trade_results").fetchone()[0]
        total_active = total_executed - total_closed
        total_pending = conn.execute("SELECT COUNT(*) FROM signals WHERE UPPER(status) = 'PENDING'").fetchone()[0]
        
        print(f"\n   Total senales ejecutadas: {total_executed}")
        print(f"   Operaciones activas:      {total_active}")
        print(f"   Operaciones cerradas:     {total_closed}")
        print(f"   Senales pendientes:       {total_pending}")
        
        # Alertas finales
        print("\n" + "="*100)
        print("ALERTAS:")
        print("="*100)
        alerts = []
        if active_trades and missing_sl_count > 0:
            alerts.append(f"⚠ CRITICO: {missing_sl_count} operaciones activas SIN STOP LOSS")
        if active_trades and missing_order_id_count > 0:
            alerts.append(f"⚠ ERROR: {missing_order_id_count} operaciones sin Order ID del broker")
        if count_5min > 5:
            alerts.append(f"⚠ WARNING: {count_5min} operaciones ejecutadas en 5 min (posible acumulacion)")
        if total_pending > 20:
            alerts.append(f"ℹ INFO: {total_pending} señales pendientes en cola")
        
        if alerts:
            for alert in alerts:
                print(f"   {alert}")
        else:
            print("   ✅ No se detectaron problemas criticos")
        
        print("\n" + "="*100 + "\n")
    
    finally:
        storage._close_conn(conn)

if __name__ == "__main__":
    audit_operations()
