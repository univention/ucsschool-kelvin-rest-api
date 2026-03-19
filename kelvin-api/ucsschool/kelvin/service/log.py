import logging

from ucsschool.lib.models.utils import env_or_ucr, get_stdout_handler
from ucsschool.lib.models.validator import VALIDATION_LOGGER

from ..constants import DEFAULT_LOG_LEVELS


class ValidationDataFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.name != VALIDATION_LOGGER


def setup_logging() -> None:
    min_level = env_or_ucr("ucsschool/kelvin/log_level")
    if min_level not in ("DEBUG", "INFO", "WARNING", "ERROR"):
        min_level = logging.ERROR
    min_level = logging._checkLevel(min_level)
    abs_min_level = min_level
    for name, default_level in DEFAULT_LOG_LEVELS.items():
        module_logger = logging.getLogger(name)
        module_logger.setLevel(min(default_level, min_level))
        abs_min_level = min(abs_min_level, module_logger.level)

    file_handler = get_stdout_handler(abs_min_level)
    file_handler.addFilter(ValidationDataFilter())
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addHandler(file_handler)
    root_logger = logging.getLogger()
    root_logger.setLevel(abs_min_level)
    root_logger.addHandler(file_handler)
