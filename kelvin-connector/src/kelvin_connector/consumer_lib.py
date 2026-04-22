# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only
from __future__ import annotations

import copy
import json
import os
import secrets
import sys
import time
import types
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    from loguru import Logger

import ldap
import loguru
import requests
from typing_extensions import override

AttributeMapping = Mapping[str, Any]
FN_CONFIG = "provisioning_config.json"
ERROR_TIMEOUT = 60  # sleep duration after failed provisioning queue access in seconds


class QueueAccessError(Exception):
    """
    Raised if access to provisioning queue fails.
    """

    pass


class Topics(TypedDict):
    realm: str
    topic: str


class QueryEventObject(TypedDict):
    publisher_name: str
    ts: str
    realm: str
    topic: str
    body: dict[str, Any]  # pyright: ignore[reportExplicitAny]
    sequence_number: int
    num_delivered: int


class SubscriptionError(Exception):
    """
    Raised when a subscription fails.
    """

    pass


class DN:  # TODO FIXME copied from univention-python (univention.DN)
    """A |LDAP| Distinguished Name."""

    _CASE_INSENSITIVE_ATTRIBUTES = {"cn", "uid", "dc", "ou", "c", "l", "o"}

    __slots__ = ("_dn", "_hash", "_str", "dn")

    def __init__(self, dn: str) -> None:
        self.dn = dn
        self._hash = None
        self._str = None
        try:
            self._dn = ldap.dn.str2dn(self.dn)
        except ldap.DECODING_ERROR:
            raise ValueError("Malformed DN syntax: %r" % (self.dn,))

    @property
    def rdn(self) -> tuple[str, str]:
        """
        >>> DN('foo=1,bar=2').rdn
        ('foo', '1')
        """
        return tuple(self._dn[0][0][:2])

    @override
    def __eq__(self, other: object) -> bool:
        """
        >>> DN('foo=1') == DN('foo=1')
        True
        >>> DN('foo=1') == DN('foo=2')
        False
        >>> DN('Foo=1') == DN('foo=1')
        True
        >>> DN('Foo=1') == DN('foo=2')
        False
        >>> DN('uid=Administrator') == DN('uid=administrator')
        True
        >>> DN('univentionAppID=Foo') == DN('univentionAppID=foo')
        False
        >>> DN('foo=1,bar=2') == DN('foo=1,bar=2')
        True
        >>> DN('bar=2,foo=1') == DN('foo=1,bar=2')
        False
        >>> DN('foo=1+bar=2') == DN('foo=1+bar=2')
        True
        >>> DN('bar=2+foo=1') == DN('foo=1+bar=2')
        True
        >>> DN('bar=2+Foo=1') == DN('foo=1+Bar=2')
        True
        >>> DN(r'foo=%s31' % chr(92)) == DN(r'foo=1')
        True
        """
        return hash(self) == hash(other)

    def __ne__(self, other: "DN") -> bool:
        return not self == other

    def __hash__(self) -> int:
        # compute hash only once - object is static
        if self._hash is None:
            self._hash = hash(
                tuple(
                    tuple(
                        sorted(
                            (
                                attr.lower(),
                                val.lower()
                                if attr.lower() in self._CASE_INSENSITIVE_ATTRIBUTES
                                else val,
                                ava,
                            )
                            for attr, val, ava in rdn
                        )
                    )
                    for rdn in self._dn
                )
            )
        return self._hash


class EventHandler:
    def __init__(self, logger: Logger, *args, **kwargs) -> None:
        self.logger: Logger = logger

    def handle_event(self, event: QueryEventObject) -> bool:
        """
        Calls the handler functions depending on the event type.

        :param dict[str, Any] event: event to be processed
        :return: If no exception is thrown by the handler functions, True is returned, else False
        """
        raise NotImplementedError()


class UDMEventHandler(EventHandler):
    @override
    def handle_event(self, event: QueryEventObject) -> bool:
        """
        Calls the handler functions depending on the event type.

        :param dict[str, Any] event: event to be processed
        :return: If no exception is thrown by the handler functions, True is returned, else False
        """
        metadata, old, new, has_moved = self._event_to_udm(event)
        try:
            if old and new:
                self._handle_modify(metadata, old, new, has_moved)
            elif old:
                self._handle_remove(metadata, old)
            else:
                self._handle_create(metadata, new)
        except SystemExit as e:
            raise e
        except Exception as e:  # noqa: E722,F841
            exc_type, exc_value, exc_traceback = sys.exc_info()
            self._error_handler(metadata, old, new, exc_type, exc_value, exc_traceback)
            return False
        return True

    @classmethod
    def _event_to_udm(
        cls, event: QueryEventObject
    ) -> tuple[AttributeMapping, AttributeMapping, AttributeMapping, bool]:
        """
        Converts the event to UDM data objects metadata, old and new.
        :param dict[str, Any] event: the event to be converted
        :returns: metadata, old, new
        :rtype: tuple[AttributeMapping, AttributeMapping, AttributeMapping]
        """
        metadata = copy.deepcopy(event)
        del metadata["body"]
        old = event["body"]["old"]
        new = event["body"]["new"]
        has_moved = False
        if old and new:
            old_dn = DN(old["dn"])
            new_dn = DN(new["dn"])
            has_moved = old_dn != new_dn
        return metadata, old, new, has_moved

    def _handle_create(self, metadata: AttributeMapping, new: AttributeMapping) -> None:
        """
        Called when a new object was created.

        :param str metadata: metadata of the create event
        :param dict new: new UDM objects attributes
        """
        raise NotImplementedError

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
        raise NotImplementedError

    def _handle_remove(self, metadata: AttributeMapping, old: AttributeMapping) -> None:
        """
        Called when an object was deleted.

        :param str metadata: metadata of the delete event
        :param dict old: previous UDM objects attributes
        """
        raise NotImplementedError

    def _error_handler(
        self,
        metadata: AttributeMapping,
        old: AttributeMapping,
        new: AttributeMapping,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        exc_traceback: types.TracebackType | None,
    ) -> None:
        """
        Will be called for unhandled exceptions in create/modify/remove.

        :param str metadata: current events metadata
        :param dict old: previous UDM objects attributes
        :param dict new: new UDM objects attributes
        :param type exc_type: exception class
        :param BaseException exc_value: exception object
        :param traceback exc_traceback: traceback object
        """
        assert exc_value is not None
        self.logger.exception("metadata=%r\n    old=%r\n    new=%r", metadata, old, new)  # noqa: LOG004
        raise exc_value.with_traceback(exc_traceback)

    @classmethod
    def diff(
        cls, event: QueryEventObject, keys: Iterable[str] | None = None
    ) -> dict[str, tuple[Any, Any]]:
        """
        Find differences in old and new. Returns dict with keys pointing to old
        and new values.

        :param dict old: previous UDM objects attributes
        :param dict new: new UDM objects attributes
        :param list keys: consider only those keys in comparison
        :return: key -> (old[key], new[key]) mapping
        :rtype: dict
        """
        _, old, new, _ = cls._event_to_udm(event)
        res = {}
        if keys:
            keyset = set(keys)
        else:
            keyset = set(old) | set(new)
        for key in keyset:
            if set(old.get(key, [])) != set(new.get(key, [])):
                res[key] = old.get(key), new.get(key)
        return res


class ConsumerModule:
    def __init__(self, handler: EventHandler, *args, **kwargs):
        """
        ConsumerModule
        :param EventHandler handler:
        :param kwargs:
           str config_path: path to configuration file
           str name: name of the consumer (has to be unique)
           str provisioning_url: url of provisioning service
               (e.g. "https://FQDN-OF-PRIMARY/univention/provisioning/")
        """
        self.handler: EventHandler = handler
        self.config = kwargs
        self.check_config()
        self.logger: Logger = loguru.logger
        self.logger.info(f"Starting consumer {self.config['name']}")
        self.session: requests.Session = requests.Session()
        self.session.verify = False
        self.subscription_name: str | None
        self.subscription_password: str | None
        self.subscription_name, self.subscription_password = self._get_subscription_credentials()

    def check_config(self):
        assert isinstance(self.config.get("name"), str) and self.config.get("name")
        self.config["config_path"] = os.path.abspath(
            self.config.get("config_path", "/var/lib/univention/consumer")
        ).rstrip("/")
        assert self.config["config_path"]
        assert self.config.get("provisioning_url") is not None

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}({self.config})"

    def _get_subscription_credentials(self) -> tuple[str | None, str | None]:
        """
        Get subscription credentials from configuration file.
        :returns: (name, password)
            name and password are None if configuration file could
            not be found or values are unset.
        """
        fn = os.path.join(self.config["config_path"], FN_CONFIG)
        if os.path.isfile(fn):
            with open(fn) as fd:
                data = json.load(fd)
                if "subscription_name" in data and "subscription_password" in data:
                    self.logger.debug(f"Read configuration file {fn}")
                    return data["subscription_name"], data["subscription_password"]
                self.logger.warning(
                    (
                        f"Read configuration file {fn} but no "
                        "subscription_name or subscription_password was found"
                    )
                )
        else:
            self.logger.info(f"No configuration file {fn} found")
        return None, None

    def _save_subscription_credentials(self, name: str, password: str) -> None:
        """
        Save given subscription name and password to configuration file.
        """
        data = {
            "subscription_name": name,
            "subscription_password": password,
        }
        fn = os.path.join(self.config["config_path"], FN_CONFIG)
        fn_new = f"{fn}.new"
        fd = os.open(fn_new, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, indent=2)
        os.rename(fn_new, fn)

    def subscribe(
        self, admin_username: str, admin_password: str, topics: list[Topics], prefill: bool = True
    ) -> None:
        """
        Creates a new subscription for the configured realm and topics at the provisioning service.
        It requires a special secret that is only accessible
        by domain administrators of the Nubus domain.

        :param str admin_username: administrator's username of provisioning service
        :param str admin_password: administrator's password of provisioning service
        :param list[dict[str, str]] topics: list of realms and topics to subscribe to
            e.g.:
            topics = [
                {"realm": "udm", "topic": "users/user"},
                {"realm": "udm", "topic": "groups/group"}
            ]
        :param bool prefill: whether to prefill the subscription queue after initial registration
        :raises: SubscriptionError in case of failure
        """
        self.subscription_name, self.subscription_password = self._get_subscription_credentials()
        if not self.subscription_name or not self.subscription_password:
            self.subscription_name = f"{self.config['name']}-{secrets.token_hex(16)}"
            self.subscription_password = secrets.token_urlsafe(32)

        create_sub_json = {
            "name": self.subscription_name,
            "realms_topics": topics,
            "request_prefill": prefill,
            "password": self.subscription_password,
        }
        resp = self.session.post(
            self.config["provisioning_url"] + "/v1/subscriptions",
            json=create_sub_json,
            auth=(admin_username, admin_password),
        )
        if not (200 <= resp.status_code <= 299):
            self.logger.error(
                f"Subscription request failed with error code {resp.status_code}: {resp.text}"
            )
            raise SubscriptionError(resp.text)

        self._save_subscription_credentials(self.subscription_name, self.subscription_password)

    def loop(self):
        """
        Endless loop
        """
        self.logger.debug("Starting consumer loop...")
        while True:
            try:
                self.step()
            except QueueAccessError as e:
                self.logger.critical(f"Unable to access provisioning queue: {e}")
                self.logger.error(f"Sleeping {ERROR_TIMEOUT}s before continuing")
                time.sleep(ERROR_TIMEOUT)

    def step(self, long_polling_timeout: int = 10):
        """
        Fetch next event from provisioning queue. If there is no waiting event in the subscribed queue,
        the request does long polling. It either times out after the given number of seconds or
        directly returns if the next events is pushed to the queue.
        :param int long_polling_timeout: number of seconds
            to wait for new events in case the queue is empty
        :return: None
        :raise: QueueAccessError is raised, in case the
                access to the queue is denied or credentials are missing.
        """
        event = self._fetch_event(long_polling_timeout)
        if event:
            if self.handler.handle_event(event):
                self._acknowledge_event(event)
        else:
            # If the queue is empty, it uses long polling
            # with a default timeout of <long_polling_timeout> seconds,
            # for immediate notification of new changes.
            self.logger.debug("Long polling timeout, no more events.")

    def _fetch_event(self, long_polling_timeout: int) -> QueryEventObject | None:
        """
        Fetch next item from queue.
        :return: event dictionary
        :rtype: dict
        :raise: QueueAccessError
        """
        if not self.subscription_name or not self.subscription_password:
            raise QueueAccessError("No subscription name or password")
        resp = self.session.get(
            f"{self.config['provisioning_url']}/v1/subscriptions/{self.subscription_name}/messages/next",
            params={"timeout": long_polling_timeout},
            auth=(self.subscription_name, self.subscription_password),
        )
        if resp.status_code != 200:
            raise QueueAccessError(resp.text)
        return resp.json()

    def _acknowledge_event(self, event: QueryEventObject) -> None:
        """
        Acknowledge specified event at provisioning service.
        :param event: the event to be acknowledged
        :return: None
        """
        assert self.subscription_name is not None
        assert self.subscription_password is not None
        seq_num = event["sequence_number"]
        status_json = {"status": "ok"}
        self.logger.debug(f"Acknowledging event {seq_num}")
        response = self.session.patch(
            (
                f"{self.config['provisioning_url']}/v1/"
                f"subscriptions/{self.subscription_name}/messages/{seq_num}/status"
            ),
            json=status_json,
            auth=(self.subscription_name, self.subscription_password),
        )
        if response.status_code != 200:
            self.logger.error(f"Acknowledging event {seq_num} failed: {response.text}")
