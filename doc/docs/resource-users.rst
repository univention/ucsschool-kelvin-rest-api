.. SPDX-FileCopyrightText: 2021-2023 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Resource Users
==============

The ``Users`` resource is represented in the LDAP tree as user objects.

To list those LDAP objects run:

.. code-block:: console

    $ FILTER='(|(objectClass=ucsschoolStaff)(objectClass=ucsschoolStudent)(objectClass=ucsschoolTeacher))'
    $ univention-ldapsearch -LLL "$FILTER"

UCS\@school uses the :ref:`UDM REST API <udm-rest-api>` which in turn uses UDM to access LDAP.
UDM properties have different names than their associated LDAP attributes.
Their values may also differ.
To list the same UDM objects run:

.. code-block:: console

    $ FILTER='(|(objectClass=ucsschoolStaff)(objectClass=ucsschoolStudent)(objectClass=ucsschoolTeacher))'
    $ udm users/user list --filter "$FILTER"

.. _users-resource-repr:

Users resource representation
-----------------------------

The following JSON is an example User resource in the *UCS\@school Kelvin REST API*:

.. code-block:: json

    {
        "dn": "uid=demo_student,cn=schueler,cn=users,ou=DEMOSCHOOL,dc=uni,dc=ven",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student",
        "ucsschool_roles": ["student:school:DEMOSCHOOL", "student:school:DEMOSCHOOL2"],
        "name": "demo_student",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "firstname": "Demo",
        "lastname": "Student",
        "birthday": "2003-10-24",
        "disabled": false,
        "email": "demo_student@uni.ven",
        "expiration_date": "2030-02-14",
        "record_uid": "demo_student12",
        "roles": ["https://<fqdn>/ucsschool/kelvin/v1/roles/student"],
        "schools": [
            "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
            "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL2"
        ],
        "school_classes": {
            "DEMOSCHOOL": ["Democlass"],
            "DEMOSCHOOL2": ["demoklasse2"]
        },
        "workgroups": {
            "DEMOSCHOOL": ["demoworkgroup"],
            "DEMOSCHOOL2": ["demoworkgroup2"]
        },
        "source_uid": "Kelvin",
        "udm_properties": {
            "description": "An example user attending two school.",
            "gidNumber": 5023,
            "employeeType": null,
            "organisation": null,
            "phone": ["+49 177 3578031", "+49 241 3456232"],
            "title": null,
            "uidNumber": 2007
        }
    }


.. csv-table:: Attribute description
   :header: "name", "value", "Description", "Notes"
   :widths: 3, 2, 6, 5
   :escape: '

    "dn", "string", "The DN of the user in LDAP.", "read only"
    "name", "string", "The users username.", ""
    "url", "URL", "The URL of the user object in the UCS\@school Kelvin API.", "read only"
    "firstname", "string", "The users given name.", ""
    "lastname", "string", "The users family name.", ""
    "birthday", "date", "The users birthday in ISO 8601 format: ``YYYY-MM-DD``.", ""
    "disabled", "boolean", "Whether the user should be deactivated.", ""
    "email", "string", "The users email address (``mailPrimaryAddress``), used only when the emails domain is hosted on UCS, not to be confused with the *contact* attribute ``e-mail``.", ""
    "expiration_date", "string", "The users password expiration date. The user won't be able to log in from that date on. Format: ``YYYY-MM-DD``.", "The year must be between 1961 and 2099."
    "roles", "list", "The users UCS\@school roles. A list of URLs in the ``roles`` resource.", "required when creating, see section ``Changing roles`` below about changing a user''s roles"
    "school", "string", "School (OU) the user belongs to. A URL in the ``schools`` resource.", "required for creation when ``schools`` is not set"
    "schools", "list", "List of schools (OUs) the user belongs to. A list of URLs in the ``schools`` resource.", "required for creation when ``school`` is not set"
    "school_classes", "nested object", "School classes the user is a member of. A mapping from school names to class names, for example: ``{'"'school1'"': ['"'class1'"', '"'class2'"'], '"'school2'"': ['"'class3'"']}``.", "The schools must also be listed (as URLs) in the ``schools`` attribute."
    "workgroups", "nested object", "Workgroups the user is a member of. A mapping from school names to workgroup names, for example: ``{'"'school1'"': ['"'wg1'"', '"'wg2'"'], '"'school2'"': ['"'wg3'"']}``.", "The schools must also be listed (as URLs) in the ``schools`` attribute."
    "record_uid", "string", "Unique identifier of the user in the upstream database the user was imported from. Used in combination with ``source_uid`` by the UCS\@school import to uniquely identify users in both LDAP and upstream databases.", "changing is strongly discouraged"
    "source_uid", "string", "Identifier of the upstream database the user was imported from. Defaults to ``Kelvin`` if unset.", "changing is strongly discouraged"
    "ucsschool_roles", "list", "List of ucsschool_roles strings auto-managed by the system and custom addition ucsschool_roles strings . ucsschool_role strings with context type school are ignored. Format is ``ROLE:CONTEXT_TYPE:CONTEXT``, for example: ``['"'myrole:mycontext:gym1'"', '"'student:school:gym1'"']``."
    "udm_properties", "nested object", "Object with UDM properties. For example: ``{'"'street'"': '"'Luise Av.'"', '"'phone'"': ['"'+49 30 321654987'"', '"'123 456 789'"']}``", "Must be configured, see below."

The ``password`` and ``kelvin_password_hashes`` attributes are not listed, because they cannot be retrieved, they can only be *set* when creating or modifying a user.
UCS systems never store or send clear text passwords.

The ``password`` attribute is a single string containing the clear text password to set for the user.

The ``kelvin_password_hashes`` attribute is an object where all of the following attributes must be set. Setting all hashes ensures a consistent behavior for authenticating against OpenLDAP, Kerberos and Samba services:

* ``user_password``: list of strings containing the LDAPs ``userPassword`` attribute
* ``samba_nt_password``: string containing the LDAPs ``sambaNTPassword`` attribute
* ``krb_5_key``: list of strings containing the LDAPs ``krb5Key`` attribute, each item is base64 encoded
* ``krb5_key_version_number``: : integer containing the LDAPs ``krb5KeyVersionNumber`` attribute
* ``samba_pwd_last_set``: integer containing the LDAPs ``sambaPwdLastSet`` attribute

Run the following command on a UCS system to see how those values should look like:

.. code-block:: console

    $ univention-ldapsearch -LLL uid=Administrator userPassword sambaNTPassword krb5Key krb5KeyVersionNumber sambaPwdLastSet

When transmitted in a valid POST/PATCH/PUT operation, the values of ``kelvin_password_hashes`` will be set on the users LDAP object as given (``krb_5_key`` will be base64 decoded), without further validation.

school[s]
^^^^^^^^^
The Users resource has a ``school`` attribute whose primary meaning is the position of its LDAP object in the LDAP tree.
More important is its ``schools`` attribute.
It is the list of schools that students are enrolled in or where staff and teachers work.

When creating/changing a user and sending only a value for ``school``, ``schools`` will be a list of that one item.

When creating a user and only ``schools`` is sent, ``school`` will automatically be chosen as the alphabetically first of the list.
When changing a user, the user object will stay in its OU, if it is the ``schools`` list, regardless of alphabetical order.

When both ``school`` and ``schools`` are used, the value of ``school`` must be in the list of values in ``schools``.

school_classes
^^^^^^^^^^^^^^
All school names in ``school_classes`` must exist (as URLs) in ``schools``.

If the value of ``school_classes`` contains an empty dictionary in a modify
request, the user will be removed from all classes.

workgroups
^^^^^^^^^^
All school names in ``workgroups`` must exist (as URLs) in ``schools``.

If the value of ``workgroups`` contains an empty dictionary in a modify
request, the user will be removed from all workgroups. To avoid this behavior,
simply don't pass the attribute in PUT or in PATCH and the current workgroups
will be kept.

udm_properties for resource users
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The attribute ``udm_properties`` is an object that can contain arbitrary UDM properties.
It must be configured in the file :file:`/var/lib/ucs-school-import/configs/kelvin.json`, or :file:`/etc/ucsschool/kelvin/mapped_udm_properties.json`;
see :ref:`Configuration of user object management (import configuration)` and :ref:`configuration-udm-properties`.
It must not contain UDM properties that are already available as regular attributes (like ``username`` → ``name``, ``mailPrimaryAddress`` → ``email``, ...).


Users list and search
---------------------

Example ``curl`` command to retrieve the list of all users:

.. code-block:: console

    $ curl -i -k -X GET "https://<fqdn>/ucsschool/kelvin/v1/users/" \
        -H "accept: application/json"
        -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJh...."

The response headers will be::

    HTTP/1.1 200 OK
    Date: Mon, 20 Jan 2020 15:11:14 GMT
    Server: uvicorn
    content-length: 43274
    content-type: application/json
    Via: 1.1 <fqdn>

The response body will be:

.. code-block:: json

    [
        {
            "dn": "uid=demo_admin,cn=lehrer,cn=users,ou=DEMOSCHOOL,dc=uni,dc=ven",
            "url": "https://<fqdn>/ucsschool/kelvin/v1/users/demo_admin",
            "ucsschool_roles": ["teacher:school:DEMOSCHOOL"],
            "name": "demo_admin",
            "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
            "firstname": "Demo",
            "lastname": "Admin",
            "birthday": null,
            "disabled": false,
            "email": null,
            "expiration_date": null,
            "record_uid": null,
            "roles": ["https://<fqdn>/ucsschool/kelvin/v1/roles/teacher"],
            "schools": ["https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL"],
            "school_classes": {},
            "workgroups": {},
            "source_uid": null,
            "udm_properties": {}
        }
    ]

To search for users with usernames that contain ``Brian``, append ``?name=*Brian*`` to the school
resource. The search is case-insensitive. The URL would be: ``https://<fqdn>/ucsschool/kelvin/v1/users/?name=%2ABrian%2A``

The Users resource supports searching for all attributes and to combine those.
To search for users that are both ``staff`` and ``teacher`` with usernames that start with ``demo``, birthday on the 3rd of February, have a lastname that ends with ``sam`` and are enrolled in school ``demoschool``, the URL is: ``https://<fqdn>/ucsschool/kelvin/v1/users/?school=demoschool&name=demo%2A&birthday=2001-02-03&lastname=%2Asam&roles=staff&roles=teacher``

The user in the example response is working in two schools as both staff and teacher:

.. code-block:: json

    [
        {
            "dn": "uid=test.staff.teach,cn=lehrer und mitarbeiter,cn=users,ou=test,dc=uni,dc=ven",
            "url": "https://<fqdn>/ucsschool/kelvin/v1/users/test.staff.teach",
            "ucsschool_roles": [
                "staff:school:test",
                "teacher:school:test",
                "staff:school:other",
                "teacher:school:other"
            ],
            "name": "test.staff.teach",
            "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/test",
            "firstname": "staffer",
            "lastname": "teach",
            "birthday": "1988-03-18",
            "disabled": false,
            "email": "test.staff.teach@uni.dtr",
            "expiration_date": null,
            "record_uid": "test.staff.teach12",
            "roles": [
                "https://<fqdn>/ucsschool/kelvin/v1/roles/staff",
                "https://<fqdn>/ucsschool/kelvin/v1/roles/teacher"
            ],
            "schools": [
                "https://<fqdn>/ucsschool/kelvin/v1/schools/test",
                "https://<fqdn>/ucsschool/kelvin/v1/schools/other"
            ],
            "school_classes": {
                "test": ["testclass", "testclass2"],
                "other": ["otherklasse", "otherklasse2"]
            },
            "workgroups": {
                "test": ["testworkgroup", "testworkgroup2"],
                "other": ["otherworkgroup", "otherworkgroup2"]
            },
            "source_uid": "TESTID",
            "udm_properties": {
                "description": "Working at two schools.",
                "gidNumber": 9319,
                "employeeType": "Lehrer und Mitarbeiter",
                "organisation": "School board",
                "phone": ["+123-456-789", "0321-456-987"],
                "title": "Mr.",
                "uidNumber": 12503
            }
        }
    ]


Users retrieve
--------------

Example ``curl`` command to retrieve a single user object:

.. code-block:: console

    $ curl -k -X GET "https://<fqdn>/ucsschool/kelvin/v1/users/demo_staff" \
        -H "accept: application/json" \
        -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJh...." | python -m json.tool

With the search being case-insensitive, the URL could also have ended in ``DeMo_StAfF``.
The response body will be similar to the following (shortened):

.. code-block:: json

    {
        "dn": "uid=demo_staff,cn=mitarbeiter,cn=users,ou=DEMOSCHOOL,dc=uni,dc=ven",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/users/demo_staff",
        "ucsschool_roles": ["staff:school:DEMOSCHOOL"],
        "name": "demo_staff"
    }

Users create
------------

When creating a user, a number of attributes must be set, unless formatted from a template (see :ref:`configuration-scheme-formatting` in :cite:t:`uv-ucsschool-import`):

* ``name``
* ``firstname``
* ``lastname``
* ``record_uid``
* ``roles``
* ``school`` or ``schools`` (or both)
* ``source_uid``

As an example, with the following being the content of :file:`/tmp/create_user.json`:

.. code-block:: json

    {
        "name": "bob",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "firstname": "Bob",
        "lastname": "Marley",
        "birthday": "1945-02-06",
        "disabled": true,
        "email": null,
        "expiration_date": null,
        "record_uid": "bob23",
        "password": "s3cr3t.s3cr3t.s3cr3t",
        "roles": ["https://<fqdn>/ucsschool/kelvin/v1/roles/teacher"],
        "schools": ["https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL"],
        "source_uid": "Reggae DB",
        "udm_properties": {
            "title": "Mr."
        }
    }

This ``curl`` command will create a user from the above data:

.. code-block:: console

    $ curl -i -k -X POST "https://<fqdn>/ucsschool/kelvin/v1/users/" \
        -H "accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJh...." \
        -d "$(</tmp/create_user.json)"

Response headers::

    HTTP/1.1 201 Created
    Date: Mon, 20 Jan 2020 16:24:33 GMT
    Server: uvicorn
    content-length: 714
    content-type: application/json
    Via: 1.1 <fqdn>

Response body:

.. code-block:: json

    {
        "dn": "uid=bob,cn=lehrer,cn=users,ou=DEMOSCHOOL,dc=uni,dc=ven",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/users/bob",
        "ucsschool_roles": ["teacher:school:DEMOSCHOOL"],
        "name": "bob",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "firstname": "Bob",
        "lastname": "Marley",
        "birthday": "1945-02-06",
        "disabled": true,
        "email": null,
        "expiration_date": null,
        "record_uid": "bob23",
        "roles": ["https://<fqdn>/ucsschool/kelvin/v1/roles/teacher"],
        "schools": ["https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL"],
        "school_classes": {},
        "workgroups": {},
        "source_uid": "Reggae DB",
        "udm_properties": {
            "description": null,
            "gidNumber": 5023,
            "employeeType": null,
            "organisation": null,
            "phone": [],
            "title": "Mr.",
            "uidNumber": 12711
        }
    }

The ``password`` attribute is missing in the response, because UCS systems never stores or sends clear text passwords.

Users modify and move
---------------------

It is possible to perform complete and partial updates of existing user objects.
The ``PUT`` method expects a JSON object with all user attributes set. Nevertheless, the attribute ``workgroups`` can be skipped to preserve its current value.
The ``password`` attribute should *not* be sent repeatedly, as most password policies forbid reusing the same password.
The ``PATCH`` method will update only those attributes sent in the request.
Both methods return a complete Users resource in the response body, exactly as a ``GET`` request would.

PUT example
^^^^^^^^^^^
All required attributes must be sent with a ``PUT`` request.

As an example, with the following being the content of :file:`/tmp/mod_user.json`:

.. code-block:: json

    {
        "name": "bob",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "firstname": "Bob72",
        "lastname": "Marley72",
        "record_uid": "bob72",
        "roles": ["https://<fqdn>/ucsschool/kelvin/v1/roles/teacher"],
        "schools": ["https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL"],
        "source_uid": "Kelvin Test2",
        "udm_properties": {"title": "Mr.2"}
    }

This ``curl`` command will modify the user with the above data:

.. code-block:: console

    $ curl -i -k -X PUT "https://<fqdn>/ucsschool/kelvin/v1/users/bob" \
        -H "accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJh...." \
        -d "$(</tmp/mod_user2.json)"

Response headers::

    HTTP/1.1 200 OK
    Date: Tue, 21 Jan 2020 22:40:21 GMT
    Server: uvicorn
    content-length: 721
    content-type: application/json
    Via: 1.1 <fqdn>

Response body:

.. code-block:: json

    {
        "birthday": null,
        "disabled": false,
        "dn": "uid=bob,cn=lehrer,cn=users,ou=DEMOSCHOOL,dc=uni,dc=ven",
        "email": null,
        "expiration_date": null,
        "firstname": "Bob72",
        "lastname": "Marley72",
        "name": "bob",
        "record_uid": "bob72",
        "roles": ["https://<fqdn>/ucsschool/kelvin/v1/roles/teacher"],
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "school_classes": {},
        "workgroups": {},
        "schools": ["https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL"],
        "source_uid": "Kelvin Test2",
        "ucsschool_roles": ["teacher:school:DEMOSCHOOL"],
        "udm_properties": {
            "description": null,
            "employeeType": null,
            "gidNumber": 5023,
            "organisation": null,
            "phone": [],
            "title": "Mr.2",
            "uidNumber": 12816
        },
        "url": "https://<fqdn>/ucsschool/kelvin/v1/users/bob"
    }

PATCH example
^^^^^^^^^^^^^
Only the attributes that should be changed are sent with a ``PATCH`` request.
The following ``curl`` command will modify the users given name only:

.. code-block:: console

    $ curl -i -k -X PATCH "https://<fqdn>/ucsschool/kelvin/v1/users/bob" \
        -H "accept: application/json" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJh...." \
        -d '{"firstname": "Robert Nesta"}'

Response headers::

    HTTP/1.1 200 OK
    Date: Tue, 21 Jan 2020 22:51:40 GMT
    Server: uvicorn
    content-length: 728
    content-type: application/json
    Via: 1.1 <fqdn>

Response body, abbreviated: the rest is the same:

.. code-block:: json

    {
        "birthday": null,
        "disabled": false,
        "dn": "uid=bob,cn=lehrer,cn=users,ou=DEMOSCHOOL,dc=uni,dc=ven",
        "email": null,
        "expiration_date": null,
        "firstname": "Robert Nesta"
    }

Move
^^^^

When a ``PUT`` or ``PATCH`` request change the ``school`` or ``schools`` attribute, the users LDAP object may be moved to a new position in the LDAP tree.

A move will only happen, when the new value for ``school`` is not in ``schools``.

When using ``PATCH`` and changing only ``school``, ``schools`` may be updated to contain the new value of ``school``.

While changing the ``name`` attribute is technically also a move, the objects *position* in the LDAP tree will not change - only its name.

Changing a users roles
^^^^^^^^^^^^^^^^^^^^^^

Since version ``1.3.0`` of the *UCS\@school Kelvin REST API* app it is possible to change a users roles.
Not all role combination or changes are allowed though, and roles may have extra requirements.
The following lists transitions where the API user has to take extra care:

=============  =============  =========
 Old            New            Note
=============  =============  =========
any            staff          Staff users have no school classes. The ``school_class`` attribute will be cleared automatically by the Kelvin API.
any            student        Students must be member of one school class for each school they are a member of. When changing the ``roles`` attribute, the user must already have a corresponding ``school_class`` entry or a new value for ``school_class`` must be sent in the same request.
any            student        The transition is not allowed if the user is also a school administrator.
=============  =============  =========

UCS\@school user objects have a few attributes and group memberships that must be set correctly.
The online article :uv:kb:`How a UCS@school user should look like <15630>` describes those.
The Kelvin API will take care of those settings, when changing user roles.

Please be aware that changing a users role can have serious side effects.
It might be necessary to make further changes to a user object or to other systems.
For some of these processes hooks for the Kelvin API could be written.
Please test all your role changing scenarios thoroughly.
A few examples of possible problems:

* The UCS\@school import is used to provision users. The ``source_uid`` user attribute is used to select which user accounts to include in searches for existing uses. If the imports are done through the graphical UMC module, the ``source_uid`` attribute contains the role of the imported user. When user roles are changed through the *UCS\@school Kelvin REST API*, the ``source_uid`` attribute is *not* adapted. If in the mentioned import case the CSV source data is not adapted, a new user would be created with the old roles and the user with the modified roles would be deleted.
* When creating users, their email addresses are created from different templates for different roles. For example ``<firstname>.<lastname>@staff.<domain>`` for staff members and ``<firstname>[0].<lastname>@teacher.<domain>`` for teachers. When user roles are changed through the *UCS\@school Kelvin REST API*, the email address is *not* adapted.
* Home directories of UCS\@school users are located on school servers in a directory structure containing the user's role (e.g. ``/home/$OU/lehrer/$USERNAME``). The directory path is stored in the LDAP attribute ``homeDirectory`` / the UDM property ``unixhome``. The location of home directories is of no technical consequence. When user roles are changed, the *UCS\@school Kelvin REST API* will not modify the users home directory property and will not move its files and directories.


Users delete
------------

The ``DELETE`` method is used to delete a user object:

.. code-block:: console

    $ curl -i -k -X DELETE "https://<fqdn>/ucsschool/kelvin/v1/users/bob" \
        -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJh...."

Response headers::

    HTTP/1.1 204 No Content
    Date: Tue, 21 Jan 2020 22:57:03 GMT
    Server: uvicorn
    content-type: application/json
    Via: 1.1 <fqdn>

No response body.
