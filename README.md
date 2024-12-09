# UCS@school Kelvin REST API

This repository contains the code for the UCS@school Kelvin REST API application.
The application provides HTTP endpoints to create and manage UCS@school domain objects like school users, school classes, schools (OUs) and computer rooms.
See the [public documentation](https://docs.software-univention.de/ucsschool-kelvin-rest-api/) for its usage and configuration.

## App release

### Checklist

_You may copy this to a gitlab release issue_

- [ ] Check contents of [kelvin-api/changelog.rst](./kelvin-api/changelog.rst)
- [ ] Check contents of [appcenter/README_UPDATE_EN](./appcenter/README_UPDATE_EN)
- [ ] Update version in [kelvin-api/VERSION.txt](./kelvin-api/VERSION.txt)
- [ ] Verify the changes have been uploaded to the test appcenter
- [ ] Transfer/Tag the latest docker image [with this jenkins job](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCS-5.0/job/Apps/job/ucsschool-kelvin-rest-api/job/App%20Autotest%20MultiEnv/)
- [ ] Kelvin [Jenkins tests](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API%20(branch%20main)/) OK
- [ ] Kelvin client [Jenkins test](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/Kelvin-client-daily) OK
- [ ] Jenkins in [test appcenter](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API)
- [ ] API still works (smoke test)
- [ ] Tag commit in gitlab
- [ ] Release application
- [ ] Release documentation (changelog number)
- [ ] Release QA (upgrade and smoke test)
- [ ] Create new application version in provider portal
- [ ] Close issues & bugs
- [ ] Release mail & chat announcement

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

#### Update the docker image in Test AppCenter

- In the provider portal under the configuration section, set the docker image to `gitregistry.knut.univention.de/univention/components/ucsschool-kelvin-rest-api:latest`.
- Run the [docker-update](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCS-5.0/job/Apps/job/ucsschool-kelvin-rest-api/job/App%20Autotest%20MultiEnv/SambaVersion=s4,Systemrolle=docker-update/) job of the `ucsschool-kelvin-rest-api` app test. The job will pull the current docker image, tag it to `docker.software-univention.de/$APP_ID:$APP_VERSION`, upload the image and finally change the apps ini to use `docker.software-univention.de/$APP_ID:$APP_VERSION` as docker image.

#### Publish packages from Test AppCenter to Production AppCenter


This code should be run **on omar**:
```shell
cd /mnt/omar/vmwares/mirror/appcenter
./copy_from_appcenter.test.sh 4.4
./copy_from_appcenter.test.sh 4.4 "$COMPONENT_ID"  # copies the given version to public app center on local mirror! Exchange the component id!
sudo update_mirror.sh -v appcenter  # syncs the local mirror to the public download server!
```

You can verify that the app has been synced to the public download server by looking at the following URL,
exchange `COMPONENT_ID` with the target component id.

```text
https://appcenter.software-univention.de/univention-repository/5.0/maintained/component/COMPONENT_ID/
```

#### Release Mail

```
Hello,

the UCS@school Kelvin REST API version <version> has been released.

For changes, see https://docs.software-univention.de/ucsschool-kelvin-rest-api/changelog.html

Best regards

UCS@school Team
```

#### Publish documentation

The documentation is build automatically when changes are pushed in `doc/docs/**/*`.
The job to copy the documentation `docs-production` to the repository `docs.univention.de` must be triggered manually.

The pipeline rule definition has two conditions in **one** rule. The
*docs-production* is only created when the files below `doc/docs/**/*` changed
**AND** when the branch is the default branch. This means, you need to develop
your documentation changes in a feature branch. And after the merge to the
default branch, the job starts, because it is in the default branch and
documentation files were changed. To run the job, you need to start it manually.

The commit in `docs.univention.de` will also trigger a pipeline, which will do the actual release.

Refer to the wiki page https://hutten.knut.univention.de/mediawiki/index.php/Docs/Deployment
for more information regarding the documentation pipeline.

#### Create a new unpublished version in the appcenter

In the [provider portal](https://selfservice.software-univention.de/univention/management/#module=appcenter-selfservice) overview, right click the "UCS@school Kelvin REST API" app and choose "New app version".
Update the "Target app version" to the next release number and hit "Create".
Set the "Docker Image" in the configuration tab in the SelfService Center should to `gitregistry.knut.univention.de/univention/components/ucsschool-kelvin-rest-api:latest`.

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

## Use custom images in Jenkins jobs

The Jenkins job [kelvin API tests](https://jenkins2022.knut.univention.de/job/UCSschool-5.0/job/kelvin%20API%20(branch%20main)/) and [kelvin API tests](https://jenkins2022.knut.univention.de/job/UCSschool-5.0/view/Daily%20Tests/job/kelvin%20API/) can be configured to use a custom image.
In the 'Build with parameters' page, insert your image name into the `UCS_ENV_KELVIN_IMAGE` configuration variable.
One source for images is the pipeline `build_docker_image`, which is run for a feature branch if it changed sufficiently.
To find the image name, scroll to the bottom of the job log and look for `Pushing image to ...`.


## Use custom images on test vm

For this, you need to activate the Test Appcenter.

To install the Kelvin application with the new branch docker image you can temporarily
change the App's docker image setting:

```
image="gitregistry.knut.univention.de/univention/components/ucsschool-kelvin-rest-api:branch-handleuldap3binderror"

univention-install univention-appcenter-dev
univention-app dev-set \
    4.4/ucsschool-kelvin-rest-api=1.5.4 \
    "DockerImage"="DockerImage=$image"
univention-app install \
    4.4/ucsschool-kelvin-rest-api=1.5.4
```
or you can update an existing app by running:

```
docker pull "$image"
univention-app dev-set ucsschool-kelvin-rest-api "DockerImage=$image"
univention-app reinitialize ucsschool-kelvin-rest-api
```


# Development Setup

This section gathers information for development setup.
Everything here is optional.

## Installation of python packages

It is useful to have all packages installed during development, so that the IDE can autocomplete and lint correctly.
Please be aware that python-ldap is a dependency of univention-lib-slim. This python package requires to build some C-extensions and has
some additional requirements. Please follow the instructions provided [here](https://www.python-ldap.org/en/python-ldap-3.4.3/installing.html#installing-from-pypi)

```shell
python3 -m venv venv
. venv/bin/activate
pip install -U pip wheel
pip install -i https://test.pypi.org/simple/ univention-config-registry
pip install -i https://git.knut.univention.de/api/v4/projects/701/packages/pypi/simple uldap3
pip install -e univention-lib-slim/
pip install -e univention-directory-manager-modules-slim/
pip install -e ucs-school-lib/modules/
pip install -e ucs-school-import/modules/
pip install -e kelvin-api/ -r kelvin-api/requirements.txt -r kelvin-api/requirements_dev.txt -r kelvin-api/requirements_test.txt
```

## Running pre-commit

The pipeline for this repository has a pre-commit job which prevents code from being merged which does not conform to the pre-commit programs and configuration.
You should run pre-commit checks before push you can use either pre-commit in a python3.11 environment or use docker. This will save you and your co-workers from having much headache.

### Without Docker

Download [OPA](https://www.openpolicyagent.org/docs/latest/#running-opa) and put the `opa` executable in a directory which is listed in your $PATH.
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
    -it docker-registry.knut.univention.de/knut/pre-commit-opa-python3.11 \
    /bin/bash -c "git config --global --add safe.directory /ucsschool-kelvin-rest-api && pre-commit run -a"
```

