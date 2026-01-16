# UCS@school Kelvin REST API

This repository contains the code for the UCS@school Kelvin REST API application.
The application provides HTTP endpoints to create and manage UCS@school domain objects like school users, school classes, schools (OUs) and computer rooms.
See the [public documentation](https://docs.software-univention.de/ucsschool-kelvin-rest-api/) for its usage and configuration.

## App release

### Checklist

_You may copy this to a gitlab release issue_

- [ ] Check contents of [kelvin-api/changelog.rst](./kelvin-api/changelog.rst)
- [ ] Update version in [kelvin-api/VERSION.txt](./kelvin-api/VERSION.txt)
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

## Update remote Kelvin installation

If you have a Kelvin installation on a UCS VM, you can update this instance with locally changed code, by using the script `autoupdate-kelvin-container`.

## Fast development and test execution in VM and docker container

Setup a UCS@school primary node and install the docker container of your feature branch:

``` shell
notebook# ssh root@10.201.2.135
uasvm# univention-install univention-appcenter-dev ; univention-app dev-use-test-appcenter
uasvm# univention-app install ucsschool-kelvin-rest-api=0.0.0-sschwardt-school-admins
```

Then grab a new shell and start the autoupdater helper, that is using `rsync` and `inotifycopy` from our toolshed repo:

``` shell
notebook:~/git/edu/ucsschool-kelvin-rest-api$ ./autoupdate-kelvin-container 10.201.2.135
[helper keeps running]
```

Now you can edit the code easily on your notebook and the script `autoupdate-kelvin-container` automatically copies the new code into the container:

``` shell
notebook# ssh root@10.201.2.135
root@uasvm# univention-app configure ucsschool-kelvin-rest-api
root@uasvm# univention-app shell ucsschool-kelvin-rest-api
container# cd /kelvin/kelvin-api/
container# ucr set ucsschool/kelvin/log_level=DEBUG
container# pkill -HUP -f "gunicorn: master \[ucsschool.kelvin.main:app\]"
container# pytest-3 -lvvs tests/test_route_user.py -k "test_create and not udm" 2>&1 | tee test.log
container#
```

## Installation of python packages

It is useful to have all packages installed during development, so that the IDE can autocomplete and lint correctly.
Please be aware that python-ldap is a dependency of univention-lib-slim. This python package requires to build some C-extensions and has
some additional requirements. Please follow the instructions provided [here](https://www.python-ldap.org/en/python-ldap-3.4.3/installing.html#installing-from-pypi)

```shell
apt-get install libsasl2-dev libldap-dev  # required for univention-directory-manager-modules-slim
python3 -m venv venv
. venv/bin/activate
pip install -U pip wheel
pip install -i https://test.pypi.org/simple/ univention-config-registry
pip install -i https://git.knut.univention.de/api/v4/projects/701/packages/pypi/simple uldap3
pip install -e univention-lib-slim/
pip install -e univention-directory-manager-modules-slim/
pip install -e ucs-school-lib/modules/
pip install -e ucs-school-import/modules/
pip install -e kelvin-api/ -r kelvin-api/requirements_all.txt
```

## Running pre-commit

The pipeline for this repository has a pre-commit job which prevents code from being merged which does not conform to the pre-commit programs and configuration.
You should run pre-commit checks before push you can use either pre-commit in a python3.11 environment or use docker. This will save you and your co-workers from having much headache.

### Without Docker

For the following steps, an installation of Python 3.11 is required.
In your cloned ucsschool-kelvin-rest-api repository, you can install `pre-commit` like this:

```
virtualenv -p 3.11 venv
. ./venv/bin/activate

pip install pre-commit
pre-commit install
```

To test if everything works fine, run pre-commit with the `-a` option:

```
pre-commit run -a
```

Other means of creating virtual enviroments for Python should of course also work.

Note: Installing and using pre-commit system-wide may work, but some developers reported problems with it.

### With Docker

```
docker run -v ".:/ucsschool-kelvin-rest-api" \
    -w "/ucsschool-kelvin-rest-api" \
    -it docker-registry.knut.univention.de/knut/pre-commit \
    /bin/bash -c "git config --global --add safe.directory /ucsschool-kelvin-rest-api && pre-commit run -a"
```
