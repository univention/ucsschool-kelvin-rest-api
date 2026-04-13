# -*- coding: utf-8 -*-

# SPDX-FileCopyrightText: 2026 Univention GmbH
# SPDX-License-Identifier: AGPL-3.0-only

import sys

from univention.config_registry import main


def run_ucr():
    main(sys.argv[1:])
