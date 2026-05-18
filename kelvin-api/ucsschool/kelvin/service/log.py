import logging

from ucsschool.lib.models.utils import env_or_ucr, get_stdout_handler
from ucsschool.lib.models.validator import VALIDATION_LOGGER

from ..constants import DEFAULT_LOG_LEVELS


class ValidationDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name != VALIDATION_LOGGER


class HealthEndpointFilter(logging.Filter):
    """Suppress /health access log entries unless DEBUG logging is active."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.args, tuple) and len(record.args) >= 3 and record.args[2] == "/health":
            return logging.getLogger("uvicorn.access").isEnabledFor(logging.DEBUG)
        return True


def setup_logging() -> None:
    min_level = env_or_ucr("ucsschool/kelvin/log_level")
    if min_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        min_level = logging.ERROR
    min_level = logging._checkLevel(min_level)
    abs_min_level = min_level
    for name, default_level in DEFAULT_LOG_LEVELS.items():
        module_logger = logging.getLogger(name)
        if default_level >= logging.WARNING:
            # Noisy third-party libraries: default is a floor, never go more verbose than it
            level = max(default_level, min_level)
        else:
            # Application loggers: follow the global min_level
            level = min(default_level, min_level)
        module_logger.setLevel(level)
        abs_min_level = min(abs_min_level, module_logger.level)

    file_handler = get_stdout_handler(abs_min_level)
    file_handler.addFilter(ValidationDataFilter())
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addFilter(HealthEndpointFilter())
    access_logger.addHandler(file_handler)
    root_logger = logging.getLogger()
    root_logger.setLevel(abs_min_level)
    root_logger.addHandler(file_handler)
