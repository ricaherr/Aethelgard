#!/usr/bin/env python3
"""
DIAGNOSTIC: End-to-End Data Flow Analysis
Verifica la cadena completa de datos desde Scanner → UI
"""

import asyncio
import websockets
import json
import sys
import time
from datetime import datetime
from collections import defaultdict
import signal

class DataFlowDiagnostic:
    def __init__(self, ws_url="ws://localhost:8000/ws/GENERIC/analysis"):
        self.ws_url = ws_url
        self.running = True
        self.events_received = defaultdict(int)
        self.analysis_signals_count = 0
        self.elements_count = 0
        self.last_update = None
        
    async def connect_and_listen(self, duration_seconds=30):
        """Conecta a WebSocket y escucha eventos"""
        print("\n" + "="*80)
        print("🔍 DIAGNOSTIC: ANALYSIS WEBSOCKET LISTENER")
        print("="*80)
        print(f"Target: {self.ws_url}")
        print(f"Duration: {duration_seconds}s")
        print(f"Start time: {datetime.now().strftime('%H:%M:%S.%f')[:-3]}")
        print("="*80 + "\n")
        
        try:
            async with websockets.connect(self.ws_url) as websocket:
                print("✅ WebSocket CONNECTED\n")
                
                # Listen for messages
                start_time = time.time()
                while self.running and (time.time() - start_time) < duration_seconds:
                    try:
                        # Set timeout to avoid hanging
                        message = await asyncio.wait_for(
                            websocket.recv(),
                            timeout=2.0
                        )
                        
                        self._process_message(message)
                        
                    except asyncio.TimeoutError:
                        # No message received in 2 seconds - expected
                        pass
                    except Exception as e:
                        print(f"❌ Error receiving message: {e}")
                        break
                
                print("\n" + "="*80)
                print("📊 DIAGNOSTIC SUMMARY")
                print("="*80)
                self._print_summary()
                print("="*80 + "\n")
                        
        except Exception as e:
            print(f"❌ WebSocket Connection Failed: {e}")
            print("\n⚠️  POSSIBLE ISSUES:")
            print("  1. Server not running")
            print("  2. WebSocket endpoint not available")
            print("  3. Authentication required")
            return False
        
        return True
    
    def _process_message(self, raw_message):
        """Procesa y analiza cada mensaje"""
        try:
            data = json.loads(raw_message)
            
            # Extract event type
            event_type = data.get('type', 'UNKNOWN')
            self.events_received[event_type] += 1
            self.last_update = datetime.now()
            
            # For ANALYSIS_UPDATE, extract metrics
            if event_type in ['ANALYSIS_UPDATE', 'TRADER_PAGE_UPDATE']:
                payload = data.get('payload', {})
                analysis_signals = payload.get('analysis_signals', {})
                elements = payload.get('elements', [])
                priority = payload.get('priority', 'unknown')
                
                self.analysis_signals_count = len(analysis_signals)
                self.elements_count = len(elements)
                
                print(f"📨 Event: {event_type}")
                print(f"   ├─ Priority: {priority}")
                print(f"   ├─ Analysis Signals: {len(analysis_signals)}")
                print(f"   ├─ Elements: {len(elements)}")
                print(f"   ├─ Detected: {payload.get('analysis_detected', False)}")
                
                # Show first few signals
                if analysis_signals:
                    print(f"   ├─ Signal samples:")
                    for idx, (key, signal) in enumerate(list(analysis_signals.items())[:3]):
                        sig_type = signal.get('type', '?')
                        sig_asset = signal.get('asset', '?')
                        print(f"   │  └─ {sig_type}: {sig_asset}")
                    if len(analysis_signals) > 3:
                        print(f"   │     ... and {len(analysis_signals)-3} more")
                else:
                    print(f"   └─ ⚠️  NO SIGNALS in payload")
                
                print()
        except json.JSONDecodeError:
            print(f"⚠️  Invalid JSON: {raw_message[:100]}")
        except Exception as e:
            print(f"❌ Error processing message: {e}")
    
    def _print_summary(self):
        """Imprime resumen de diagnóstico"""
        if not self.events_received:
            print("\n❌ NO EVENTS RECEIVED")
            print("\n⚠️  DIAGNOSTIC VERDICT: WEBSOCKET NOT EMITTING DATA")
            print("\nPOSSIBLE ROOT CAUSES:")
            print("  1. Backend not executing MarketStructureAnalyzer")
            print("  2. UIMappingService.emit_trader_page_update() not being called")
            print("  3. socket_service.emit_event() has an error")
            print("  4. WebSocket broadcast not reaching clients")
            return
        
        total_events = sum(self.events_received.values())
        analysis_events = self.events_received.get('ANALYSIS_UPDATE', 0)
        trader_events = self.events_received.get('TRADER_PAGE_UPDATE', 0)
        
        print(f"\n📊 EVENTS RECEIVED:")
        for event_type, count in sorted(self.events_received.items(), key=lambda x: -x[1]):
            print(f"   • {event_type}: {count}")
        
        print(f"\n✅ TOTAL: {total_events} events")
        
        if analysis_events > 0 or trader_events > 0:
            print("\n✅ ANALYSIS UPDATE EVENTS RECEIVED!")
            print(f"\n📈 LAST SIGNALS STATE:")
            print(f"   • Analysis Signals Count: {self.analysis_signals_count}")
            print(f"   • Elements Count: {self.elements_count}")
            
            if self.analysis_signals_count > 0:
                print("\n✅ DIAGNOSTIC VERDICT: SYSTEM WORKING CORRECTLY")
                print("   Backend is detecting market structures and emitting via WebSocket")
            else:
                print("\n⚠️  DIAGNOSTIC VERDICT: MIXED RESULTS")
                print("   WebSocket is receiving ANALYSIS_UPDATE events but...")
                print("   ...no analysis_signals in the last payload")
                print("\nPOSSIBLE ISSUES:")
                print("   1. Analysis signals being generated but not persisting")
                print("   2. Timing issue - signals cleared before emit")
                print("   3. MarketStructureAnalyzer not finding valid structures")
        else:
            print("\n❌ DIAGNOSTIC VERDICT: NO ANALYSIS UPDATES RECEIVED")
            print("\nOther events received:", list(self.events_received.keys()))
            print("\nPOSSIBLE ROOT CAUSES:")
            print("  1. MarketStructureAnalyzer not executing")
            print("  2. UIMappingService.add_structure_signal() not being called")
            print("  3. emit_trader_page_update() throwing exception silently")
    
    def stop(self):
        """Detiene la escucha"""
        self.running = False


async def main():
    """Main entry point"""
    # Configure signal handler for graceful shutdown
    diagnostic = DataFlowDiagnostic()
    
    def signal_handler(sig, frame):
        print("\n\n⏹️  Stopping diagnostic...")
        diagnostic.stop()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    # Run diagnostic for 60 seconds
    success = await diagnostic.connect_and_listen(duration_seconds=60)
    
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    print("\n🔧 AETHELGARD DATA FLOW DIAGNOSTIC")
    print("==================================\n")
    print("Este diagnóstico verifica:")
    print("  ✓ Conexión WebSocket")
    print("  ✓ Emisión de eventos ANALYSIS_UPDATE")
    print("  ✓ Presencia de signals en payloads")
    print("  ✓ Flujo end-to-end de datos\n")
    
    asyncio.run(main())
