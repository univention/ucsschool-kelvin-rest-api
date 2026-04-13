.. SPDX-FileCopyrightText: 2026 Univention GmbH
.. SPDX-License-Identifier: AGPL-3.0-only

Architecture
============

System overview
---------------

* 🚧 What does the system look like from a bird's eye view?
* 🚧 Which external systems are involved (PostgreSQL, Guardian, Keycloak?, UDM REST, Provisioning service)?
* 🚧 How do the components interact?
* 🚧 C4 context diagram? (system within context)
* 🚧 C4 container diagram? (API, DB, Kelvin Connector, Provisioning Service, ...)

Components
----------

* 🚧 What layers are there (router, service, repository)?
* 🚧 What are the responsibilities of each layer?
* 🚧 What is the data flow for a typical request?

Data model
----------

Entities
^^^^^^^^

Tables in this section have been generated from the ``SQLAlchemy`` models unless otherwise noted.

User
""""

   A user represents a person and their account.

.. include:: architecture/user-attributes.rst

.. note::

   The Kelvin API requires ``source_uid`` and ``record_uid``. When a user is provisioned by the connector however
   it is possibly that he won't have a value for these two attributes. In that case, ``"nubus"`` is the ``source_uid``
   and ``record_uid`` is equal to the ``univentionObjectIdentifier``/``public_id``.

.. include:: architecture/user-relations.rst


.. .. include:: architecture/user-constraints.rst



Role
""""

   A role, e.g. teacher, student, legal guardian or admin.

.. include:: architecture/role-attributes.rst

.. include:: architecture/role-relations.rst

.. note::

   The assignment of a role to a group means that the members of that group inherit the role.
   The details of this relationship is not yet worked out and not documented here.

.. attention::

   A role does not have a corresponding object in the Nubus database. Roles in Nubus are saved as strings
   on the ``guardianRole`` multi-value attribute. Thus, the ``public_id`` does not correspond to any
   ``univentionObjectIdentifier`` in Nubus. However, the ``public_id`` might be refer to the identifier of a
   role in the Guardian application.

School
""""""

.. include:: architecture/school-attributes.rst

.. include:: architecture/school-relations.rst


SchoolMembership
""""""""""""""""

.. include:: architecture/schoolmembership-attributes.rst

.. include:: architecture/schoolmembership-relations.rst

.. note::

   1. A user must have at least one school membership.
   2. A user must have exactly one primary school membership.
   3. A user must have at least one role in a school he is a member of.

   These constraints are not yet completely enforced in this model:
   A school less user can be created, this has to be prevented in the application
   layer.


Group
"""""

.. include:: architecture/group-attributes.rst

.. include:: architecture/group-relations.rst



GroupType
"""""""""

   Classifies a group (e.g. school class, workgroup)

.. include:: architecture/grouptype-attributes.rst

.. include:: architecture/grouptype-relations.rst


UserUDMProperties
"""""""""""""""""

Not yet implemented in ``SQLAlchemy``.

.. include:: architecture/user-udm-properties-attributes.rst

.. include:: architecture/user-udm-properties-relations.rst


GroupUDMProperties
""""""""""""""""""

Not yet implemented in ``SQLAlchemy``.

.. include:: architecture/group-udm-properties-attributes.rst

.. include:: architecture/group-udm-properties-relations.rst


SchoolUDMProperties
"""""""""""""""""""

Not yet implemented in ``SQLAlchemy``.

.. include:: architecture/school-udm-properties-attributes.rst

.. include:: architecture/school-udm-properties-relations.rst


Entity-Relationship diagram
^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. mermaid:: architecture/er.mmd

.. attention::

   Omitted relations to simplify the diagram:

   * All relations related to UDM properties

Localization
^^^^^^^^^^^^

Localized attributes are stored in a JSON object, where the keys are the language codes (ISO 639) and the values are the localized strings.

.. code:: json

   {
     "en": "English",
     "de": "Deutsch"
   }

Future Entities
^^^^^^^^^^^^^^^

.. attention::

   The following entities are suggestions for future development.

SchoolAuthority
"""""""""""""""

   A school authority manages 0 or more schools.

.. list-table:: Attributes
   :header-rows: 1
   :widths: 1 1 1 3 3

   * - Name
     - Type
     - Default
     - Constraints
     - Description
   * - ``public_id``
     - ``uuid``
     - Generated
     - ``Unique``, ``not NULL``
     -
   * - ``display_name``
     - ``json``
     - ``{}``
     - ``not NULL``
     - Localized display name of the school authority

.. list-table:: Relations from the perspective of entity ``SchoolAuthority``
   :header-rows: 1
   :widths: 1 1 2

   * - Entity
     - Cardinality
     - Relationship
   * - School
     - 1:N
     - A school authority **administers** N schools.

.. note::

   * A school authority does not have a direct relation to an object in UDM.

UserRelation
""""""""""""

See `Issue #208 <https://git.knut.univention.de/univention/dev/education/ucsschool-kelvin-rest-api/-/work_items/208>`_

   A user has a relation of a certain type to another user.

.. note::

   This suggestion for a relation has some shortcomings: Only for parent-child type relationships
   with no other constraints, like one-to-one etc. Additionally, it seems to be complicated to implement
   with SQLAlchemy. Another variant is to have additional association tables for each new relation.

.. list-table:: Attributes of ``UserRelation``
   :header-rows: 1
   :widths: 1 1 1 3 3

   * - Name
     - Type
     - Default
     - Constraints
     - Description
   * - ``relation_type``
     - ``enum``
     -
     - ``Unique`` via ``enum``
     -

.. list-table:: Relations to entities from the perspective of ``UserRelation``
   :header-rows: 1
   :widths: 1 1 2

   * - Entity
     - Cardinality
     - Relationship
   * - User
     - 1:1
     - A user relation **contains** exactly one parent
   * - User
     - 1:1
     - A user relation **contains** exactly one child

Architecture of Authentication & Authorization
----------------------------------------------

* 🚧 How does the auth flow work (API token? OIDC?)?
* 🚧 How are group memberships checked?
* 🚧 What roles/permissions are there?
* 🚧 Sequence diagram for auth flow

Interfaces
----------

* 🚧 Which protocols/formats are used?
* 🚧 What dependencies on external systems exist?
