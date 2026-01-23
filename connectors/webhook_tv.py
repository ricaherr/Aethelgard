"""
Webhook para TradingView
Recibe alertas de TradingView y las envía a Aethelgard
"""
import json
import logging
import asyncio
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
import httpx

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuración
AETHELGARD_SERVER_URL = "http://localhost:8000/api/signal"
CLIENT_ID = "TradingView"

# Crear aplicación FastAPI para el webhook
app = FastAPI(title="TradingView Webhook Bridge")


def parse_tradingview_alert(alert_data: dict) -> dict:
    """
    Parsea una alerta de TradingView al formato de Aethelgard
    
    TradingView envía alertas en formato JSON con campos como:
    - symbol: Símbolo del instrumento
    - action: BUY, SELL, CLOSE, etc.
    - price: Precio
    - stop_loss, take_profit: Niveles opcionales
    - strategy: Nombre de la estrategia
    """
    try:
        # TradingView puede enviar los datos de diferentes formas
        # Intentar extraer de diferentes campos comunes
        
        symbol = alert_data.get("symbol") or alert_data.get("ticker") or alert_data.get("{{ticker}}")
        action = alert_data.get("action") or alert_data.get("signal") or alert_data.get("{{strategy.order.action}}")
        price = float(alert_data.get("price") or alert_data.get("{{close}}") or alert_data.get("{{strategy.order.price}}", 0))
        
        # Mapear acciones de TradingView a formato Aethelgard
        action_map = {
            "buy": "BUY",
            "sell": "SELL",
            "close": "CLOSE",
            "long": "BUY",
            "short": "SELL"
        }
        
        signal_type = action_map.get(action.lower(), action.upper())
        
        # Extraer stop loss y take profit
        stop_loss = alert_data.get("stop_loss") or alert_data.get("{{strategy.order.stop_loss}}")
        take_profit = alert_data.get("take_profit") or alert_data.get("{{strategy.order.take_profit}}")
        
        if stop_loss:
            stop_loss = float(stop_loss)
        if take_profit:
            take_profit = float(take_profit)
        
        # Volumen
        volume = alert_data.get("volume") or alert_data.get("{{strategy.order.contracts}}")
        if volume:
            volume = float(volume)
        
        # Estrategia
        strategy_id = alert_data.get("strategy") or alert_data.get("{{strategy.name}}")
        
        return {
            "connector": "TV",
            "symbol": symbol,
            "signal_type": signal_type,
            "price": price,
            "timestamp": datetime.utcnow().isoformat(),
            "volume": volume,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "strategy_id": strategy_id,
            "metadata": {
                "source": "TradingView",
                "raw_alert": alert_data
            }
        }
    
    except Exception as e:
        logger.error(f"Error parseando alerta de TradingView: {e}")
        raise


async def send_to_aethelgard(signal_data: dict) -> dict:
    """
    Envía la señal a Aethelgard
    
    Args:
        signal_data: Datos de la señal en formato Aethelgard
    
    Returns:
        Respuesta de Aethelgard
    """
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                AETHELGARD_SERVER_URL,
                json=signal_data,
                headers={"Content-Type": "application/json"}
            )
            response.raise_for_status()
            return response.json()
    
    except httpx.HTTPError as e:
        logger.error(f"Error enviando señal a Aethelgard: {e}")
        raise HTTPException(status_code=500, detail=f"Error comunicando con Aethelgard: {str(e)}")


@app.post("/webhook")
async def tradingview_webhook(request: Request):
    """
    Endpoint para recibir alertas de TradingView
    
    TradingView puede enviar datos como:
    - JSON en el body
    - Form data
    - Query parameters
    """
    try:
        # Intentar obtener datos del body
        content_type = request.headers.get("content-type", "")
        
        if "application/json" in content_type:
            alert_data = await request.json()
        elif "application/x-www-form-urlencoded" in content_type:
            form_data = await request.form()
            alert_data = dict(form_data)
        else:
            # Intentar parsear como JSON de todas formas
            try:
                body = await request.body()
                alert_data = json.loads(body.decode())
            except:
                # Si falla, intentar como query params
                alert_data = dict(request.query_params)
        
        logger.info(f"Alerta recibida de TradingView: {alert_data}")
        
        # Parsear a formato Aethelgard
        signal_data = parse_tradingview_alert(alert_data)
        
        # Enviar a Aethelgard
        result = await send_to_aethelgard(signal_data)
        
        logger.info(f"Señal enviada a Aethelgard. Resultado: {result}")
        
        return JSONResponse(
            status_code=200,
            content={
                "status": "success",
                "message": "Alerta procesada correctamente",
                "signal_id": result.get("signal_id"),
                "regime": result.get("regime")
            }
        )
    
    except ValueError as e:
        logger.error(f"Error de validación: {e}")
        raise HTTPException(status_code=400, detail=f"Error de validación: {str(e)}")
    except Exception as e:
        logger.error(f"Error procesando webhook: {e}")
        raise HTTPException(status_code=500, detail=f"Error interno: {str(e)}")


@app.get("/health")
async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "TradingView Webhook Bridge"}


@app.get("/")
async def root():
    """Endpoint raíz"""
    return {
        "service": "TradingView Webhook Bridge",
        "version": "1.0.0",
        "endpoints": {
            "webhook": "/webhook",
            "health": "/health"
        },
        "instructions": {
            "setup": "Configura una alerta en TradingView con la URL: http://tu-servidor:8001/webhook",
            "format": "TradingView enviará los datos en el body de la petición POST"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
