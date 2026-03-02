"""
Infrastructure layer: Low-level, cross-cutting concerns.
- Process communication (IPC)
- Session management
- Health checks
"""

from .process_gateway import (
    ProcessGatewayInterface,
    DatabaseGateway,
    RedisGateway,
    get_process_gateway
)

__all__ = [
    "ProcessGatewayInterface",
    "DatabaseGateway", 
    "RedisGateway",
    "get_process_gateway"
]
