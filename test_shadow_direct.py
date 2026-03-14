import asyncio
import websockets
import json

async def test():
    try:
        print('[TEST] Connecting to ws://localhost:8000/ws/shadow')
        async with websockets.connect('ws://localhost:8000/ws/shadow') as ws:
            print('[TEST] Connected! Waiting for message...')
            msg = await asyncio.wait_for(ws.recv(), timeout=3.0)
            data = json.loads(msg)
            print(f'[TEST] Received: {data.get("event_type")}')
            print('[TEST] Waiting 2 seconds...')
            await asyncio.sleep(2)
            print('[TEST] Test complete')
    except Exception as e:
        print(f'[TEST] Error: {type(e).__name__}: {e}')

asyncio.run(test())
