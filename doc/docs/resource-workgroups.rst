Resource Workgroups
===================

The ``Workgroups`` resource represents the workgroups a school user is a member of.

The resource objects are represents as group objects in the LDAP.

``Workgroups`` can be created, retrieved, modified, deleted and searched for with the Kelvin API.

Workgroups resource representation
----------------------------------

The following JSON is an example Workgroups resource in the *UCS\@school Kelvin REST API*::

    {
        "dn": "cn=DEMOSCHOOL-Demoworkgroup,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/workgroups/DEMOSCHOOL/Demoworkgroup",
        "ucsschool_roles":[
            "workgroup::school:DEMOSCHOOL"
        ],
        "udm_properties": {},
        "name": "Demoworkgroup",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "description": null,
        "users": [
            "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student"
        ],
        "create_share": true,
        "email": null,
        "allowed_email_senders_users": [],
        "allowed_email_senders_groups": []
    }


.. csv-table:: Property description
   :header: "name", "value", "Description", "Notes"
   :widths: 5, 2, 6, 3
   :escape: '

    "dn", "string", "dn of the LDAP", "read only"
    "url", "URL", "The URL of the workgroup object in the UCS\@school Kelvin API.", "read only"
    "ucsschool_roles", "list", "List of roles the workgroup has. Format is ``ROLE:CONTEXT_TYPE:CONTEXT``, for example: ``['"'workgroup:school:DEMOSCHOOL'"']``.", "auto-managed by system, setting and changing discouraged"
    "udm_properties", "nested object", "Object with UDM properties. For example: ``{'"'street'"': '"'Luise Av.'"', '"'phone'"': ['"'+49 30 321654987'"', '"'123 456 789'"']}``", "Must be configured."
    "name", "string", "Name of the workgroup", "editable"
    "school", "URL", "The URL of the school object a workgroup belongs to in the UCS\@school Kelvin API.", "read_only"
    "description","null|string","Descriptive information about a workgroup.","editable"
    "users","List<URL>", "A list with the URL in the UCS\@school Kelvin API per user within the workgroup.","editable"
    "create_share", "boolean", "Whether a share should be created for the workgroup.", "read only"
    "email", "string", "Email", "editable"
    "allowed_email_senders_users", "list", "Users that are allowed to send e-mails to the workgroup.", "editable"
    "allowed_email_senders_groups", "list", "Groups that are allowed to send e-mails to the workgroup.", "editable"


udm_properties
--------------

The attribute ``udm_properties`` is an object that can contain arbitrary UDM properties.
It must be configured in the file ``/etc/ucsschool/kelvin/mapped_udm_properties.json``, see :ref:`UDM Properties`.


Workgroups list and search
--------------------------

Example ``curl`` command to retrieve the list of all workgroups at ``DEMOSCHOOL`` ::

    $ curl  -X GET  "https://<fqdn>/ucsschool/kelvin/v1/workgroups/?school=DEMOSCHOOL" \
            -H "accept: application/json"
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciO..."

The response headers will be::

    HTTP/1.1 200 OK
    Connection: Keep-Alive
    Content-length: 462
    Content-type: application/json
    Date: Tue,10 May 2022 06:44:09 GMT
    Keep-alive: timeout=5,max=99
    Server: uvicorn
    Via: 1.1 <fqdn>

The response body will be::

    [
        {
            "dn": "cn=DEMOSCHOOL-Demoworkgroup,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
            "url": "https://<fqdn>/ucsschool/kelvin/v1/workgroups/DEMOSCHOOL/Demoworkgroup",
            "ucsschool_roles": [
                "workgroup:school:DEMOSCHOOL"
            ],
            "udm_properties": {},
            "name": "Demoworkgroup",
            "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
            "description": null,
            "users": [
                "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student"
            ],
            "create_share": true,
            "email": null,
            "allowed_email_senders_users": [],
            "allowed_email_senders_groups": []
        }
    ]

It is required to provide the ``?school=<schoolname>`` in the query. The search for the school name is
case sensitive and requires exact match.

Only providing the school will list all workgroups of that school.
Optionally you can search for specific workgroup names in that school by appending ``?name=<workgroupname>`` to the school
resource. This search for the workgroup name is case-insensitive and supports wildcards (*).
For example to search for a workgroup with the name ``DEMOWORKGROUP`` you can append ``?name=*workgroup``.
The URL would be: ``https://<fqdn>/ucsschool/kelvin/v1/workgroups/?school=DEMOSCHOOL?name=%2workgroup``.


Workgroups retrieve
-------------------

Example ``curl`` command to retrieve the workgroup ``Demoworkgroup`` at ``DEMOSCHOOL`` ::

    $ curl  -X GET  "https://<fqdn>/ucsschool/kelvin/v1/workgroups/DEMOSCHOOL/Demoworkgroup" \
            -H "accept: application/json"
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciO..."

The response headers will be::

    Connection: Keep-Alive
    Content-length: 460
    Content-type: application/json
    Date: Tue,10 May 2022 07:55:51 GMT
    Keep-alive: timeout=5,max=100
    Server: uvicorn
    Via: 1.1 <fqdn>

The response body will be::

    {
        "dn": "cn=DEMOSCHOOL-Demoworkgroup,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/workgroups/DEMOSCHOOL/Demoworkgroup",
        "ucsschool_roles": [
            "workgroup:school:DEMOSCHOOL"
        ],
        "udm_properties": {},
        "name": "Demoworkgroup",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "description": null,
        "users": [
            "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student"
        ],
        "create_share": true,
        "email": null,
        "allowed_email_senders_users": [],
        "allowed_email_senders_groups": []
    }

Matching of the queried ``workgroup`` *and* ``school`` is case-sensitive.
The response body will be identical to the response in the example above, if a school only has a single workgroup registered.
Otherwise the list of workgroups from the example above will contain the ``workgroup`` which has been requested.


Workgroups modify
-----------------

Example ``curl`` command to modify the workgroup ``Demoworkgroup2`` at ``DEMOSCHOOL`` ::

    $ curl  -X PATCH  "https://<fqdn>/ucsschool/kelvin/v1/workgroups/Demoschool/Demoworkgroup2" \
            -H "accept: application/json" \
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1N..." \
            -H "Content-Type: application/json" \
            -d "{
            "description": "The new workgroup description."
            }"

The response headers will be::

    HTTP/1.1 200 OK
    Connection: Keep-Alive
    Content-length: 397
    Content-type: application/json
    Date: Tue,10 May 2022 07:49:13 GMT
    Keep-alive: timeout=5,max=100
    Server: uvicorn
    Via: 1.1 <fqdn>

The response will be::

    {
        "dn": "cn=Demoschool-Demoworkgroup2,cn=schueler,cn=groups,ou=Demoschool,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/workgroups/Demoschool/Demoworkgroup2",
        "ucsschool_roles": [
        "workgroup:school:Demoschool"
        ],
        "udm_properties": {},
        "name": "Demoworkgroup2",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/Demoschool",
        "description": "The new workgroup description.",
        "users": [],
        "create_share": true,
        "email": null,
        "allowed_email_senders_users": [],
        "allowed_email_senders_groups": []
    }

The example shows how to change the description of a ``workgroup``.
Optionally ``udm_properties`` and/or ``users`` can be modified.
But a ``workgroup`` object's ``school`` or ``create_share`` can't be modified.


Workgroups create
-----------------

Example ``curl`` command to create the workgroup ``Demoworkgroup2`` at ``DEMOSCHOOL`` ::

    $ curl  -X POST  "https://<fqdn>/ucsschool/kelvin/v1/workgroups/" \
            -H "accept: application/json" \
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1..." \
            -H "Content-Type: application/json" \
            -d "{
            "name": "Demoworkgroup2",
            "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL"
            }"

The response headers will be::

    HTTP/1.1 201 CREATED
    Connection: Keep-Alive
    Content-length: 394
    Content-type: application/json
    Date: Tue,10 May 2022 07:45:30 GMT
    Keep-alive: timeout=5,max=100
    Server: uvicorn
    Via: 1.1 <fqdn>


The response will be::

    {
        "dn": "cn=DEMOSCHOOL-Demoworkgroup2,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/workgroups/DEMOSCHOOL/Demoworkgroup_2",
        "ucsschool_roles": [
            "workgroup:school:DEMOSCHOOL"
        ],
        "udm_properties": {},
        "name": "Demoworkgroup2",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "description": null,
        "users": [],
        "create_share": true,
        "email": null,
        "allowed_email_senders_users": [],
        "allowed_email_senders_groups": []
    }



The queried school has to exist, whilst the ``workgroup`` to be created must **not** exist.
To create a ``workgroup`` its name and the corresponding school must be provided.
Optionally a ``description``, ``udm_properties``, ``users`` and/or ``create_share`` can be provided on creation.

Workgroups delete
-----------------

Example ``curl`` command to delete the workgroup ``Demoworkgroup2`` at ``DEMOSCHOOL`` ::

    $ curl  -X DELETE  "https://<fqdn>/ucsschool/kelvin/v1/workgroups/DEMOSCHOOL/Demoworkgroup2" \
            -H "accept: */*" \
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."


The response headers will be::

    HTTP/1.1 204 NO CONTENT
    Connection: keep-alive
    Date: Tue,10 May 2022 07:38:49 GMT
    Keep-alive: timeout=5,max=100
    Server: uvicorn
    Via: 1.1 <fqdn>

The server responses with 204 (with no body), if a workgroup got deleted successfully.
Matching of the queried ``workgroup`` *and* ``school`` is case-sensitive.
