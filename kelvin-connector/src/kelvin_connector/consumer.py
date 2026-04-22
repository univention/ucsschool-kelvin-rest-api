# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger
from typing_extensions import override

from .consumer_lib import AttributeMapping, ConsumerModule, QueryEventObject, UDMEventHandler

if TYPE_CHECKING:
    from loguru import Logger


class UnknownTopicException(Exception):
    pass


class KelvinConnectorEventHandler(UDMEventHandler):
    def __init__(self, logger: Logger, *args, **kwargs) -> None:
        super().__init__(logger, *args, **kwargs)

    def _is_school_object_event(self, event: QueryEventObject) -> bool:
        if event["topic"] not in ["users/user", "groups/group", "container/ou"]:
            raise UnknownTopicException()
        return "ucsschoolRole" in event["body"]["old"] or "ucsschoolRole" in event["body"]["new"]

    @override
    def handle_event(self, event: QueryEventObject) -> bool:
        try:
            if not self._is_school_object_event(event):
                return False
        except UnknownTopicException:
            self.logger.error("Unknown topic encountered")
            return False
        return super().handle_event(event)

    @override
    def _handle_create(self, metadata: AttributeMapping, new: AttributeMapping) -> None:
        """
        Called when a new object was created.

        :param str metadata: metadata of the create event
        :param dict new: new UDM objects attributes
        """
        print(metadata, new)

    @override
    def _handle_modify(
        self, metadata: AttributeMapping, old: AttributeMapping, new: AttributeMapping, has_moved: bool
    ) -> None:
        """
        Called when an existing object was modified or moved.

        A move can be be detected by looking at <has_moved>. Attributes can be
        modified during a move.

        :param str metadata: metadata of the modify event
        :param dict old: previous UDM objects attributes
        :param dict new: new UDM objects attributes
        """
        print(metadata, old, new, has_moved)

    @override
    def _handle_remove(self, metadata: AttributeMapping, old: AttributeMapping) -> None:
        """
        Called when an object was deleted.

        :param str metadata: metadata of the delete event
        :param dict old: previous UDM objects attributes
        """
        print(metadata, old)


def main():
    LDAP_SERVER_TYPE = os.environ.get("LDAP_SERVER_TYPE", None)
    if LDAP_SERVER_TYPE is None or LDAP_SERVER_TYPE != "master":
        logger.critical(f"Connector cannot run on {LDAP_SERVER_TYPE=}.")
        sys.exit(1)

    PROVISIONING_API_FQDN = os.environ.get("PROVISIONING_FQDN", None)
    if PROVISIONING_API_FQDN is None:
        logger.critical("Provisioning API FQDN is missing.")
        sys.exit(1)

    CONFIG_PATH = Path("/var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/conf/")

    event_handler = KelvinConnectorEventHandler(logger)
    consumer = ConsumerModule(
        event_handler,
        name="kelvin-connector",
        provisioning_url=f"https://{PROVISIONING_API_FQDN}/univention/provisioning",
        config_path=CONFIG_PATH,
    )

    consumer.loop()
