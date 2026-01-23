"""
Ejemplo de uso de Aethelgard
Muestra cómo enviar señales y consultar el régimen de mercado
"""
import asyncio
import json
import websockets
from datetime import datetime
from models.signal import Signal, ConnectorType, SignalType


async def test_connection():
    """Ejemplo de conexión y envío de señal"""
    uri = "ws://localhost:8000/ws/MT5/test_client"
    
    try:
        async with websockets.connect(uri) as websocket:
            print("✓ Conectado a Aethelgard")
            
            # Enviar señal de prueba
            signal = {
                "type": "signal",
                "connector": "MT5",
                "symbol": "EURUSD",
                "signal_type": "BUY",
                "price": 1.0850,
                "timestamp": datetime.utcnow().isoformat(),
                "volume": 0.01,
                "stop_loss": 1.0800,
                "take_profit": 1.0900,
                "strategy_id": "test_strategy"
            }
            
            print(f"Enviando señal: {signal['symbol']} {signal['signal_type']} @ {signal['price']}")
            await websocket.send(json.dumps(signal))
            
            # Recibir respuesta
            response = await websocket.recv()
            data = json.loads(response)
            print(f"✓ Respuesta recibida: {data}")
            
            # Enviar ping
            await websocket.send(json.dumps({"type": "ping"}))
            pong = await websocket.recv()
            print(f"✓ Heartbeat: {pong}")
            
    except Exception as e:
        print(f"✗ Error: {e}")
        print("Asegúrate de que el servidor esté ejecutándose (python main.py)")


async def test_http_endpoint():
    """Ejemplo de uso del endpoint HTTP"""
    import httpx
    
    try:
        async with httpx.AsyncClient() as client:
            # Enviar señal vía HTTP
            signal = {
                "connector": "TV",
                "symbol": "EURUSD",
                "signal_type": "SELL",
                "price": 1.0850,
                "timestamp": datetime.utcnow().isoformat(),
                "volume": 0.01
            }
            
            response = await client.post(
                "http://localhost:8000/api/signal",
                json=signal
            )
            
            print(f"✓ Respuesta HTTP: {response.json()}")
            
            # Consultar régimen
            regime_response = await client.get(
                "http://localhost:8000/api/regime/EURUSD"
            )
            print(f"✓ Régimen actual: {regime_response.json()}")
            
    except Exception as e:
        print(f"✗ Error: {e}")


if __name__ == "__main__":
    print("=== Ejemplo de uso de Aethelgard ===\n")
    print("1. Asegúrate de que el servidor esté ejecutándose:")
    print("   python main.py\n")
    print("2. Ejecutando prueba de conexión WebSocket...\n")
    
    asyncio.run(test_connection())
    
    print("\n3. Ejecutando prueba de endpoint HTTP...\n")
    asyncio.run(test_http_endpoint())
