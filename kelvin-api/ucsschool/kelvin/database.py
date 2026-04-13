# -*- coding: utf-8 -*-

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import os
from pathlib import Path

from sqlalchemy import make_url
from sqlalchemy.engine.url import URL

from ucsschool.lib.models.utils import env_or_ucr


def get_database_url() -> URL:
    sqlalchemy_url = make_url(env_or_ucr("ucsschool/kelvin/db/uri")).set(
        username=env_or_ucr("ucsschool/kelvin/db/username"),
        password=Path(
            os.getenv(
                "UCSSCHOOL_KELVIN_DB_PASSWORDFILE", "/etc/ucsschool/kelvin/postgresql-kelvin.secret"
            )
        )
        .read_text()
        .strip(),
    )

    if sqlalchemy_url.drivername == "postgresql":
        sqlalchemy_url = sqlalchemy_url.set(drivername="postgresql+psycopg")
    return sqlalchemy_url
