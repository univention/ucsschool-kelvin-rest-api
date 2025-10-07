.. :changelog:

.. The file can be read on the installed system at https://FQDN/ucsschool/kelvin/changelog

Changelog
=========

v3.1.1 (2025-10-07)
-------------------

* Fixed: A behavioral regression has been removed. When using the PATCH method and a import schema, the value is now
  removed again when setting ``None``. In versions 3.0.0 and 3.1.0, the schema was incorrectly re-evaluated
  and the attribute was filled with a value according to the schema
  (Issue :spelling:ignore:`univention/components/ucsschool-kelvin-rest-api#162`).

v3.1.0 (2025-09-25)
-------------------
* API behavior has been simplified: Attributes legal_guardians and legal_wards will always be present on returned user resources.
  The value of these attributes will be empty JSON arrays when the user does not have the required role (Issue :spelling:ignore:`univention/components/ucsschool-kelvin-rest-api#164`).
* Fixed: An undocumented and redundant attribute named ``user_type`` that was introduced with 3.0.0 has been removed (Issue :spelling:ignore:`univention/components/ucsschool-kelvin-rest-api#164`).

v3.0.0 (2025-09-02)
-------------------
* Fixed: Use ``stdout`` to fix problems with logrotate.
  As part of this change the init system in the container has been removed.
  Logs are still duplicated to the old ``http.log``,
  but can now also be viewed with ``univention-app logs ucsschool-kelvin-rest-api`` or
  ``journalctl APP_NAME=ucsschool-kelvin-rest-api``.
  The log rotate of ``http.log`` is now handled by the UCS host system (:uv:bug:`56048`).
* Fixed: Certificates are now mounted from the UCS host system (:uv:bug:`51728`).
* Fixed: Error when creating a new school in a single-server environment (:uv:bug:`58448`).
* Fixed: Getting a school that was created with the setting to not create noneducational objects (UCR-V ``ucsschool/ldap/noneducational/create/objects`` is set to false) (:uv:bug:`57261`).
* Fixed: School admins are now fully supported in kelvin (:uv:bug:`54051`).
* Feature: Add legal guardian role to Kelvin (Issue :spelling:ignore:`univention/components/ucsschool-kelvin-rest-api#154`).

v2.0.0 (2025-03-14)
-------------------
* The Kelvin API now validates user names by default to avoid that they contain Windows reserved names (Issue :spelling:ignore:`univention/ucsschool#1052`).
  See `Microsoft Documentation <https://learn.microsoft.com/en-us/windows/win32/fileio/naming-a-file>`_ for more information about the affected reserved names.
* Removed dependency on internal OPA service. No changes in behavior (Issue  :spelling:ignore:`univention/components/ucsschool-kelvin-rest-api#145`).

v1.10.3 (2024-12-09)
--------------------
* Fixed: The patch endpoint for school classes and work groups now accepts an empty list to clear all members (:uv:bug:`57771`).

v1.10.2 (2024-10-07)
--------------------
* Fixed: When restarting the OPA service, a crash was possible when the API is under high load (:uv:bug:`57000`).

v1.10.1 (2024-07-25)
--------------------
* Fixed a bug that would lead to misleading log messages when changing the password hashes of a user (:uv:bug:`56590`).
* Swagger UI dependencies are now served statically instead of using CDNs (:uv:bug:`56314`).

v1.10.0 (2024-03-05)
--------------------
* Changed: The API base url, for example the portal link, now redirects to the OpenAPI docs page (:uv:bug:`55556`).
* Fix: The HEAD endpoint for schools could return an outdated result due to a caching issue (Issue #108).
* Fix: The GET endpoint for schools does now return "None" for non-existing file servers instead of raising an error (Issue #137).

v1.9.0 (2023-10-17)
-------------------
* The hostname for objects in the Kelvin API is no longer case sensitive (:uv:bug:`54305`).
* The UCS\@school Kelvin REST API UCS\@school app can now only be installed if the UCS\@school app is locally installed. (:uv:bug:`54333`).
* Fixed a cache issue where a correct object URL could still lead to a 404 response (:uv:bug:`56699`).
* Disable OPA telemetry (:uv:bug:`56193`).

v1.8.10 (2023-08-24)
--------------------
* Re-enable username validation checks for creation and modification of users (Issue #98).
* Remove all old school groups from user when removed from a school (:uv:bug:`56121`).
* Automatically add all school groups to user when added to a school (:uv:bug:`56121`).
* The UCR-V ``ucsschool/validation/username/windows-check`` is used during username validation (:uv:bug:`56152`)

v1.8.9 (2023-05-19)
-------------------
* Fix group membership when removing admins from schools (:uv:bug:`55986`).
* Update upstream dependencies to fix security vulnerability (:uv:bug:`56097`).

v1.8.8 (2023-05-04)
-------------------
* Validate usernames to avoid Windows reserved names (:uv:bug:`53519`).
* Return HTTP 404 for non existing roles, instead of 422 (Issue #83).

v1.8.7 (2023-03-30)
-------------------
* Prevent logging of sensitive information, such as passwords, in the OPA log (Issue #71).

v1.8.6 (2023-03-07)
-------------------
* Fix error in ``udm_properties`` check for school classes (Issue #72).
* The script ``update_openapi_client`` no longer fails due to multiple ``jar``-files (Issue id-broker-plugin#17).
* UCS\@school lib hooks were not called when the UCS\@school Kelvin REST API was called. This has been fixed (Issue #61).

v1.8.5 (2023-02-22)
-------------------
* Fix ``h11._util.LocalProtocolError: Can't send data when our state is ERROR`` traceback (:uv:bug:`55730`).
* General performance improvements, with focus on object existence, searches and user creation (Issue #56).
* Upgrade to Python 3.11 (Issue #56).

v1.8.4 (2023-02-16)
-------------------
* Security fix in login (Issue #64).

v1.8.3 (2023-01-16)
-------------------
* Unhandled exceptions are logged (:uv:bug:`55114`).
* Move operations succeed, when a language header is set.

v1.8.2 (2022-12-20)
-------------------
* Speed up validation when creating or changing users (:uv:bug:`55384`).
* Use the LDAP client library ``uldap3`` instead of a custom implementation to get better support and improved performance during direct LDAP calls (Issue #50).

v1.8.1 (2022-12-07)
-------------------
* Compare OU names case insensitive (:uv:bug:`55472`).
* Calculate group names using OU names from LDAP (:uv:bug:`55456`).
* Fixed: Setting UCS\@school roles with context type school in PATCH led to inconsistent UCS\@school Users (Issue #47).

v1.8.0 (2022-11-11)
-------------------
* Add support for arbitrary context types for users (:uv:bug:`55355`).
* Added a configuration option to enable the evaluation of password policies when creating UCS\@school users (:uv:bug:`55408`).
* Internal: Added option to check password policies when creating or modifying users (:uv:bug:`55393`).
* Added the possibility to send an Accept-Language header with each request.
* All forwarded UDM errors are now structured the same way as FastAPI validation errors (Issue #30).
* Fixed handling of role strings attribute if schools attribute is empty.

v1.7.0 (2022-07-18)
-------------------
* **Breaking change for UCS\@school Kelvin REST API clients below ``1.7.0``**: Add work group support in user resource (:uv:bug:`54891`).
* Allow the creation of school classes without share (:uv:bug:`54875`).
* Add a correlation ID to the headers of requests and responses. Write the ID to the log (Issue #25).
* App Center scripts were added to keep the state of UCR variables, which are set manually inside the docker container (:uv:bug:`54959`).
* The request time is now added to the log file (Issue #28).
* Validation errors are logged as warnings to make filtering the log easier (Issue #895).
* Add HEAD /schools/{school_name} endpoint (Issue #24).
* Allow mapping UDM properties to work groups (:uv:bug:`55259`).
* The ``multipart`` library output is not logged anymore (at ``DEBUG`` level), when retrieving a token (Issue #27).

v1.6.0 (2022-08-24)
-------------------
* Security Issue: An error causing group shares to be created with wrong permissions has been fixed. The permissions of existing shares will be fixed during the joinscript (:uv:bug:`55103`).
* Creating schools with OU names including underscores is now allowed, if the DC name is passed, too (:uv:bug:`55125`).


v1.5.6 (2022-06-30)
-------------------
* Remove create_share from school class objects to avoid conflicts with older Kelvin client versions (:uv:bug:`54916`).

v1.5.5 (2022-06-23)
-------------------
* Add work group resource (:uv:bug:`54876`).
* Allow the creation of school classes without share (:uv:bug:`54875`).
* Entering an invalid school URL does result in HTTP error-code 422 instead of 500 (:uv:bug:`52895`).
* Enable log rotation of the Open Policy Agent (:uv:bug:`54247`).
* The validation was adapted to prevent invalid school names in multi-server environments (:uv:bug:`54793`).
* An error has been fixed, which was raised by invalid UCS\@school roles during the validation (:uv:bug:`54653`).
* Improve date validation error messages (:uv:bug:`54812`).
* Added documentation for the classes resource (:uv:bug:`52734`).
* Updated descriptions of variables in the Swagger UI to fit the expected values and added JSON Examples to descriptions where needed (:uv:bug:`54739`).


v1.5.4 (2022-04-27)
-------------------
* The valid date range is now specified (:uv:bug:`54668`).
* A new App Setting was added to configure the amount CPU cores utilized by the UCS\@school Kelvin REST API (:uv:bug:`54575`).
* It is now possible to define multiple schools for users via PATCH and PUT requests (:uv:bug:`54481`, :uv:bug:`54690`).

v1.5.3 (2022-02-08)
-------------------
* Fixed token requests with authorized user and wrong password leading to ``HTTP 500`` (:uv:bug:`54431`).
* The user get route now uses the correct filter when searching for UDM mapped properties (:uv:bug:`54474`).

v1.5.2 (2022-01-07)
-------------------
* The Kelvin API can now be installed on servers with the role DC Primary and DC Backup (:uv:bug:`54310`).

v1.5.1 (2021-11-30)
-------------------
* The Open Policy Agent component was added to components documentation (:uv:bug:`53960`).
* The log output of the Open Policy Agent is now written to ``/var/log/univention/ucsschool-kelvin-rest-api/opa.log`` (:uv:bug:`53961`).
* The test suite for the ``ucsschool.lib`` component was improved (:uv:bug:`53962`).
* Username generation counter can now be raised above 100 (:uv:bug:`53987`).
* The ``no_proxy`` environment variable is now honored by the Kelvin REST API when accessing the UDM REST API (:uv:bug:`54066`).
* The user resource now has an ``expiration_date`` attribute, which can be used to set the account expiration date. A user won't be able to login from that date on (:uv:bug:`54126`).

v1.5.0 (2021-09-10)
-------------------
* Unix homes are now set correctly for users. (:uv:bug:`52926`)
* The Kelvin API now supports udm properties on all Kelvin resources except roles. (:uv:bug:`53744`)

v1.4.4 (2021-06-29)
-------------------
* The Kelvin API now supports UDM REST APIs using certificates, which are not signed by the UCS-CA. (:uv:bug:`52766`)
* The UCS\@school object validation now validate groups, schools and roles case-insensitive. (:uv:bug:`53044`)

v1.4.3 (2021-06-16)
-------------------
* A security error was fixed, that allowed the unrestricted use of the Kelvin API with unsigned authentication tokens.
  Please update as fast as possible (:uv:bug:`53454`)!

v1.4.2 (2021-05-26)
-------------------
* Support for hooks for objects managed by classes from the package ``ucsschool.lib.models`` was added. See manual section `Python hooks for pre- and post-object-modification actions <https://docs.software-univention.de/ucsschool-kelvin-rest-api/installation-configuration.html#python-hooks-for-pre-and-post-object-modification-actions>`_ for details (:uv:bug:`49557`).
* An error when creating usernames with templates was fixed (:uv:bug:`52925`).

v1.4.1 (2021-05-03)
-------------------
* No error message is logged anymore after the deletion of an object (:uv:bug:`52896`).
* Repeated restarts of the Kelvin server have been fixed.

v1.4.0 (2021-04-20)
-------------------
* The FastAPI framework has been updated to version ``0.63.0``.
* Open Policy Agent was added for access control and implemented partially for the user resource.
* The Kelvin API now supports creating schools.

v1.3.0 (2021-02-18)
-------------------
* It is now possible to change the roles of users. See manual section `Changing a users roles <https://docs.software-univention.de/ucsschool-kelvin-rest-api/resource-users.html#changing-a-users-roles>`_ for details (:uv:bug:`52659`).
* Validation errors when reading malformed user objects from LDAP now produce more helpful error messages (:uv:bug:`52368`).
* UCS\@school user and group objects are now validated before usage, when loading them from LDAP. See manual sections `Resources <https://docs.software-univention.de/ucsschool-kelvin-rest-api/resources.html#resources>`_ and `Backup count of validation logging <https://docs.software-univention.de/ucsschool-kelvin-rest-api/installation-configuration.html#backup-count-of-validation-logging>`_ for details (:uv:bug:`52309`).
* A bug setting the properties ``profilepath`` and ``sambahome`` to empty values when creating users has been fixed (:uv:bug:`52668`).

v1.2.0 (2020-11-12)
-------------------
* Improve user resource search speed: find all matching users with one lookup (:uv:bug:`51813`).
* Add fallback for retrieving LDAP connection settings from UCR if environment variables are not available (:uv:bug:`51154`).
* Add attribute ``kelvin_password_hashes`` to user resource. It allows overwriting the password hashes in the UCS LDAP with the ones delivered. Use only if you know what you're doing!

v1.1.2 (2020-08-11)
-------------------
* The OpenAPI schema of the UDM REST API has been restricted to authenticated users. The Kelvin API now uses the updated ``update_openapi_script``, passing credentials to update the OpenAPI client library (:uv:bug:`51072`).
* The school class resource has been modified to accept class name containing only one character (:uv:bug:`51363`).
* Setting and changing the ``password`` attribute has been fixed (:uv:bug:`51285`).
* The UCS CA is now registered in the HTTP client certification verification backend to prevent SSL certification errors when communicating with the UDM REST API on the Docker host (:uv:bug:`51510`).
* The ``school_admin`` role is now supported (:uv:bug:`51509`).
* Update Docker image base to Alpine 3.12, updating Python to 3.8 (:uv:bug:`51768`).

v1.1.1 (2020-06-15)
-------------------
* The validation of the ``name`` attribute of the ``SchoolClass`` resource has been fixed to allow short class names like ``1``.
* The ``password`` attribute of the ``User`` resource has been fixed.
* The signatures of the ``UserPyHook`` methods have been adapted to be able to await asynchronous methods.
* The UCS CA is now added to the ``certifi`` SSL certification store.
* Support for the ``school_admin`` role was added.


v1.1.0 (2020-04-15)
-------------------
* The UDM REST API Python Client library has been updated to version ``0.4.0``, so it can handle authorized access to the UDM REST API OpenAPI schema.

v1.0.1 (2020-02-17)
-------------------
* The ucsschool lib has been extended to allow for context types other than ``school`` in ``ucsschool_roles`` attribute of most resources.

v1.0.0 (2020-01-20)
-------------------
* Initial release.
