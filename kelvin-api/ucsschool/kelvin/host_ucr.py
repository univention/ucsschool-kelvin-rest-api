# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import argparse
import logging
import os
from collections.abc import Iterable, Mapping, Sequence

from univention.config_registry.backend import ConfigRegistry, ReadOnlyConfigRegistry

HOST_UCR_DIR = "/host-ucr"
HOST_UCR_SOURCE_DIR = "/etc/univention"
SKIP_SYNC_ENV = "SKIP_UCSSCHOOL_KELVIN_HOST_UCR_SYNC"

SYNCED_PREFIXES = (
    "groups/default/",
    "ucsschool/import/",
    "ucsschool/ldap/",
    "ucsschool/validation/",
    "users/default/",
)
SYNCED_KEYS = frozenset(
    {
        "dhcpd/ldap/base",
        "ldap/server/name",
        "ldap/server/port",
        "mail/hosteddomains",
        "ucsschool/default/share/nfs",
        "ucsschool/local/oulist",
        "ucsschool/singlemaster",
        "ucsschool/username/max_length",
    }
)

logger = logging.getLogger(__name__)


class HostUcrError(Exception):
    pass


class HostConfigRegistry(ReadOnlyConfigRegistry):
    PREFIX: str = HOST_UCR_DIR

    def __init__(self) -> None:
        missing = [
            name
            for name in sorted(self.BASES.values())
            if not os.path.isfile(os.path.join(self.PREFIX, name))
        ]
        if missing:
            raise HostUcrError(
                f"Host UCR files are missing or aren't regular files below {self.PREFIX}:"
                f" {', '.join(missing)}. On the host, remove any directory of that name in"
                f" {HOST_UCR_SOURCE_DIR}, run 'ucr dump' to recreate the files, and restart the app."
            )
        super().__init__()


def is_synced(key: str) -> bool:
    return key in SYNCED_KEYS or key.startswith(SYNCED_PREFIXES)


def synced_keys(*registries: Iterable[str]) -> list[str]:
    keys = set(SYNCED_KEYS)
    for registry in registries:
        keys.update(key for key in registry if is_synced(key))
    return sorted(keys)


def diff(host: Mapping[str, str], container: Mapping[str, str]) -> dict[str, str | None]:
    return {
        key: host.get(key) for key in synced_keys(host, container) if host.get(key) != container.get(key)
    }


def load_host(host: ReadOnlyConfigRegistry) -> None:
    try:
        host.load()
    except UnicodeDecodeError as exc:
        raise HostUcrError(f"Host UCR files in {host.PREFIX} aren't valid UTF-8: {exc}") from exc
    if not host.get("ldap/base"):
        raise HostUcrError(
            f"Host UCR files in {host.PREFIX} are unreadable or truncated: 'ldap/base' is not set"
        )


def sync(host: ReadOnlyConfigRegistry, container: ConfigRegistry) -> dict[str, str | None]:
    load_host(host)
    container.lock()
    try:
        container.load()
        changes = diff(host, container)
        if changes:
            container.update(changes)
            container.save()
    finally:
        container.unlock()
    for key, value in changes.items():
        logger.info("%s: %s", key, "unset" if value is None else repr(value))
        if container.get(key) != value:
            logger.warning(
                "%s: container value %r is shadowed by a container UCR layer other than 'normal'",
                key,
                container.get(key),
            )
    logger.info("Synced %d UCR variable(s) from the host.", len(changes))
    return changes


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Sync the Kelvin-relevant UCR variables of the Docker host into the container.",
        epilog=f"Set {SKIP_SYNC_ENV}=true to skip the sync, for example to start Kelvin while it fails.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        dest="list_keys",
        help="print the synced UCR variable names and exit",
    )
    list_keys = parser.parse_args(argv).list_keys
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not list_keys and os.environ.get(SKIP_SYNC_ENV) == "true":
        logger.warning("Skipped syncing the host UCR variables, because %s is 'true'.", SKIP_SYNC_ENV)
        return 0
    try:
        host = HostConfigRegistry()
        container = ConfigRegistry()
        if list_keys:
            load_host(host)
            container.load()
            print("\n".join(synced_keys(host, container)))
        else:
            sync(host, container)
    except (HostUcrError, OSError) as exc:
        logger.error("Syncing the host UCR variables failed: %s", exc)
        return 1
    return 0
