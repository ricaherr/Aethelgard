"""
Aethelgard Logging Utilities — Visual Console Formatter
========================================================
Proporciona salida de log con código de color por severidad (colorama).
Los colores se aplican solo al handler de consola; el handler de archivo
siempre escribe texto plano (sin códigos ANSI).

Detección automática de soporte de color:
- NO_COLOR / AETHELGARD_NO_COLOR → desactiva colores
- FORCE_COLOR / AETHELGARD_FORCE_COLOR → fuerza colores
- En otro caso: TTY check en sys.stdout

Niveles custom registrados:
- SUCCESS (25) — entre INFO y WARNING → Verde
- AUDIT   (35) — entre WARNING y ERROR → Magenta
"""
import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import Optional

from colorama import Fore, Style, init as _colorama_init

# Inicializar colorama una sola vez (habilita emulación ANSI en Windows)
_colorama_init(autoreset=False)

# ── Niveles custom ───────────────────────────────────────────────────────────
SUCCESS_LEVEL: int = 25  # INFO (20) < SUCCESS < WARNING (30)
AUDIT_LEVEL: int = 35    # WARNING (30) < AUDIT < ERROR (40)

logging.addLevelName(SUCCESS_LEVEL, "SUCCESS")
logging.addLevelName(AUDIT_LEVEL, "AUDIT")

# ── Mapeo severidad → color ANSI ─────────────────────────────────────────────
_LEVEL_COLORS: dict[int, str] = {
    logging.DEBUG:    Fore.CYAN,
    logging.INFO:     Fore.BLUE,
    SUCCESS_LEVEL:    Fore.GREEN,
    logging.WARNING:  Fore.YELLOW,
    AUDIT_LEVEL:      Fore.MAGENTA,
    logging.ERROR:    Fore.RED,
    logging.CRITICAL: Fore.RED + Style.BRIGHT,
}

_BASE_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


# ── Formatter ────────────────────────────────────────────────────────────────
class ColoredConsoleFormatter(logging.Formatter):
    """
    Formatter que añade códigos ANSI al inicio de cada línea según la severidad.

    Si use_colors=False (o al usarse con un FileHandler) la salida es texto plano.
    """

    def __init__(self, fmt: str = _BASE_FORMAT, use_colors: bool = True) -> None:
        super().__init__(fmt=fmt)
        self._use_colors = use_colors

    def format(self, record: logging.LogRecord) -> str:
        message = super().format(record)
        if not self._use_colors:
            return message
        color = _LEVEL_COLORS.get(record.levelno, "")
        if not color:
            return message
        return f"{color}{message}{Style.RESET_ALL}"


# ── Auto-detección de soporte ANSI ───────────────────────────────────────────
def _colors_supported() -> bool:
    """
    Devuelve True cuando el entorno soporta códigos ANSI en consola.

    Precedencia (de mayor a menor):
    1. NO_COLOR / AETHELGARD_NO_COLOR → False
    2. FORCE_COLOR / AETHELGARD_FORCE_COLOR → True
    3. sys.stdout.isatty() → True/False
    """
    if os.environ.get("NO_COLOR") or os.environ.get("AETHELGARD_NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR") or os.environ.get("AETHELGARD_FORCE_COLOR"):
        return True
    return hasattr(sys.stdout, "isatty") and bool(sys.stdout.isatty())


# ── Inicialización del logging ───────────────────────────────────────────────
def setup_logging(
    level: int = logging.INFO,
    log_file: str = "logs/main.log",
    use_colors: Optional[bool] = None,
) -> None:
    """
    Configura el logger raíz con dos handlers:

    - StreamHandler (consola): usa ColoredConsoleFormatter con colores detectados.
    - TimedRotatingFileHandler (archivo): usa Formatter plano, sin ANSI.

    Reemplaza cualquier configuración previa (handlers del root logger se limpian).

    Args:
        level:      Nivel mínimo de logging (por defecto INFO).
        log_file:   Ruta al archivo de log rotativo.
        use_colors: Sobreescribe la auto-detección. None = auto (TTY check).
    """
    if use_colors is None:
        use_colors = _colors_supported()

    Path(log_file).parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    # Handler de consola — con colores opcionales
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(ColoredConsoleFormatter(use_colors=use_colors))
    root.addHandler(console_handler)

    # Handler de archivo — siempre texto plano
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",
        interval=1,
        backupCount=15,
        encoding="utf-8",
    )
    file_handler.setFormatter(logging.Formatter(_BASE_FORMAT))
    root.addHandler(file_handler)


# ── Factory de loggers ────────────────────────────────────────────────────────
def get_logger(name: str) -> logging.Logger:
    """Devuelve un logger con nombre usando la configuración del logger raíz."""
    return logging.getLogger(name)
