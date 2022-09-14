Resource Status
===============

The ``Status`` resource can be used to retrieve information about the state of the server.
Currently the response contains two values: ``internal_errors_last_minute`` and ``version``.

Clients can use the ``internal_errors_last_minute`` information in their monitoring or load balancing setups.

Clients can use the ``version`` information to for example access features on the server, that are only available in certain versions.

For ease of use in monitoring setups, the ``/status`` endpoint does not require authentication.

The resource objects have no direct representation in LDAP.

There is currently only one endpoint, that returns a single item.

Status resource representation
------------------------------

The following JSON is an example Status resource in the *UCS\@school Kelvin REST API*:

.. code-block:: json

    {
        "internal_errors_last_minute": 0,
        "version": "1.7.0"
    }

.. csv-table:: Property description
   :header: "name", "value", "Description", "Notes"
   :widths: 3, 2, 8, 3
   :escape: '

    "internal_errors_last_minute", "int", "The number of HTTP 500 status messages, the server returned in the last minute.", "read only"
    "version", "string", "The version of the Kelvin REST API app.", "read only"


Status retrieve
---------------

Example ``curl`` command to retrieve a single status object:

.. code-block:: console

    $ curl -X GET "https://<fqdn>/ucsschool/kelvin/v1/status"\
        -H "accept: application/json"
