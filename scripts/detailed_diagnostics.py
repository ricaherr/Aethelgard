#!/usr/bin/env python3
"""
DETAILED DIAGNOSTICS: Check what's happening in the orchestrator
Examina el estado del sistema y verifica dónde se rompe el flujo
"""

import asyncio
import websockets
import json
import time
from datetime import datetime
from collections import defaultdict

async def main():
    print("\n" + "="*80)
    print("🔬 DETAILED DIAGNOSTICS: System State Analysis")
    print("="*80 + "\n")
    
    print("📋 CHECKING BACKEND LOGS FOR KEY INITIALIZATION MESSAGES...")
    print("-" * 80)
    print("\nSearching for:")
    print("  ✓ [ORCHESTRATOR] UI_Mapping_Service initialized")
    print("  ✓ [ANALYZER] MarketStructureAnalyzer initialized  ")
    print("  ✓ [UI_MAPPING] EMITTING ANALYSIS_UPDATE")
    print("  ✓ [UI_MAPPING] Error emitting trader page update")
    print("-" * 80 + "\n")
    
    print("\n📡 CHECKING WEBSOCKET EVENTS...\n")
    
    ws_url = "ws://localhost:8000/ws/GENERIC/analysis"
    try:
        async with websockets.connect(ws_url) as websocket:
            print(f"✅ WebSocket Connected\n")
            
            start = time.time()
            events_count = 0
            analysis_count = 0
            
            while time.time() - start < 45:  # 45 seconds
                try:
                    msg = await asyncio.wait_for(websocket.recv(), timeout=2.0)
                    data = json.loads(msg)
                    event_type = data.get('type', 'UNKNOWN')
                    events_count += 1
                    
                    if event_type in ['ANALYSIS_UPDATE', 'TRADER_PAGE_UPDATE']:
                        analysis_count += 1
                        print(f"✅ {event_type} RECEIVED (#{analysis_count})")
                        
                        payload = data.get('payload', {})
                        signals = payload.get('analysis_signals', {})
                        print(f"   Analysis Signals: {len(signals)}")
                        
                except asyncio.TimeoutError:
                    pass
            
            print(f"\n" + "="*80)
            print(f"📊 RESULTS after 45 seconds:")
            print(f"   • Total events received: {events_count}")
            print(f"   • ANALYSIS_UPDATE events: {analysis_count}")
            print("="*80 + "\n")
            
            if analysis_count == 0:
                print("\n⛔ CRITICAL FINDING:")
                print("   NO ANALYSIS_UPDATE events were received")
                print("\nROOT CAUSE ANALYSIS:")
                print("   The socket IS working (other events flow through)")
                print("   But analysis.py is NOT emitting via WebSocket")
                print("\nPOSSIBLE ROOT CAUSES:")
                print("   1. UIMappingService was NOT initialized (check logs)")
                print("   2. MarketStructureAnalyzer was NOT initialized")
                print("   3. emit_trader_page_update() is not being called")
                print("   4. SocketService.emit_event() has a silent error\n")
            else:
                print("\n✅ System appears to be working!")
                print("   Check frontend to see why data isn't displaying\n")
    
    except Exception as e:
        print(f"❌ WebSocket Error: {e}")
        print("   Server may not be running\n")

if __name__ == "__main__":
    asyncio.run(main())
