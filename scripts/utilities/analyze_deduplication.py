#!/usr/bin/env python3
"""
Deep Analysis - Signal Deduplication Logic
Investigates why 1,065 duplicates exist despite deduplication system
"""
import sys
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
import json

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from data_vault.storage import StorageManager
from data_vault.signals_db import calculate_deduplication_window

def analyze_deduplication_logic():
    """Deep dive into deduplication logic failures"""
    
    print("\n" + "="*100)
    print("ANALISIS PROFUNDO: LOGICA DE DEDUPLICACION")
    print("="*100)
    
    storage = StorageManager()
    conn = storage._get_conn()
    
    try:
        # 1. ANALIZAR CAMBIOS DE STATUS
        print("\n" + "="*100)
        print("1. DISTRIBUCION DE STATUS:")
        print("="*100)
        
        status_counts = conn.execute("""
            SELECT status, COUNT(*) as count
            FROM signals
            GROUP BY status
        """).fetchall()
        
        total_signals = sum(row[1] for row in status_counts)
        print(f"\n   TOTAL SEÑALES EN DB: {total_signals}\n")
        
        for status, count in status_counts:
            pct = count/total_signals*100
            print(f"   {status or 'NULL':15} {count:6} ({pct:5.1f}%)")
        
        # 2. ANALIZAR TEMPORAL (timestamp only - no created_at/updated_at)
        print("\n" + "="*100)
        print("2. SEÑALES RECIENTES (últimas 50):")
        print("="*100)
        
        timeline = conn.execute("""
            SELECT id, symbol, timeframe, status, timestamp
            FROM signals
            WHERE status IN ('PENDING', 'EXECUTED', 'EXPIRED')
            ORDER BY timestamp DESC
            LIMIT 50
        """).fetchall()
        
        print(f"\n{'Timestamp':<20} {'Status':<12} {'Symbol':<10} {'TF':<6} {'Signal ID'}")
        print("-" * 70)
        
        for sig in timeline:
            sig_id, symbol, tf, status, ts = sig
            ts_str = str(ts)[:19] if ts else "N/A"
            
            print(f"{ts_str:<20} {status:<12} {symbol:<10} {tf or 'N/A':<6} {str(sig_id)[:8]}...")
        
        # Count EXPIRED signals
        expired_count = sum(1 for s in timeline if s[3] == 'EXPIRED')
        print(f"\n   Señales EXPIRED en muestra: {expired_count}/{len(timeline)}")
        
        # 3. VENTANAS DE DEDUPLICACION POR TIMEFRAME
        print("\n" + "="*100)
        print("3. VENTANAS DE DEDUPLICACION CALCULADAS:")
        print("="*100)
        
        timeframes = ['M5', 'M15', 'H1', 'H4', 'D1']
        print(f"\n{'Timeframe':<10} {'Window (min)':<15} {'Window (sec)'}")
        print("-" * 50)
        
        for tf in timeframes:
            window_min = calculate_deduplication_window(tf)
            window_sec = window_min * 60
            print(f"{tf:<10} {window_min:<15} {window_sec}")
        
        # 4. CASOS REALES DE DUPLICADOS
        print("\n" + "="*100)
        print("4. CASOS REALES DE DUPLICACION (Mismo Symbol+TF+Type):")
        print("="*100)
        
        # Find actual duplicates in PENDING status
        duplicates = conn.execute("""
            SELECT symbol, signal_type, timeframe, status, COUNT(*) as count, 
                   MIN(timestamp) as first, MAX(timestamp) as last
            FROM signals
            WHERE status = 'PENDING'
            GROUP BY symbol, signal_type, timeframe
            HAVING count > 1
            ORDER BY count DESC
            LIMIT 20
        """).fetchall()
        
        print(f"\n   TOTAL GRUPOS DUPLICADOS: {len(duplicates)}\n")
        print(f"{'Symbol':<10} {'Type':<8} {'TF':<6} {'Count':<7} {'First Signal':<20} {'Last Signal':<20} {'Gap (min)'}")
        print("-" * 100)
        
        for dup in duplicates:
            symbol, sig_type, tf, status, count, first, last = dup
            
            # Calculate time gap
            first_dt = datetime.fromisoformat(first) if first else datetime.now()
            last_dt = datetime.fromisoformat(last) if last else datetime.now()
            gap_minutes = (last_dt - first_dt).total_seconds() / 60
            
            # Get deduplication window for this timeframe
            dedup_window = calculate_deduplication_window(tf)
            
            status_marker = "❌ SHOULD DEDUP" if gap_minutes < dedup_window else "✅ OK (outside window)"
            
            print(f"{symbol:<10} {sig_type:<8} {tf or 'N/A':<6} {count:<7} {str(first)[:19]:<20} {str(last)[:19]:<20} {gap_minutes:>8.1f} min  {status_marker}")
        
        # 5. VERIFICAR LOGICA has_recent_signal()
        print("\n" + "="*100)
        print("5. TEST DE LOGICA has_recent_signal():")
        print("="*100)
        
        # Pick a symbol with duplicates
        test_cases = conn.execute("""
            SELECT symbol, signal_type, timeframe, timestamp
            FROM signals
            WHERE status = 'PENDING'
            AND symbol IN (
                SELECT symbol FROM signals 
                WHERE status = 'PENDING' 
                GROUP BY symbol, signal_type, timeframe 
                HAVING COUNT(*) > 1
            )
            ORDER BY timestamp DESC
            LIMIT 10
        """).fetchall()
        
        print("\n   Testing has_recent_signal() con casos reales:\n")
        
        for symbol, sig_type, tf, ts in test_cases:
            # Call actual method
            has_recent = storage.has_recent_signal(symbol, sig_type, tf)
            ts_str = str(ts)[:19] if ts else "N/A"
            
            result_str = "✅ DETECTADO" if has_recent else "❌ NO DETECTADO"
            print(f"   {symbol:<10} {sig_type:<15} {tf or 'N/A':<6} {ts_str:<20} -> {result_str}")
        
        # 6. ANALIZAR METADATA DE SEÑALES (buscar patterns)
        print("\n" + "="*100)
        print("6. ANALISIS DE METADATA (señales PENDING):")
        print("="*100)
        
        metadata_sample = conn.execute("""
            SELECT symbol, timeframe, status, metadata
            FROM signals
            WHERE status = 'PENDING'
            LIMIT 5
        """).fetchall()
        
        print("\n   Sample metadata de señales pendientes:\n")
        for symbol, tf, status, meta_str in metadata_sample:
            try:
                meta = json.loads(meta_str) if meta_str else {}
                signal_id = meta.get('signal_id', 'N/A')[:8]
                strategy = meta.get('strategy', 'N/A')
                
                print(f"   {symbol:<10} {tf or 'N/A':<6} status={status:<10} signal_id={signal_id}... strategy={strategy}")
            except:
                print(f"   {symbol:<10} {tf or 'N/A':<6} metadata parse error")
        
        # 7. RECOMENDACIONES
        print("\n" + "="*100)
        print("DIAGNOSTICO:")
        print("="*100)
        
        diagnostics = []
        
        pending_count = next((c for s, c in status_counts if s == 'PENDING'), 0)
        executed_count = next((c for s, c in status_counts if s == 'EXECUTED'), 0)
        
        if pending_count > 100:
            diagnostics.append(f"🔴 {pending_count} señales PENDING acumuladas (limpieza requerida)")
        
        if len(duplicates) > 50:
            diagnostics.append(f"🔴 {len(duplicates)} grupos de duplicados detectados (deduplication FALLANDO)")
        
        # Check if any duplicates are within dedup window
        critical_dups = sum(1 for d in duplicates if (datetime.fromisoformat(d[6]) - datetime.fromisoformat(d[5])).total_seconds() / 60 < calculate_deduplication_window(d[2]))
        if critical_dups > 0:
            diagnostics.append(f"🔴 {critical_dups} duplicados DENTRO de ventana dedup (BUG CRITICO)")
        
        if status_changed < len(timeline) * 0.1:
            diagnostics.append(f"🟡 Bajo rate de status changes ({status_changed}/{len(timeline)}) - señales no se actualizan?")
        
        if diagnostics:
            for diag in diagnostics:
                print(f"\n   {diag}")
        else:
            print("\n   ✅ Sistema de deduplicación funcionando correctamente")
        
        print("\n" + "="*100 + "\n")
        
    finally:
        storage._close_conn(conn)

if __name__ == "__main__":
    analyze_deduplication_logic()
