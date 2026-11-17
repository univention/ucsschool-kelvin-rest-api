# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import logging
from collections.abc import Iterator

import pytest
from kelvin_connector.log import install_request_id_record_factory, request_id_context


@pytest.fixture
def restore_record_factory() -> Iterator[None]:
    factory = logging.getLogRecordFactory()
    yield
    logging.setLogRecordFactory(factory)


def _record() -> logging.LogRecord:
    return logging.getLogger("test").makeRecord("test", logging.INFO, "f.py", 1, "msg", (), None)


def test_records_get_the_request_id_of_the_context(restore_record_factory: None) -> None:
    install_request_id_record_factory()

    with request_id_context("req-1"):
        assert getattr(_record(), "request_id") == "req-1"
    assert not hasattr(_record(), "request_id")


def test_installing_the_record_factory_again_does_not_stack_it(restore_record_factory: None) -> None:
    install_request_id_record_factory()
    factory = logging.getLogRecordFactory()

    install_request_id_record_factory()

    assert logging.getLogRecordFactory() is factory
