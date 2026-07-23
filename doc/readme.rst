.. SPDX-FileCopyrightText: 2021-2023 Univention GmbH
..
.. SPDX-License-Identifier: AGPL-3.0-only

Developer documentation for building the UCS\@school Kelvin REST API
====================================================================

The HTML is built with a Univention Docker container that runs Sphinx.

Initial docs
------------

You can render the content of ``docs`` and ``dev`` by using the following commands::

    $ cd ucsschool-kelvin-rest-api/doc
    $ make html

You don't have to do this anymore. This is here for documentation's sake.

Autobuild HTML docs during development
--------------------------------------

To have the HTML output served at http://127.0.0.1:8000 and auto-rebuild when a file is changed, do the following:

Start a Docker container that will build and serve the docs at http://127.0.0.1:8000::

    $ make livehtml-dev
    or
    $ make livehtml-docs

To stop the container hit ``Ctrl-C``.

For more information about the documentation tooling, see the `sphinx-docker
repository <https://git.knut.univention.de/univention/dev/docs/sphinx-docker>`_.

Publish HTML documentation
--------------------------

The pipeline takes care of building and publishing the HTML and PDF. After you
merge your documentation changes to the default branch, you can publish it.
Follow these steps:

1. Manually trigger the ``docs-merge-to-one-artifact`` job. After it completes,
   the ``docs-create-production-merge-request`` runs and creates a merge request
   with the content in the `docs.univention.de
   <https://git.knut.univention.de/univention/docs.univention.de>`_ downstream
   repository.

2. In the downstream repository, you become assignee of the merge request.
   GitLab automatically merges the merge request after successful tests. To
   pause the documentation release, you can deactivate the automatic merge in
   the merge request. You find the link to the merge request in the downstream
   part of the pipeline in the log output of the ``create merge request`` or in
   your assigned merge requests lists.

Depending on the automation progress of the downstream repository, you may have
to manually trigger the ``deploy`` there. It's planned to remove that manual
trigger.

If the manual ``deploy`` is still active, you need to trigger the ``deploy`` job
in the `downstream repository pipeline
<https://git.knut.univention.de/univention/docs.univention.de/-/pipelines>`_
running after the successful merge. You find the link to that pipeline in the
successful merged merge request.

Check the `staged documentation
<http://univention-repository.knut.univention.de/download/docs/>`_.
You have to press a deploy button to publish the documentation.
