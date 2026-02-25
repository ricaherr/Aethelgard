"""
Routers - Modular endpoint organization.
"""
from core_brain.api.routers.trading import router as trading_router
from core_brain.api.routers.risk import router as risk_router

__all__ = ["trading_router", "risk_router"]
