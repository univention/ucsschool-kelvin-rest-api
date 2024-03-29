.. SPDX-FileCopyrightText: 2021-2023 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

.. _install-and-config:

Installation and configuration
==============================

Installation
------------

The app *UCS\@school Kelvin REST API* must be installed on the DC master or DC backup.
This can be done either through the UMC module *Univention App Center* or on the command line:

.. code-block:: console

    $ univention-app install ucsschool-kelvin-rest-api

The join script :file:`50ucsschool-kelvin-rest-api.inst` should run automatically.
To verify if it succeeded, open the *Domain join* UMC module or run:

.. code-block:: console

    $ univention-check-join-status

If it hasn't run, start it in the UMC module or execute:

.. code-block:: console

    $ univention-run-join-scripts

If problems occur during installation or join script execution, relevant log files are:

#. :file:`/var/log/univention/appcenter.log`
#. :file:`/var/log/univention/join.log`

Configuration
-------------

The *UCS\@school Kelvin REST API* can be used out of the box, but there are various parameters that can be configured.

.. hint::

   The command ``univention-app configure --list ucsschool-kelvin-rest-api``
   lists all available app settings and their current values.

.. hint::

   App Settings can be changed using the command line with ``univention-app
   configure ucsschool-kelvin-rest-api --set ucsschool/kelvin/log_level=DEBUG &&
   univention-app restart ucsschool-kelvin-rest-api``


Number of cores
^^^^^^^^^^^^^^^

The number of CPU cores used by the *UCS\@school Kelvin REST API* app can be configured.
The default is ``2``. Values below ``1`` start one process for each available CPU.
The value can be changed through the *app settings* of the *UCS\@school Kelvin REST API* app in the *Univention App Center* UMC module.

.. _configuration-token-validity:

Token validity
^^^^^^^^^^^^^^

All HTTP requests to resources must carry a valid JWT token. The number of minutes a token is valid can be configured. The default is ``60``. The value can be changed through the *app settings* of the *UCS\@school Kelvin REST API* app in the *Univention App Center* UMC module.

Custom CA Certificates
^^^^^^^^^^^^^^^^^^^^^^^

By default, the *UCS\@school Kelvin REST API* only connects to an LDAP server which is using the CA provided by UCS. If the LDAP server uses a different CA, that CA needs to be configured through the *app settings* in the *Univention App Center* UMC module.

Log level
^^^^^^^^^

The minimum severity for log messages written to :file:`/var/log/univention/ucsschool-kelvin-rest-api/http.log` can be configured. The default is ``INFO``. The value can be changed through the *app settings* of the *UCS\@school Kelvin REST API* app in the *Univention App Center* UMC module.

Backup count of validation logging
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
The UCR variable ``ucsschool/validation/logging/backupcount`` sets the amount of copies of the log file ``ucs-school-validation.log``, which should be kept in rotation. The default is ``60``. The host's UCR-V is copied into the Docker container during the join script.
To change it for the *UCS\@school Kelvin REST API*, it has to be modified inside the Docker container.

Configuration of user object management (import configuration)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The directory :file:`/var/lib/ucs-school-import/configs` is mounted as a *volume* into the Docker container where the *UCS\@school Kelvin REST API* runs. This makes it accessible from the host as well as from inside the container.

The directory contains the file ``kelvin.json``, which is the top level configuration file for the UCS\@school import code, executed when ``user`` objects are managed.
Documentation for the UCS\@school import configuration is available only in German in :cite:t:`uv-ucsschool-import`.

.. _configuration-udm-properties:

UDM Properties
^^^^^^^^^^^^^^

Previous versions of Kelvin already had ``udm_properties`` functionality available for user resources.
With the release of Kelvin 1.5.0, the ``udm_properties`` functionality is also supported for all other resources
(except roles) as well. The list of ``mapped_udm_properties`` can be configured in
:file:`/etc/ucsschool/kelvin/mapped_udm_properties.json`.

The format of the ``mapped_udm_properties.json`` is::

    {
        "name_of_resource": ["name_of_property_to_map",...],
        ...
    }

For example:

.. code-block:: json

    {
        "user": ["unixhome", "title"],
        "school_class": ["mailAddress"],
        "school": ["description"]
    }

The following restrictions have to be observed:

#. The Kelvin configuration may also contain a ``mapped_udm_properties``. This refers to the user resource.
   If there is also a configuration for the key ``user`` in ``mapped_udm_properties.json``, it will override the
   ``mapped_udm_propertes`` Kelvin configuration (for users only).
#. Any udm property that is directly linked to an already existing model field results in an invalid configuration.
   It is not allowed, for example, to configure the ``description`` of a school class as an udm property, since it is
   already present in the model itself. This is now also true for the user resource, where this was possible before.

.. important::

   Please be advised that this direct access to udm properties is in no way
   checked or validated by any UCS\@school logic and thus can lead to corrupt
   objects and errors on your system, if not used correctly.

Python hooks for user object management (import hooks)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

*Read next chapter about hooks for non-user objects like school classes.*

The directory :file:`/var/lib/ucs-school-import/kelvin-hooks` is mounted as a *volume* into the Docker container, so it can be accessed from the host. The directory content is scanned when the Kelvin API server starts.
If it contains classes that inherit from ``ucsschool.importer.utils.import_pyhook.ImportPyHook``, they are executed when users are managed through the Kelvin API.
The hooks are very similar to the Python hooks for the UCS\@school import (see :cite:t:`uv-ucsschool-import`).
The differences are:

* Python 3.7 only
* Only three types of hooks are executed: ``UserPyHook``, ``FormatPyHook`` and ``ConfigPyHook`` (all located in modules in the ``ucsschool.importer.utils`` package).
* ``self.dry_run`` is always ``False``
* ``self.lo`` is always a LDAP connection with write permissions (``cn=admin``) as ``dry_run`` is always ``False``
* ``FormatPyHook`` and ``ConfigPyHook`` are the same as in the UCS\@school import, but a ``UserPyHook`` hook instance has an additional member ``self.udm``.

``self.udm`` is an instance of ``udm_rest_client.udm.UDM`` (see `Python UDM REST Client`_).
It can be used to comfortably query the UDM REST API running on the DC master.
When using the UCS\@school lib or import, it must be used in most places that ``self.lo`` was used before.

**Important**: When calling methods of *ucsschool* objects (e.g. ``ImportUser``, ``SchoolClass`` etc.) ``self.udm`` must be used instead of ``self.lo`` and those methods may have to be used with ``await``. Thus hooks methods will be ``async``.
For example:

.. code-block:: python

    async def post_create(self, user: ImportUser) -> None:
        user.firstname = "Sam"
        awaituser.modify(self.udm)

        udm_user_obj = await user.get_udm_object(self.udm)
        udm_user_obj["foo"] = "bar"
        await udm_user_obj.save()  # UDM REST Client object: "save", not "modify"


Python hooks for pre- and post-object-modification actions
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

*Read previous chapter about hooks for user objects.*

Since version ``1.4.2`` of the *UCS\@school Kelvin REST API* app it is possible to execute custom Python code before and after the creation, modification, moving or deletion of any UCS\@school object.

To use the hook functionality a Python class deriving from ``ucsschool.lib.models.hook.Hook`` (`https://github.com/.../hook.py <https://github.com/univention/ucs-school/blob/feature/kelvin/ucs-school-lib/modules/ucsschool/lib/models/hook.py>`_) must be created.

In the class methods ``pre_create()``, ``post_create()``, ``pre_modify()`` and so on can be implemented. They will be executed at the specified time.

The Python module with the hook class must be stored in the directory ``/var/lib/ucs-school-lib/kelvin-hooks``. Please note that it is a different directory than the one from the previous chapter.

Two examples can be found at `https://github.com/.../hook_example1.py
<https://github.com/univention/ucs-school/blob/feature/kelvin/ucs-school-lib/usr/share/doc/python-ucs-school/hook_example1.py>`_ and `https://github.com/.../hook_example2.py
<https://github.com/univention/ucs-school/blob/feature/kelvin/ucs-school-lib/usr/share/doc/python-ucs-school/hook_example2.py>`_.

The API for those hooks is almost identical to the one described in `Python hooks for user object management (import hooks)`_.
The main differences are that the attribute ``self.dry_run`` does not exist, a UCR instance is available in ``self.ucr`` and the class attribute ``model``.

The class attribute ``model`` is used to determine for objects of which classes (models) the hook should be executed.
The hook will also be executed for subclasses of the one defined here.
If for example ``model = Teacher`` (from module ``ucsschool.lib.models.user``), the hooks methods would also be execute for objects of ``TeachersAndStaff``, but not for those of type ``Staff`` or ``Student`` (as they are not derived from ``Teacher``).

The class attribute ``priority`` defines the order in which methods of hooks for the same type (same ``model``) are executed, or if they are deactivated.
Methods with higher numbers are executed before those with lower numbers.
If the value is ``None`` the method will not run.

The methods ``pre_create()``, ``post_modify()`` and so on receive the object being modified and return ``None``.
The type of ``obj`` is the one in ``model`` (or a subclass).

To add custom initialization code, ``__init__()`` can be implemented the following way:

.. code-block:: python

    from ucsschool.lib.models.hook import Hook
    # from udm_rest_client import UDM
    # from univention.admin.uldap import LoType

    class MailForSchoolClass(Hook):
        def __init__(self, udm: UDM, lo: LoType = None, *args, **kwargs) -> None:
            super(MailForSchoolClass, self).__init__(udm, lo, *args, **kwargs)
            # From here on self.lo, self.logger and self.ucr are available.
            # You code here.

To activate a hook, or or a change to a hook, restart the *UCS\@school Kelvin REST API* Docker container:

.. code-block:: console

    $ /etc/init.d/docker-app-ucsschool-kelvin-rest-api restart


Further reading about the UCS\@school hooks is available for German readers in :ref:`pyhooks` in :cite:t:`uv-ucsschool-manual`.
Please note that the example in that text is for the synchronous variant, missing the ``async/await`` keywords and not using the UDM REST API client. Compare with the examples linked in this chapter.


File locations
--------------

Log files
^^^^^^^^^

:file:`/var/log/univention/ucsschool-kelvin-rest-api` is a volume mounted into the docker container, so it can be accessed from the host.
The directory contains the file ``http.log``, which is the log of the HTTP-API (both ASGI server and API application)
and the file ``ucs-school-validation.log``, which is used to write sensitive information during the UCS\@school validation.

User object (import) configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

:file:`/var/lib/ucs-school-import/configs` is a volume mounted into the docker container, so it can be accessed from the host.
The directory contains the file ``kelvin.json``, which is the top level configuration file for the UCS\@school import code that is executed as part of the *UCS\@school Kelvin REST API* that runs inside the Docker container when user objects are managed.


Python hooks
^^^^^^^^^^^^

:file:`/var/lib/ucs-school-import/kelvin-hooks` and :file:`/var/lib/ucs-school-lib/kelvin-hooks` are volumes mounted into the docker container, so they can be accessed from the host.
Their purpose is explained above in chapters `Python hooks for user object management (import hooks)`_ and `Python hooks for pre- and post-object-modification actions`_.


.. _`Python UDM REST Client`: https://udm-rest-client.readthedocs.io/en/latest/
