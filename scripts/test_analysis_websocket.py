#!/usr/bin/env python3
"""
Test script to verify Analysis WebSocket is working and emitting data
"""
import asyncio
import websockets
import json
import sys
from datetime import datetime

async def test_analysis_websocket():
    """Test the /ws/GENERIC/analysis WebSocket endpoint"""
    
    uri = "ws://localhost:8000/ws/GENERIC/analysis"
    print(f"🔌 [ANALYSIS WS TEST] Connecting to {uri}...")
    
    try:
        async with websockets.connect(uri) as websocket:
            print(f"✅ [ANALYSIS WS TEST] Connected!")
            print(f"⏱️  Listening for analysis events (30 seconds timeout)...\n")
            
            message_count = 0
            analysis_count = 0
            start_time = datetime.now()
            
            try:
                while True:
                    # Set timeout to 30 seconds
                    try:
                        message = await asyncio.wait_for(websocket.recv(), timeout=30)
                        message_count += 1
                        
                        try:
                            data = json.loads(message)
                            msg_type = data.get('type', 'UNKNOWN')
                            
                            print(f"📬 Message #{message_count}: {msg_type}")
                            
                            # Check for analysis-related messages
                            if 'ANALYSIS' in msg_type or 'analysis' in str(data):
                                analysis_count += 1
                                print(f"   📊 Analysis data detected!")
                                
                                # Show payload preview
                                if 'payload' in data:
                                    payload = data['payload']
                                    if isinstance(payload, dict):
                                        print(f"   🔍 Payload keys: {list(payload.keys())}")
                                        if 'analysis_signals' in payload:
                                            print(f"   ✅ Found analysis_signals: {len(payload['analysis_signals'])} signals")
                                        if 'elements' in payload:
                                            print(f"   ✅ Found elements: {len(payload['elements']) if isinstance(payload['elements'], list) else '?'} elements")
                            
                            # Show heartbeat
                            if 'HEARTBEAT' in msg_type:
                                print(f"   💓 Heartbeat received")
                            
                            print()
                            
                        except json.JSONDecodeError:
                            print(f"   ⚠️  Invalid JSON: {message[:100]}")
                    
                    except asyncio.TimeoutError:
                        elapsed = (datetime.now() - start_time).total_seconds()
                        print(f"\n⏱️  Timeout reached after {elapsed:.1f} seconds")
                        break
            
            except KeyboardInterrupt:
                elapsed = (datetime.now() - start_time).total_seconds()
                print(f"\n⏹️  Interrupted after {elapsed:.1f} seconds")
    
    except Exception as e:
        print(f"❌ [ANALYSIS WS TEST] Error: {type(e).__name__}: {e}")
        print(f"   - Check if server is running on port 8000")
        print(f"   - Check if /ws/GENERIC/analysis endpoint is available")
        return False
    
    # Summary
    print(f"\n📊 TEST SUMMARY:")
    print(f"   - Total messages received: {message_count}")
    print(f"   - Analysis-specific messages: {analysis_count}")
    print(f"   - Status: {'✅ PASS' if analysis_count > 0 else '⚠️  NO ANALYSIS DATA (check backend)'}")
    
    return analysis_count > 0

if __name__ == "__main__":
    success = asyncio.run(test_analysis_websocket())
    sys.exit(0 if success else 1)
