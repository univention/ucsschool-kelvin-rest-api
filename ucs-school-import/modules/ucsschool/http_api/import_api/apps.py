# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

"""
App registry
"""

from __future__ import unicode_literals

from django.apps import AppConfig


class HttpApiConfig(AppConfig):
    name = "import_api"
    verbose_name = "UCS@school import API"
