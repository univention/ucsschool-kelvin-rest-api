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

With ``limit``, the response body is a JSON object instead of a list::

   {
     "results": [ ... ],
     "next_page_url": "https://<fqdn>/ucsschool/kelvin/v2/users/?school=DEMOSCHOOL&limit=100&cursor=eyJ2...",
     "previous_page_url": null
   }

``results``
   The objects of the page, sorted by name.

``next_page_url``
   The URL of the next page, or ``null`` on the last page.

``previous_page_url``
   The URL of the previous page, or ``null`` on the first page.

To read the next or previous page, request its URL.
The URLs keep all parameters of your search and add a ``cursor`` parameter,
which marks the position of the page.
Treat the cursor as opaque:
don't build or change it, take it from a page URL.
A ``cursor`` without ``limit``, or one the Kelvin REST API didn't create,
leads to the server responding with HTTP status ``400``.

Every page request is independent of the others.
Any Kelvin REST API instance can answer it,
so a setup with several instances or a load balancer needs no sticky sessions.
Objects that someone creates or deletes while you read the pages
don't shift the following pages.
Reading in one direction, every object that exists for the whole time appears exactly once,
unless someone renames it between two page requests.
When you go back to earlier pages after objects were created, deleted, or renamed,
their boundaries can differ from the ones you saw before.
When you reach the start this way, you get the regular first page,
the same one a search without ``cursor`` returns,
so some objects can appear on two pages.

.. versionadded:: 4.2.0

   Pagination is supported by the version 2 API only,
   for the searches of users, schools, school classes, work groups, and roles.
