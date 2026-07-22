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


Where ``v2`` reads can be slower than ``v1``
--------------------------------------------
The ``v2`` read and search endpoints (``GET``, ``HEAD``) answer from a local, pre-replicated
database instead of querying the :ref:`UDM REST API <udm-rest-api>` and LDAP directly.
For most resources (listing or fetching users, classes, workgroups, and schools) this is
considerably faster than ``v1``.

There are, however, a few endpoints where ``v2`` is *slower* than ``v1``:

* listing roles (``GET /roles/``) and retrieving a single role (``GET /roles/{name}``), and
* checking a school for existence (``HEAD /schools/{name}``).

Under typical situations, the absolute response times for these endpoints remain small,
and the difference is only noticeable in direct ``v1``-versus-``v2`` comparisons.


Kelvin connector log level cannot be adjusted
---------------------------------------------
The log level of the Kelvin connector, which keeps the version 2 database in sync, cannot
be adjusted yet.


No indicator for the initial synchronization
--------------------------------------------
After installing or upgrading to Kelvin 4.0.0, the Kelvin connector performs an initial
synchronization of all existing schools, groups, and users into the database that backs the
version 2 API (see :ref:`upgrade-to-4`). There is no dedicated way yet to check
whether this initial synchronization has finished.

As a workaround, either:

* create a new user and wait until it appears in the version 2 API. Because the
  synchronization is ordered, all previously existing objects are present once the new user
  shows up; or
* watch the connector logs and wait until log activity subsides:

  .. code-block:: console

      $ docker logs ucsschool-kelvin-rest-api_provisioning_1
