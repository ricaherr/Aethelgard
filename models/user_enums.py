"""
User Management Enums: SSOT for Valid Values.

Centraliza todos los valores posibles para:
- Roles (admin, trader)
- Tiers (BASIC, PREMIUM, INSTITUTIONAL)
- Status (active, suspended, deleted)

Cambiar un valor aquí propaga a TODO el sistema automáticamente.
"""
from enum import Enum
from typing import List, Tuple


class UserRole(str, Enum):
    """Roles de usuario en el sistema."""
    ADMIN = "admin"
    TRADER = "trader"

    @classmethod
    def valid_roles(cls) -> Tuple[str, ...]:
        """Retorna tupla de valores válidos (para validaciones)."""
        return tuple(role.value for role in cls)

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Valida si un valor es un rol válido."""
        return value in cls.valid_roles()


class UserTier(str, Enum):
    """Niveles de membresía/plan."""
    BASIC = "BASIC"
    PREMIUM = "PREMIUM"
    INSTITUTIONAL = "INSTITUTIONAL"

    @classmethod
    def valid_tiers(cls) -> Tuple[str, ...]:
        """Retorna tupla de valores válidos."""
        return tuple(tier.value for tier in cls)

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Valida si un valor es un tier válido."""
        return value in cls.valid_tiers()


class UserStatus(str, Enum):
    """Estados de usuario."""
    ACTIVE = "active"
    SUSPENDED = "suspended"
    DELETED = "deleted"

    @classmethod
    def valid_statuses(cls) -> Tuple[str, ...]:
        """Retorna tupla de valores válidos."""
        return tuple(status.value for status in cls)

    @classmethod
    def is_valid(cls, value: str) -> bool:
        """Valida si un valor es un estado válido."""
        return value in cls.valid_statuses()

    @classmethod
    def active_statuses(cls) -> Tuple[str, ...]:
        """Retorna solo los estados activos (excluendo deleted)."""
        return (cls.ACTIVE.value, cls.SUSPENDED.value)


# ── Constants for Convenience ──────────────────────────────────────────────────

VALID_ROLES = UserRole.valid_roles()
VALID_TIERS = UserTier.valid_tiers()
VALID_STATUSES = UserStatus.valid_statuses()
VALID_ACTIVE_STATUSES = UserStatus.active_statuses()
