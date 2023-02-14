Developer docu for building the UCS\@school Kelvin REST API
===========================================================

HTML is built using a Docker container with Sphinx: https://github.com/keimlink/docker-sphinx-doc

Initial docs
------------

The initial ``docs`` content was created with::

    $ docker run -u "$(id -u):$(id -g)" -it --rm -v "$(pwd)/docs":/home/python/docs keimlink/sphinx-doc:1.7.1 sphinx-quickstart docs

You don't have to do this anymore. This is here just for documentations sake.

Autobuild HTML docs during development
--------------------------------------

To have the HTML output served at http://127.0.0.1:8000 and auto-rebuild when a file is changed, do the following:

Start a Docker container that will build and serve the docs at http://127.0.0.1:8000::

    $ docker run -ti --rm -v "$PWD:/project" -w /project -u $UID --network=host --pull=always docker-registry.knut.univention.de/knut/sphinx-base:latest make -C docs livehtml

To stop the container hit ``Ctrl-C``.

Further information about the tooling for documentation can be found [here](https://git.knut.univention.de/univention/documentation/sphinx-docker)

Publish HTML documentation
--------------------------

The pipeline takes care of building and publishing the HTML and PDF. After
merging the documentation changes to the default branch, the ``docs-production``
job adds to the pipeline. Start it manually to run the job to publish the
content to the `docs.univention.de
<https://git.knut.univention.de/univention/docs.univention.de>`_ repository.

The job will fail, if no Sphinx build job that generate the needed artifacts
haven run before.

The documentation will be build automatically in our pipeline https://git.knut.univention.de/univention/docs.univention.de/-/pipelines
Check the [staged documentation](http://univention-repository.knut.univention.de/download/docs/).
You have to press a deploy button to publish the documentation.
