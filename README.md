# UCS@school Kelvin REST API

This repository contains the code for the UCS@school Kelvin REST API

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
- After each commit and pipeline run you can install the app with the new docker image

<!-- This will probably not work yet, since the registry needs authentication!
The release flow will be the following (This was not tested yet):
- When all features for the release are merged in the main branch, create a tag for the new release.
- Set the resulting docker image as the image in the app version to release
- Publish the app as usual. The AppCenter should automatically copy the image from the gitlab registry to our public
  docker registry
-->

### Caveats

The gitlab docker registry uses our internal rootCA. This has to be imported in the UCS VM before installing the app
and can be done like this:
```
wget --no-check-certificate http://nissedal.knut.univention.de/ucs-root-ca.crt -P /usr/local/share/ca-certificates/
update-ca-certificates
```

The gitlab docker registry requires authentication, which has to be done before installing the app:
```
$TOKEN_NAME=your-token-name
$TOKEN_SECRET=s3cRet
docker login -u $TOKEN_NAME -p $TOKEN_SECRET gitregistry.knut.univention.de
```

You can either use a personal access token or a project access token, which has at least the registry_read scope.
A project access token can be found in [univention/components/ucsschool-kelvin-rest-api#1](https://git.knut.univention.de/univention/components/ucsschool-kelvin-rest-api/-/issues/1).

To install the kelvin App with the new branch docker image you can temporarily 
change the App's docker image setting:

```
univention-install univention-appcenter-dev
univention-app dev-set \
    4.4/ucsschool-kelvin-rest-api=1.5.4 \
    "DockerImage"="gitregistry.knut.univention.de/univention/components/ucsschool-kelvin-rest-api:branch-cgarcia-6-workgroup-management-in-kelvin-api"
univention-app install \
    4.4/ucsschool-kelvin-rest-api=1.5.4
```

# Release

## Update the docker image

- In the provider portal set the docker image to `gitregistry.knut.univention.de/univention/components/ucsschool-kelvin-rest-api:branch-main`. Copy the name of the docker image and save it for later.
- Run the [docker-update](https://univention-dist-jenkins.k8s.knut.univention.de/job/UCS-5.0/job/Apps/job/ucsschool-kelvin-rest-api/job/App%20Autotest%20MultiEnv/SambaVersion=s4,Systemrolle=docker-update/) job of the `ucsschool-kelvin-rest-api` app test. It will pull the docker image and set the needed tags for you automatically.
- Reset the docker image to the one before (e.g. `docker.software-univention.de/ucsschool-kelvin-rest-api:1.5.5`)

## Publish packages from TestAppCenter

The correct version string, for example `ucsschool-kelvin-rest-api_2022050407282` can be found here
https://appcenter-test.software-univention.de/meta-inf/4.4/ucsschool-kelvin-rest-api/ by navigating to the last (published) version.

This code should be run **on dimma or omar**:
```shell
cd /mnt/omar/vmwares/mirror/appcenter
./copy_from_appcenter.test.sh 4.4 ucsschool-kelvin-rest-api_20220504072827  # copies the given version to public app center on local mirror!
sudo update_mirror.sh -v appcenter  # syncs the local mirror to the public download server!
```

## Publish documentation

The documentation is build automatically when changes are pushed in `docs/**/**`.
The job to copy the documentation `docs-production` to the repository `docs.univention.de` must be triggered manually.
**Warning**: Currently the job can be started regardless of any changes. This will be fixed with https://git.knut.univention.de/univention/components/ucsschool-kelvin-rest-api/-/issues/15

The commit in `docs.univention.de` will also trigger a pipeline, which will do the actual release.
The pipeline also needs to be triggered manually. 



