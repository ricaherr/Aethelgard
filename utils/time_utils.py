from datetime import datetime, timezone
from typing import Optional, Union
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo


def _parse_datetime(value: str) -> datetime:
    """Parse datetime string in common legacy formats."""
    normalized = value.strip().replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(normalized)
    except Exception:
        pass

    # Legacy DB format without timezone
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(normalized.replace("T", " "), fmt)
        except Exception:
            continue
    raise ValueError(f"Formato de fecha no soportado: {value}")


def to_utc_datetime(
    dt: Union[str, datetime],
    source_tz: Optional[str] = None
) -> datetime:
    """
    Normalize datetime/string to timezone-aware UTC datetime.
    Naive datetimes are interpreted as local timezone unless source_tz is provided.
    """
    parsed: datetime
    if isinstance(dt, str):
        parsed = _parse_datetime(dt)
    elif isinstance(dt, datetime):
        parsed = dt
    else:
        raise ValueError(f"Tipo de fecha no soportado: {type(dt)}")

    if parsed.tzinfo is None:
        if source_tz:
            try:
                parsed = parsed.replace(tzinfo=ZoneInfo(source_tz))
            except Exception:
                raise ValueError(f"Zona horaria invalida: {source_tz}")
        else:
            local_tz = datetime.now().astimezone().tzinfo or timezone.utc
            parsed = parsed.replace(tzinfo=local_tz)

    return parsed.astimezone(timezone.utc)


def to_utc(dt: Union[str, datetime], source_tz: Optional[str] = None) -> str:
    """
    Convierte un datetime o string a UTC ISO 8601 (YYYY-MM-DD HH:MM:SS.SSS) para almacenamiento.
    source_tz puede ser string (ej: 'Europe/Madrid') o None (asume UTC o naive local).
    """
    dt_utc = to_utc_datetime(dt, source_tz=source_tz)
    return dt_utc.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Milisegundos, sin microsegundos
