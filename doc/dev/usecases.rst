.. SPDX-FileCopyrightText: 2026 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only


*********
Use Cases
*********

* 🚧 Actor: Who initiates this use case (user role, external system, scheduler)?
* 🚧 Preconditions: What must be true before this use case can execute?
* 🚧 Trigger: What event starts this use case?
* 🚧 Main Flow: What are the step-by-step interactions?
* 🚧 Alternative Flows: What variations exist (optional steps, different paths)?
* 🚧 Exception Flows: What happens when something goes wrong?
* 🚧 Postconditions: What is guaranteed to be true after successful execution?
* 🚧 Business Rules: What domain rules apply during this use case?


Actor List
==========

1. Administrators

   Human administrators who manage UCS\@school domain data (users, groups, schools).
   They may work through a GUI (UMC modules) or automate tasks through direct HTTP
   API usage or command line interface provided by Kelvin.

2. UCS\@school bulk import software

   The UCS\@school import interface (CLI) used for bulk provisioning from external
   source data (e.g., CSV). It reads and normalizes records, generates unique
   usernames and email addresses, calculates changes (add/modify/delete), and
   applies them automatically.

3. UCS\@school user interface software

   Graphical user interfaces used by administrators to manage the same objects as
   the API, for example UCS web interfaces (UMC modules / user management UI).
   In this context, the UI acts as an HTTP client of the Kelvin REST API.

4. API Operator

   The person or team operating the Kelvin REST API service.

   Typical responsibilities include installation/updates, configuration (e.g. log
   level, token validity), certificate/CA management, monitoring, and incident
   response via service log files (see
   https://docs.software-univention.de/ucsschool-kelvin-rest-api/installation-configuration.html and
   https://docs.software-univention.de/ucsschool-kelvin-rest-api/what-to-do-in-case-of-errors.html).

5. School Management Software

   An external school information system (SIS) or school management application
   that provisions and maintains identities and groups in UCS\@school.
   It typically integrates via Kelvin REST API endpoints (CRUD and search) as an
   automated HTTP client.

6. Nubus (Kelvin Connector is triggered by Nubus)

   Nubus components can initiate changes on the directory side (UDM/LDAP). In the
   Kelvin v2 architecture, such changes are synchronized asynchronously into the
   School domain (and vice versa) through dedicated synchronization processes
   (often referred to as connector/provisioning consumers).

   Nubus is therefore an *event source and sync peer* impacting UCS\@school data
   consistency, rather than a typical interactive end user of the Kelvin HTTP API.

7. Kelvin V1

   The Kelvin REST API version 1 is the existing, fully functional school management
   API. It reads and writes UCS\@school data synchronously through the UCS\@school
   Import library, UDM REST API, and LDAP. During the migration phase Kelvin V1
   continues to operate alongside Kelvin V2. Changes made through Kelvin V1 land
   directly in LDAP and are propagated to the Kelvin V2 School database by the
   UDM-to-School synchronization process (eventual consistency). Kelvin V1 is
   considered a peer data source whose writes must be reflected in the School
   database and vice versa.

Single Object CRUD
==================

.. note::
   Actors want to manage the following school objects:

   - Users
   - Groups
   - Schools
   - Computers
   - Computer Rooms
   - Exams

   A subset of the attributes of these objects are synchronized with the directory service.

.. include:: usecases/uc001a_create_object.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc001b_read_object.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc001c_update_object.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc001d_delete_object.rst
   :start-after: .. preview-start
   :end-before: .. preview-end


Bulk Operations
===============


.. include:: usecases/uc002a_bulk_create.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc002b_bulk_update.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc002c_bulk_delete.rst
   :start-after: .. preview-start
   :end-before: .. preview-end



Searching
=========

.. include:: usecases/uc003a_simple_search.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc003b_complex_search.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

Maintenance
===========

.. include:: usecases/uc004a_health_check.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc004b_statistics.rst
   :start-after: .. preview-start
   :end-before: .. preview-end



Extending and customizing Kelvin
================================

.. include:: usecases/uc005a_user_hooks.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc005b_format_hooks.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc005c_config_hooks.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc009_mapped_udm_properties.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

Migration
=========

.. include:: usecases/uc006_coexistence.rst
   :start-after: .. preview-start
   :end-before: .. preview-end


Other Notable Use Cases
=======================

.. include:: usecases/uc007_password_change.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc008_reset_password_multiple_users.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc010_multiple_instances.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc011_permission_system.rst
   :start-after: .. preview-start
   :end-before: .. preview-end

.. include:: usecases/uc012_read_only_kelvin.rst
   :start-after: .. preview-start
   :end-before: .. preview-end


Use Case Details
================

.. toctree::
   :maxdepth: 1

   usecases/uc001a_create_object
   usecases/uc001b_read_object
   usecases/uc001c_update_object
   usecases/uc001d_delete_object
   usecases/uc002a_bulk_create
   usecases/uc002b_bulk_update
   usecases/uc002c_bulk_delete
   usecases/uc003a_simple_search
   usecases/uc003b_complex_search
   usecases/uc004a_health_check
   usecases/uc004b_statistics
   usecases/uc005a_user_hooks
   usecases/uc005b_format_hooks
   usecases/uc005c_config_hooks
   usecases/uc006_coexistence
   usecases/uc007_password_change
   usecases/uc008_reset_password_multiple_users
   usecases/uc009_mapped_udm_properties
   usecases/uc010_multiple_instances
   usecases/uc011_permission_system
   usecases/uc012_read_only_kelvin
