import logging
from functools import partial

from fastapi import FastAPI

from ucsschool.lib.models.utils import env_or_ucr, get_stdout_handler
from ucsschool.lib.models.validator import VALIDATION_LOGGER

from ..config import UDM_MAPPING_CONFIG, load_configurations
from ..constants import DEFAULT_LOG_LEVELS
from ..import_config import get_import_config


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


def load_configs(logger: logging.Logger) -> None:
    load_configurations()
    logger.info("UDM mapping configuration: %s", UDM_MAPPING_CONFIG)


def log_version(app: FastAPI, logger: logging.Logger) -> None:
    logger.info("Started %s version %s.", app.title, app.version)


def add_event_handlers(app: FastAPI, logger: logging.Logger) -> None:
    app.add_event_handler("startup", setup_logging)
    app.add_event_handler("startup", partial(load_configs, logger=logger))
    app.add_event_handler("startup", get_import_config)
    app.add_event_handler("startup", partial(log_version, app=app, logger=logger))
