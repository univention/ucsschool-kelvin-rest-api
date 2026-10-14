.. SPDX-FileCopyrightText: 2021-2023 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Resources
=========

Resources may support a varying range of operations: retrieve, search, create, modify, move and delete.

Requests to resource endpoints must carry a valid token.
Section :ref:`install-and-config` describes how to obtain one.
Sending no or an invalid token leads to the server responding with HTTP status ``401``.

The token must be in the ``Authorization`` header with a value ``Bearer <token>``. E.g.::

    "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...."

When objects are loaded that are called by the **UDM Rest API**, the expected properties of the corresponding UCS\@school object are checked
and errors are logged. The output of the complete object as well as the stack trace are written to :file:`ucs-school-validation.log`.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   resource-roles
   resource-schools
   resource-users
   resource-classes
   resource-workgroups

Pagination
----------

The searches of the version 2 API return their results page by page
when you add the ``limit`` parameter,
for example ``GET /ucsschool/kelvin/v2/users/?school=DEMOSCHOOL&limit=100``.
``limit`` sets the maximum number of objects on a page, from 1 to 1000.
Without ``limit``, a search returns all results as a plain JSON list.

With ``limit``, the response body is the same JSON list,
holding the objects of one page, sorted by name.
The ``Link`` response header, as defined in :rfc:`8288`,
holds the URLs of the other pages::

   Link: <https://kelvin.example.com/ucsschool/kelvin/v2/users/?school=DEMOSCHOOL&limit=100>; rel="first",
         <https://kelvin.example.com/ucsschool/kelvin/v2/users/?school=DEMOSCHOOL&limit=100&cursor=eyJ2...>; rel="next",
         <https://kelvin.example.com/ucsschool/kelvin/v2/users/?school=DEMOSCHOOL&limit=100&cursor=eyJ2...>; rel="last"

The header uses the following relation types:

``first``
   The URL of the first page.

``prev``
   The URL of the previous page. Missing on the first page.

``next``
   The URL of the next page. Missing on the last page.

``last``
   The URL of the last page.

To read another page, request its URL.
The URLs keep all parameters of your search and add a ``cursor`` parameter,
which marks the position of the page.
Treat the cursor as opaque:
don't build or change it, take it from a URL in the ``Link`` header.
A ``cursor`` without ``limit``, or one the Kelvin REST API didn't create,
leads to the server responding with HTTP status ``400``.

.. versionadded:: 4.2.0

   Pagination is supported by the version 2 API only,
   for the searches of users, schools, school classes, work groups, and roles.
