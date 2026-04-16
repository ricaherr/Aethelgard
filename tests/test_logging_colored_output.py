"""
Tests para utils/logging_utils.py — Sistema de Logging Visual con Colores
ETI: Logging_Visual_Colors_2026-04-16
Cubre: ColoredConsoleFormatter, niveles custom, _colors_supported, setup_logging, get_logger.
"""
import logging
import os
import pytest

from utils.logging_utils import (
    AUDIT_LEVEL,
    SUCCESS_LEVEL,
    ColoredConsoleFormatter,
    _colors_supported,
    get_logger,
    setup_logging,
)

# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_record(level: int, message: str = "test") -> logging.LogRecord:
    """Crea un LogRecord mínimo para pruebas unitarias."""
    return logging.LogRecord(
        name="test", level=level, pathname="", lineno=0,
        msg=message, args=(), exc_info=None,
    )


# ── ColoredConsoleFormatter ──────────────────────────────────────────────────

class TestColoredConsoleFormatter:
    def test_debug_contiene_cyan(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.DEBUG, "debug msg"))
        assert "\033[36m" in result  # Fore.CYAN

    def test_info_contiene_blue(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.INFO, "info msg"))
        assert "\033[34m" in result  # Fore.BLUE

    def test_success_contiene_green(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(SUCCESS_LEVEL, "ok"))
        assert "\033[32m" in result  # Fore.GREEN

    def test_warning_contiene_yellow(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.WARNING, "warn"))
        assert "\033[33m" in result  # Fore.YELLOW

    def test_audit_contiene_magenta(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(AUDIT_LEVEL, "audit"))
        assert "\033[35m" in result  # Fore.MAGENTA

    def test_error_contiene_red(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.ERROR, "err"))
        assert "\033[31m" in result  # Fore.RED

    def test_critical_contiene_red(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.CRITICAL, "critical"))
        assert "\033[31m" in result  # Fore.RED

    def test_sin_colores_no_tiene_ansi(self):
        fmt = ColoredConsoleFormatter(use_colors=False)
        result = fmt.format(_make_record(logging.ERROR, "no color"))
        assert "\033[" not in result

    def test_mensaje_preservado_sin_colores(self):
        fmt = ColoredConsoleFormatter(use_colors=False)
        result = fmt.format(_make_record(logging.INFO, "hello world"))
        assert "hello world" in result

    def test_mensaje_preservado_con_colores(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.INFO, "hello world"))
        assert "hello world" in result

    def test_reset_code_appended_con_colores(self):
        fmt = ColoredConsoleFormatter(use_colors=True)
        result = fmt.format(_make_record(logging.INFO, "msg"))
        assert "\033[0m" in result  # Style.RESET_ALL


# ── Niveles custom ───────────────────────────────────────────────────────────

class TestNivelesCustom:
    def test_success_level_value(self):
        assert SUCCESS_LEVEL == 25

    def test_audit_level_value(self):
        assert AUDIT_LEVEL == 35

    def test_success_level_name(self):
        assert logging.getLevelName(SUCCESS_LEVEL) == "SUCCESS"

    def test_audit_level_name(self):
        assert logging.getLevelName(AUDIT_LEVEL) == "AUDIT"

    def test_success_entre_info_y_warning(self):
        assert logging.INFO < SUCCESS_LEVEL < logging.WARNING

    def test_audit_entre_warning_y_error(self):
        assert logging.WARNING < AUDIT_LEVEL < logging.ERROR


# ── _colors_supported ────────────────────────────────────────────────────────

class TestColorsSupported:
    def test_no_color_env_desactiva(self, monkeypatch):
        monkeypatch.setenv("NO_COLOR", "1")
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_NO_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_FORCE_COLOR", raising=False)
        assert _colors_supported() is False

    def test_aethelgard_no_color_desactiva(self, monkeypatch):
        monkeypatch.setenv("AETHELGARD_NO_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_FORCE_COLOR", raising=False)
        assert _colors_supported() is False

    def test_force_color_env_activa(self, monkeypatch):
        monkeypatch.setenv("FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_NO_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_FORCE_COLOR", raising=False)
        assert _colors_supported() is True

    def test_aethelgard_force_color_activa(self, monkeypatch):
        monkeypatch.setenv("AETHELGARD_FORCE_COLOR", "1")
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        assert _colors_supported() is True

    def test_no_tty_devuelve_false(self, monkeypatch):
        monkeypatch.delenv("NO_COLOR", raising=False)
        monkeypatch.delenv("FORCE_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_NO_COLOR", raising=False)
        monkeypatch.delenv("AETHELGARD_FORCE_COLOR", raising=False)
        # En CI/pytest stdout no es TTY → debe devolver False
        import sys
        original_isatty = getattr(sys.stdout, "isatty", None)
        sys.stdout.isatty = lambda: False  # type: ignore[method-assign]
        try:
            result = _colors_supported()
        finally:
            if original_isatty is not None:
                sys.stdout.isatty = original_isatty  # type: ignore[method-assign]
        assert result is False


# ── setup_logging ────────────────────────────────────────────────────────────

class TestSetupLogging:
    def _get_and_reset(self, original_handlers):
        """Restaura handlers del root logger tras el test."""
        root = logging.getLogger()
        root.handlers = original_handlers

    def test_agrega_stream_y_file_handler(self, tmp_path):
        root = logging.getLogger()
        original = root.handlers[:]
        try:
            setup_logging(log_file=str(tmp_path / "test.log"), use_colors=False)
            nombres = [type(h).__name__ for h in root.handlers]
            assert "StreamHandler" in nombres
            assert "TimedRotatingFileHandler" in nombres
        finally:
            root.handlers = original

    def test_file_handler_no_tiene_color_formatter(self, tmp_path):
        root = logging.getLogger()
        original = root.handlers[:]
        try:
            setup_logging(log_file=str(tmp_path / "test.log"), use_colors=True)
            file_handlers = [h for h in root.handlers if hasattr(h, "baseFilename")]
            assert file_handlers, "Debe existir al menos un file handler"
            fmt = file_handlers[0].formatter
            assert not isinstance(fmt, ColoredConsoleFormatter)
        finally:
            root.handlers = original

    def test_stream_handler_tiene_color_formatter(self, tmp_path):
        root = logging.getLogger()
        original = root.handlers[:]
        try:
            setup_logging(log_file=str(tmp_path / "test.log"), use_colors=True)
            stream_handlers = [
                h for h in root.handlers
                if isinstance(h, logging.StreamHandler) and not hasattr(h, "baseFilename")
            ]
            assert stream_handlers, "Debe existir al menos un stream handler"
            assert isinstance(stream_handlers[0].formatter, ColoredConsoleFormatter)
        finally:
            root.handlers = original

    def test_crea_directorio_de_log(self, tmp_path):
        nested = tmp_path / "deep" / "dir" / "test.log"
        root = logging.getLogger()
        original = root.handlers[:]
        try:
            setup_logging(log_file=str(nested), use_colors=False)
            assert nested.parent.exists()
        finally:
            root.handlers = original

    def test_nivel_root_configurado(self, tmp_path):
        root = logging.getLogger()
        original = root.handlers[:]
        original_level = root.level
        try:
            setup_logging(level=logging.DEBUG, log_file=str(tmp_path / "test.log"), use_colors=False)
            assert root.level == logging.DEBUG
        finally:
            root.handlers = original
            root.setLevel(original_level)


# ── get_logger ───────────────────────────────────────────────────────────────

class TestGetLogger:
    def test_retorna_logger_con_nombre_correcto(self):
        logger = get_logger("aethelgard.test")
        assert logger.name == "aethelgard.test"

    def test_es_instancia_logging_logger(self):
        logger = get_logger("some.module")
        assert isinstance(logger, logging.Logger)

    def test_mismo_nombre_misma_instancia(self):
        a = get_logger("shared.module")
        b = get_logger("shared.module")
        assert a is b
