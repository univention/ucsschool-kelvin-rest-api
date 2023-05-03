.. SPDX-FileCopyrightText: 2021-2023 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

.. _client_server_compat:

Python Client Compatibility
===========================

This page gives information about the compatible Kelvin client versions, which can be used along with the App installed on your server. External software using client versions below the listed ones will break and is not supported.

For more details about the changes, please visit read the  `Python client version history`_ and the changelog which is displayed during the upgrade of your *UCS\@school Kelvin REST API*.


.. New lines are added, if breaking changes are introduced by either a server or client version.

.. csv-table:: *UCS\@school Kelvin REST API* Client Compatibility
   :header: "Server Version", "Minimal Client Version"
   :escape: '

    "1.8.8", "2.2.2"
    "1.7.0", "1.7.0"
    "1.5.5", "1.6.0"

.. Also supported, but commented out to make the table easier to read.
..  "1.5.6", "1.5.1"


.. _`Python client version history`: https://kelvin-rest-api-client.readthedocs.io/en/latest/history.html
