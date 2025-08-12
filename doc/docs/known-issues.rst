.. SPDX-FileCopyrightText: 2021-2023 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Known Issues
============

Rebuilding the UDM REST API Client
----------------------------------
The *UCS\@school Kelvin REST API* server connects to the :ref:`UDM REST API <udm-rest-api>` in :cite:t:`uv-developer-reference` server to execute modifications of the LDAP database.
So the *UCS\@school Kelvin REST API* server is itself a *client* of the UDM REST API.
The `Python UDM REST API Client`_ library is used for communication with the UDM REST API.

The UDM REST API does also provide an OpenAPI schema.
A part of the Python UDM REST API Client library is auto-generated from it using the *OpenAPI Generator* mentioned above.

.. warning::
    Whenever a new UDM module, extended option or extended attribute is installed, the *OpenAPI client* library used by the Python UDM REST API Client library **must** be rebuild to be able to access the new module/attribute.

Although the *OpenAPI client* library rebuild is automatically triggered, because of :uv:bug:`50253` the UDM REST API server will not have been reloaded.
This will prevent the changes to be incorporated into the UDM REST client of the UCS\@school Kelvin REST API server.

**It is thus necessary to rebuild the OpenAPI client manually.**

This can be done with the following commands:

.. code-block:: console

    $ systemctl restart univention-directory-manager-rest.service
    $ univention-app shell ucsschool-kelvin-rest-api /var/lib/univention-appcenter/apps/ucsschool-kelvin-rest-api/data/update_openapi_client
    $ univention-app restart ucsschool-kelvin-rest-api


No pagination
-------------
Pagination of resource collections has not yet been implemented.
When it is, there will be `Python UDM REST API Client`_ entries in the response ``headers``.
The format of the JSON response in the *body will not change*.

.. _Python UDM REST API Client: https://github.com/univention/python-udm-rest-api-client


Creating schools does not work in single server environments
------------------------------------------------------------
A bug exists for this, see :uv:bug:`55506`.
