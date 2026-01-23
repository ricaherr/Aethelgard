"""
Punto de entrada principal para Aethelgard
"""
import uvicorn
from core_brain.server import app

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
