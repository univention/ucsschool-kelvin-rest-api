.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Functional requirements
=======================

All functional requirements should be listed and named, so it's easier to reference them later on.

Core Capabilities
-----------------

* 🚧 What must the API be able to do?
* 🚧 What CRUD operations are required for which resources?

Business Rules
--------------

* 🚧 What domain-specific rules must be enforced?
* 🚧 What validations are mandatory?

.. _fr-authentication-and-authorization:

Authentication & Authorization
------------------------------

* 🚧 Who can access what?
* 🚧 What actions require which permissions?

Synchronization
---------------

* 🚧 What data must be synchronized?
* 🚧 What triggers a sync?
* 🚧 What is the expected latency?

Data Management
---------------

* 🚧 What data retention rules apply?
* 🚧 What audit/history requirements exist?

Integration
-----------

* 🚧 What external systems must be supported?
* 🚧 What data formats are required?

Functional Requirements Example
-------------------------------

.. code-block:: text
   :caption: Example for chapter content
   :name: fr-chapter-example

    FR-001: User Management
    -----------------------

    :Priority: Must-have
    :Component: API, Database

    Description
    ^^^^^^^^^^^
    The system must provide complete CRUD operations for user entities.

    Acceptance Criteria
    ^^^^^^^^^^^^^^^^^^^
    - Users can be created with email, name, and group assignments
    - Users can be retrieved individually or as a paginated list
    - Users can be updated (partial updates supported)
    - Users can be soft-deleted (retain for audit purposes)
    - All operations require appropriate group membership

    Related Use Cases
    ^^^^^^^^^^^^^^^^^
    - :ref:`uc_create_user`
    - :ref:`uc_manage_group_membership`
