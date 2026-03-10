"""
API Schemas: Response Helpers & Data Transformation.

Centraliza transformaciones de modelos a responses para evitar duplicación de código.
"""
from typing import Dict, Any


def user_to_response(user: Dict[str, Any]) -> Dict[str, Any]:
    """
    Transform user DB record to API response (sin password_hash).
    
    Args:
        user: Dict con campos id, email, role, status, tier, created_at, updated_at, password_hash
        
    Returns:
        Dict con solo campos públicos (sin password_hash)
    """
    return {
        "id": user["id"],
        "email": user["email"],
        "role": user["role"],
        "status": user["status"],
        "tier": user["tier"],
        "created_at": user["created_at"],
        "updated_at": user["updated_at"]
    }
