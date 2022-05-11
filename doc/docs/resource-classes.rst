Resource Classes
================

The ``Classes`` resource represents the classes a school user is a member of.

The resource objects are represents as group objects in the LDAP.

``Classes`` can be created, retrieved, modified, deleted and searched for with the Kelvin API.

Resource representation
-----------------------
The following JSON is an example Classes resource in the *UCS\@school Kelvin REST API*::

    {
        "dn": "cn=DEMOSCHOOL-Democlass,cn=klassen,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/classes/DEMOSCHOOL/Democlass",
        "ucsschool_roles":[
            "school_class::school:DEMOSCHOOL"
        ],
        "udm_properties": {},
        "name": "Democlass",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "description": null,
        "users": [
            "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student"
        ]
    }


.. csv-table:: Property description
   :header: "name", "value", "Description", "Notes"
   :widths: 8, 5, 50, 18
   :escape: '

    "dn", "string", "dn of the LDAP", "read only"
    "url", "URL", "The URL of the class object in the UCS\@school Kelvin API.", "read only"
    "ucsschool_roles", "List<string>", "Reference to UCs\@school LDAP attributes.","read_only"
    "udm_properties", "Dictionary", "Key-value pair of mapped udm_properties within the UCS\@school Kelvin API.", "read_only"
    "name", "string", "Name of the class", "editable"
    "school", "URL", "The URL of the school object a class belongs to in the UCS\@school Kelvin API.", "read_only"
    "description","null|string","Descriptive information about a class.","editable"
    "users","List<URL>", "A list with the URL in the UCS\@school Kelvin API per user within the class.","editable"


List / Search
-------------

Example ``curl`` command to retrieve the list of all classes at ``DEMOSCHOOL`` ::

    $ curl  -X GET  "https://<fqdn>/ucsschool/kelvin/v1/classes/?school=DEMOSCHOOL" \
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
            "dn": "cn=DEMOSCHOOL-Democlass,cn=klassen,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
            "url": "https://<fqdn>/ucsschool/kelvin/v1/classes/DEMOSCHOOL/Democlass",
            "ucsschool_roles": [
                "school_class:school:DEMOSCHOOL"
            ],
            "udm_properties": {},
            "name": "Democlass",
            "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
            "description": null,
            "users": [
                "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student"
            ]
        }
    ]

Searching for classes (with ``?name=abc*`` or similar) is *not* supported and will return an empty response.

Retrieve
--------

Example ``curl`` command to retrieve the class ``Democlass`` at ``DEMOSCHOOL`` ::

    $ curl  -X GET  "https://<fqdn>/ucsschool/kelvin/v1/classes/DEMOSCHOOL/Democlass" \
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
        "dn": "cn=DEMOSCHOOL-Democlass,cn=klassen,cn=schueler,cn=groups,ou=DEMOSCHOOL,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/classes/DEMOSCHOOL/Democlass",
        "ucsschool_roles": [
            "school_class:school:DEMOSCHOOL"
        ],
        "udm_properties": {},
        "name": "Democlass",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "description": null,
        "users": [
            "https://<fqdn>/ucsschool/kelvin/v1/users/demo_student"
        ]
    }


The queried class must exist, matching is case-sensitive.
The response body will be identical to the response in the example above, if a school only has a single class registered.
Otherwise the list of classes from the example above will contain the ``class`` which has been requested.


Modify
------

Example ``curl`` command to modify the class ``Democlass2`` at ``DEMOSCHOOL`` ::

    $ curl  -X PATCH  "https://<fqdn>/ucsschool/kelvin/v1/classes/Demoschool/Democlass2" \
            -H "accept: application/json" \
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1N..." \
            -H "Content-Type: application/json" \
            -d "{
            "name": "Democlass_2"
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
        "dn": "cn=Demoschool-Democlass_2,cn=klassen,cn=schueler,cn=groups,ou=Demoschool,dc=******,dc=******",
        "url": "https://<fqdn>/ucsschool/kelvin/v1/classes/Demoschool/Democlass_2",
        "ucsschool_roles": [
        "school_class:school:Demoschool"
        ],
        "udm_properties": {},
        "name": "Democlass_2",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/Demoschool",
        "description": null,
        "users": []
    }

The example shows how to rename a certain ``class``. Optionally a ``description``, a list ``udm_properties`` and/or ``users`` can be modified.
But a ``class`` objects school can't be modified.


Create
------

Example ``curl`` command to create the class ``Democlass2`` at ``DEMOSCHOOL`` ::

    $ curl  -X POST  "https://<fqdn>/ucsschool/kelvin/v1/classes/" \
            -H "accept: application/json" \
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1..." \
            -H "Content-Type: application/json" \
            -d "{
            "name": "Democlass2",
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
        "dn": "cn=DEMOSCHOOL-Democlass2,cn=klassen,cn=schueler,cOptionally a ``description``, a list ``udm_properties`` and/or ``users`` can be provided on creation.
        ],
        "udm_properties": {},
        "name": "Democlass2",
        "school": "https://<fqdn>/ucsschool/kelvin/v1/schools/DEMOSCHOOL",
        "description": null,
        "users": []
    }



The queried has school exist, whilst the ``class`` to be created must **not** exist.
To create a ``class`` its name and the corresponding school must be provided.
Optionally a ``description``, a list ``udm_properties`` and/or ``users`` can be provided on creation.



Delete
------

Example ``curl`` command to delete the class ``Democlass2`` at ``DEMOSCHOOL`` ::

    $ curl  -X DELETE  "https://<fqdn>/ucsschool/kelvin/v1/classes/DEMOSCHOOL/Democlass2" \
            -H "accept: */*" \
            -H "Authorization: Bearer eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9..."


The response headers will be::

    HTTP/1.1 204 NO CONTENT
    Connection: keep-alive
    Date: Tue,10 May 2022 07:38:49 GMT
    Keep-alive: timeout=5,max=100
    Server: uvicorn  
    Via: 1.1 <fqdn>

There won't be a response, if a class got deleted successfully.

The ``class`` and ``school`` have to exist.