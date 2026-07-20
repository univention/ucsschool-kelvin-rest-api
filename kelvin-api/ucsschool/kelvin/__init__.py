# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only


def get_version() -> str:
    import os
    import re
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version("ucsschool-kelvin-rest-api")  # Use the package name from pyproject.toml
    except PackageNotFoundError:
        pattern = re.compile(r"\d+\.\d+\.\d+")
        match = pattern.search(str(os.environ.get("KELVIN_BUILD_VERSION", "0.0.0")))
        if not match:
            return "0.0.0"
        return match.group()
