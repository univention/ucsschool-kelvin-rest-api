# UCS@school Kelvin REST API

This repository contains the code for the UCS@school Kelvin REST API application.
The application provides HTTP endpoints to create and manage UCS@school domain objects like school users, school classes, schools (OUs) and computer rooms.
See the [public documentation](https://docs.software-univention.de/ucsschool-kelvin-rest-api/) for its usage and configuration.

## Versions

### v2

Version `2` of the Kelvin REST API keeps the endpoints and data representation of `v1`,
but adds a read-cache and removes support for read-hooks.

Kelvin `v2` keeps the write-path of `v1` — using the UCS@school (import) library to call the UDM REST API.
Before returning the UDM→Kelvin transformed response to the HTTP client,
it stores the data in an SQL database.
Read-requests are served from this SQL database,
massively improving read performance.

Because the read-path doesn't use the UCS@school and UCS@school import libraries,
their read-hooks aren't executed.
Although the data representation is compatible with `v1`,
this is a breaking behavioral change.

The SQL database stores UCS@school objects in the representation planned for future (`v3+`) releases.
For backwards-compatibility,
`v2` transforms that representation to `v1`'s format before returning it.
Kelvin `v2` uses the `ucsschool-objects` library to handle querying and manipulating UCS@school objects.
See [ucsschool-objects/README.md](ucsschool-objects/README.md) for details.

Data in OpenLDAP is not only written by the UDM REST API on Kelvin's behalf.
Other UDM REST API clients also change LDAP data without Kelvin's knowledge.
To keep the read cache in the SQL database _eventually consistent_ with data in LDAP,
Kelvin has a companion service that is triggered by LDAP modifications.
Changes to LDAP create events in the
[Provisioning event system](https://docs.software-univention.de/manual/5.2/en/domain-ldap/nubus-provisioning-service.html#nubus-provisioning-service).
A "Provisioning Consumer",
running as a sidecar to the Kelvin REST API container,
reads the event queue and updates data in the SQL database using the `ucsschool-objects` library.

```text
                                   HTTP clients
                                        │
                                        ▼
                                  Kelvin REST API                          (kelvin-api/)
                                 /          \    \
                              write       cache   read
                               /           write    \
                              /         responses    \
                             /                  \     \
                            ▼                    ▼     ▼
        UCS@school library & import             ucsschool-objects          (ucsschool-objects/)
  (ucs-school-lib/,│       │                        ▲     │
   ucs-school-import/)     │                        │     │
                   │       │                        │     │
                   ▼       │                        │     │
  (Nubus)    UDM REST API  │                        │     │
                   │       │                        │     │
                   │       │ (sometimes             │     │
                   │      /   direct LDAP)          │     │
                   ▼     ▼                          │     ▼
  (Nubus)         OpenLDAP                          │  SQL database        (PostgreSQL)
                     │                              │
                     ▼                              │
        Provisioning event system  ────────►  Provisioning Consumer        (Nubus Provisioning)
        (LDAP change events)                   (kelvin-api sidecar)
```

### v1

Version `1` of the Kelvin REST API is a frontend for the UCS@school and UCS@school import libraries.
Those read and write data from/to the UDM REST API, which handles persistence with OpenLDAP.
Sometimes they connect to OpenLDAP directly to improve performance or because UDM doesn't expose a required attribute.

```text
      HTTP clients
           │
           ▼
      Kelvin REST API          (kelvin-api/)
           │
           ▼
UCS@school library & import    (ucs-school-import/, ucs-school-lib/)
           │        │
           ▼        │
      UDM REST API  │          (Nubus)
           │       /
           │      /   (sometimes direct LDAP for performance
           │     /     or missing UDM attributes)
           ▼    ▼
          OpenLDAP             (Nubus)
```

## App release

### Checklist

_You may copy this to a gitlab release issue_

- [ ] Check contents of [kelvin-api/changelog.rst](./kelvin-api/changelog.rst)
- [ ] Kelvin [Jenkins tests](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API%20(branch%20main)/) OK
- [ ] Kelvin client [Jenkins test](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/Kelvin-client-daily) OK
- [ ] Jenkins in [test appcenter](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API)
- [ ] Create git tag with version you want to publish
- [ ] Monitor the pipeline and follow instructions in manual steps
- [ ] API still works (smoke test)
- [ ] Release QA (upgrade and smoke test)
- [ ] Close issues & bugs

### Details

Details for some steps in the checklist.

For many steps, you will need the component id string, for example `ucsschool-kelvin-rest-api_2022050407282`.
You may run `univention-appcenter-control status ucsschool-kelvin-rest-api` and look at the newest not yet published entry to get the correct component id.
It can also be found here https://appcenter-test.software-univention.de/meta-inf/4.4/ucsschool-kelvin-rest-api/, by navigating to the last version or in the provider portal.
The component id will be referred to by using `COMPONENT_ID`.

#### Verify changes have been uploaded to the test appcenter

Exchange `COMPONENT_ID` in the following URL with your target component id and check if the files have been updated.

```text
https://appcenter-test.software-univention.de/univention-repository/5.0/maintained/component/COMPONENT_ID/
```

At least the `README_UPDATE_*` files which contain the version should have been updated by the gitlab job.

#### Release a new app version

- Create a new tag with the version number you want to release, e.g.: `release-1.1.0`
- Wait for the tag pipeline until it reaches the `do_release` job
- Is everything looking good so far? The next will make the new version public!
- Start the `do_release` job

#### Publish documentation

The documentation is build automatically when changes are pushed in `doc/docs/**/*`.
The job to copy the documentation `docs-production` to the repository `docs.univention.de` must be triggered manually.

The pipeline rule definition has two conditions in **one** rule. The
_docs-production_ is only created when the files below `doc/docs/**/*` changed
**AND** when the branch is the default branch. This means, you need to develop
your documentation changes in a feature branch. And after the merge to the
default branch, the job starts, because it is in the default branch and
documentation files were changed. To run the job, you need to start it manually.

The commit in `docs.univention.de` will also trigger a pipeline, which will do the actual release.

Refer to the wiki page https://hutten.knut.univention.de/mediawiki/index.php/Docs/Deployment
for more information regarding the documentation pipeline.

#### Create a new unpublished version in the appcenter

A new app version is created for the default branch and merge requests through a pipeline job.

## Automatic Docker image build

The docker images are automatically built in the project's [docker registry](https://git.knut.univention.de/univention/components/ucsschool-kelvin-rest-api/container_registry).
The following rules apply:

- If you commit on **any** branch an image will be built with the tag `branch-$CI_COMMIT_REF_SLUG`. These images will be
  cleaned up after 30 days
- If you create a tag on **any** branch an image will be built with the tag as the tag. These images will not be cleaned up.

This allows for the following development flow:

- Create a new feature branch for your work
- If applicable create a new Kelvin version in the Test Appcenter and set the docker image to the branch image, like:
  `gitregistry.knut.univention.de/univention/components/ucsschool-kelvin-rest-api:branch-$CLI_COMMIT_REF_SLUG`
- After each commit and pipeline run you can install the app with the new docker image. You will find the name in the build pipeline.

## Use custom app version in Jenkins jobs

The Jenkins job [kelvin API tests](https://jenkins2022.knut.univention.de/job/UCSschool-5.0/job/kelvin%20API%20(branch%20main)/) and [kelvin API tests](https://jenkins2022.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API/) can be configured to use a custom app version.
In the 'Build with parameters' page, insert your app version into the `UCSSCHOOL_KELVIN_REST_API_VERSION` configuration variable.
One source for custom app versions is the app release component pipelines, which are run for a merge request.
To find the app version, scroll to the bottom of the job log of the job `create_app_version`.

## Use custom app versions on test vm

For this, you need to activate the Test Appcenter.

To install the Kelvin application with the new merge request app version you just install the custom version:

```
univention-app install ucsschool-kelvin-rest-api='$APP_VERSION'
```

# Development Setup

This section gathers information for development setup.
Everything here is optional.

Many dev tasks are collected in a [Makefile](./Makefile).
Just run `make` in the project directory, to get an overview over available recipes.

## Run Kelvin locally

For fast development, you can run the Kelvin container locally on your notebook.
A proper UCS instance is still required for the UDM REST API and some credentials.
To run the container locally you have to do the following:

```shell
make fetch-vm-data TARGET="IP OF UCS WHERE KELVIN WOULD BE INSTALLED"
make dev-server
```

Changes to the source code are automatically synced to the running container
and should have an immediate effect.

## Installation of python packages

It is useful to have all packages installed during development, so that the IDE can autocomplete and lint correctly.
Please be aware that python-ldap is a dependency of univention-lib-slim. This python package requires to build some C-extensions and has
some additional requirements. Please follow the instructions provided [here](https://www.python-ldap.org/en/python-ldap-3.4.3/installing.html#installing-from-pypi)

The Kelvin project uses [uv](https://docs.astral.sh/uv/) as a project manager. To get a virtual environment with all required packages installed,
simply run `uv sync`. To run any command within this venv, simply run `uv run $COMMAND`.

## Create alembic migrations

```shell
make alembic-migration
```

## pre-commit

The pipeline for this repository has a [pre-commit](https://pre-commit.com/) job which prevents code from being merged which does not conform to the pre-commit programs and configuration.
You should run pre-commit checks before push you can use either pre-commit in a python3.11 environment or use docker.
This will save you and your co-workers from having much headache.

To test if everything works fine, just run pre-commit with the `-a` option:

```
pre-commit run -a
```
