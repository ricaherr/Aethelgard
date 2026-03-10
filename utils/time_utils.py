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


def broker_timestamp_to_utc_datetime(timestamp: Union[int, float]) -> datetime:
    """
    Convierte timestamp UNIX de broker a UTC datetime AWARENESS-SAFE.
    
    **GARANTÍA TIMEZONE**: Todos los brokers devuelven timestamps UNIX (siempre UTC).
    Esta función es EXPLÍCITA: timestamp UNIX → UTC datetime (nunca timezone local).
    
    Args:
        timestamp: UNIX timestamp de broker (MT5, Rithmic, OANDA, etc.)
    
    Returns:
        datetime con timezone=UTC (nunca naive, nunca local)
    
    Ejemplo:
        >>> ts = 1710082800  # 2025-03-10 10:00:00 UTC
        >>> dt = broker_timestamp_to_utc_datetime(ts)
        >>> dt.tzinfo == timezone.utc
        True
        >>> dt.hour == 10  # UTC hour
        True
    
    TRACE_ID: TZUTIL-BROKER-TIMESTAMP-001
    """
    return datetime.fromtimestamp(timestamp, tz=timezone.utc)


def broker_timestamp_to_utc_str(timestamp: Union[int, float]) -> str:
    """
    Convierte timestamp UNIX a string ISO 8601 UTC (para persistencia).
    
    Args:
        timestamp: UNIX timestamp
    
    Returns:
        String ISO 8601 con timezone UTC (ej: "2025-03-10T10:00:00+00:00")
    
    TRACE_ID: TZUTIL-BROKER-TIMESTAMP-001
    """
    dt_utc = broker_timestamp_to_utc_datetime(timestamp)
    return dt_utc.isoformat()
