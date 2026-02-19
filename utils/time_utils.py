from datetime import datetime, timezone
try:
    from zoneinfo import ZoneInfo
except ImportError:
    from pytz import timezone as ZoneInfo

def to_utc(dt, source_tz=None) -> str:
    """
    Convierte un datetime o string a UTC ISO 8601 (YYYY-MM-DD HH:MM:SS.SSS) para almacenamiento.
    source_tz puede ser string (ej: 'Europe/Madrid') o None (asume UTC o naive local).
    """
    if isinstance(dt, str):
        # Intentar parsear string a datetime
        try:
            if 'T' in dt:
                dt = dt.replace('T', ' ')
            if '.' in dt:
                base, ms = dt.split('.')
                ms = ms[:3]  # Solo milisegundos
                dt = f"{base}.{ms}"
                fmt = '%Y-%m-%d %H:%M:%S.%f'
            else:
                fmt = '%Y-%m-%d %H:%M:%S'
            dt = datetime.strptime(dt, fmt)
        except Exception:
            raise ValueError(f"Formato de fecha no soportado: {dt}")
    if dt.tzinfo is None:
        if source_tz:
            try:
                dt = dt.replace(tzinfo=ZoneInfo(source_tz))
            except Exception:
                raise ValueError(f"Zona horaria inválida: {source_tz}")
        else:
            dt = dt.replace(tzinfo=timezone.utc)
    dt_utc = dt.astimezone(timezone.utc)
    return dt_utc.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]  # Milisegundos, sin microsegundos
