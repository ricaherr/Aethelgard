"""
Socket Service: WebSocket Connection Management

Singleton service that manages all active WebSocket connections between
the core brain and connected clients (UI, connectors, etc).

Architecture:
- Single instance across the entire application
- Thread-safe connection tracking
- Event broadcasting capabilities
"""
import logging
from typing import Dict, Set, Any, Optional
from datetime import datetime
from fastapi import WebSocket

from models.signal import ConnectorType

logger = logging.getLogger(__name__)


class SocketService:
    """Singleton service for managing WebSocket connections"""
    
    _instance: Optional['SocketService'] = None
    
    def __new__(cls) -> 'SocketService':
        """Ensure only one instance exists (Singleton pattern)"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """Initialize the socket service (only once due to Singleton)"""
        if self._initialized:
            return
        
        self.active_connections: Dict[str, WebSocket] = {}
        self.connector_types: Dict[str, ConnectorType] = {}
        self._initialized = True
        logger.info("SocketService initialized (Singleton)")
    
    async def connect(self, websocket: WebSocket, client_id: str, connector: ConnectorType) -> None:
        """
        Accepts a new WebSocket connection
        
        Args:
            websocket: FastAPI WebSocket instance
            client_id: Unique client identifier
            connector: ConnectorType enum (UI, MT5, etc)
        """
        await websocket.accept()
        self.active_connections[client_id] = websocket
        self.connector_types[client_id] = connector
        logger.info(f"WebSocket connected: {client_id} ({connector.value})")
    
    def disconnect(self, client_id: str) -> None:
        """
        Removes a connection from tracking
        
        Args:
            client_id: Client identifier to disconnect
        """
        if client_id in self.active_connections:
            connector = self.connector_types.get(client_id, "Unknown")
            del self.active_connections[client_id]
            del self.connector_types[client_id]
            logger.info(f"WebSocket disconnected: {client_id} ({connector})")
    
    async def send_personal_message(self, message: dict, client_id: str) -> None:
        """
        Sends a message to a specific client
        
        Args:
            message: Message dict to send
            client_id: Target client identifier
        """
        if client_id in self.active_connections:
            try:
                await self.active_connections[client_id].send_json(message)
            except Exception as e:
                logger.error(f"Error sending message to {client_id}: {e}")
                self.disconnect(client_id)
    
    async def broadcast(self, message: dict, exclude: Optional[Set[str]] = None) -> None:
        """
        Sends a message to all connected clients
        
        Args:
            message: Message dict to broadcast
            exclude: Set of client IDs to skip (optional)
        """
        if exclude is None:
            exclude = set()
        
        disconnected = []
        for client_id, websocket in self.active_connections.items():
            if client_id not in exclude:
                try:
                    await websocket.send_json(message)
                except Exception as e:
                    logger.error(f"Error in broadcast to {client_id}: {e}")
                    disconnected.append(client_id)
        
        for client_id in disconnected:
            self.disconnect(client_id)

    async def emit_event(self, event_type: str, payload: dict) -> None:
        """
        Sends a formatted event to all connected clients
        
        Used primarily for system events (heartbeat, regime updates, etc)
        
        Args:
            event_type: Event type identifier (e.g., 'SYSTEM_HEARTBEAT')
            payload: Event payload dict
        """
        await self.broadcast({
            "type": event_type,
            "payload": payload,
            "timestamp": datetime.now().isoformat()
        })

    def get_connection_count(self) -> int:
        """Returns the number of active connections"""
        return len(self.active_connections)

    def get_connection_info(self) -> Dict[str, Any]:
        """
        Returns information about all active connections
        
        Returns:
            Dict mapping client_id to connector type
        """
        return dict(self.connector_types)


def get_socket_service() -> SocketService:
    """
    Get the singleton SocketService instance
    
    Returns:
        SocketService singleton
    """
    return SocketService()
