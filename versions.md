# PRISM Versioning


## Single-Source of Truth `VERSION`

We will only maintain a single-source of truth file `VERSION` at the top-level to be
used for all components built out as Docker images.  This file contains a
string (usually numeric form like 1.2.3) and will be used when tagging
Docker images, copying the information inside the deployment (for access from
source code where needed; e.g., see `whiteboard/` which shows this on the
web page), and also when using git tagging to create and push releases using
CI pipelines.

We assume that each PRISM component follows this quasi standard of Dockerfile
locations: `<component>/docker/Dockerfile`


### Tagging of Docker images

First, we will fill the bash script variable `${VERSION}` with the contents of
the single-source file, e.g., using `VERSION=$( cat VERSION )` at the top-level.

Let us assume that `${IMAGE}` contains the desired Docker image name of the
component.  Then we tag

```
$ cd <component>
$ docker build -t ${IMAGE} -f docker/Dockerfile <other options> .
$ docker tag ${IMAGE} race-ta1-docker.cse.sri.com/${IMAGE}:${VERSION}
```


### Build Metadata in Image

When building a docker image, we will use these steps (in our script).

```
$ cd <component>
$ docker build -t ${IMAGE} -f docker/Dockerfile \
  --build-arg VERSION=${VERSION} \
  --build-arg GIT_COMMIT=$(git rev-parse --short HEAD) \
  --build-arg GIT_BRANCH=$(git rev-parse --abbrev-ref HEAD) .
```


## Deploying with CI and manually

The preferred way of bumping version numbers and deploying to Artifactory
is using the CI pipeline after pushing a (correctly named) git tag like so:

### Releasing with CI

Make sure that you have a clean working version (i.e., nothing uncommitted) and
that the `VERSION` file contains the current version to be used.  Then:

```
$ git status  # make sure your working copy is clean
On branch <branch>
nothing to commit, working tree clean
$ cat VERSION  # make sure to have updated the version string (see note below!)
1.2.3
$ VERSION=`cat VERSION`; git tag -am "release v${VERSION}" $VERSION
$ git push origin <branch>  # this will set the CI deployment process in motion
```

The current CI configuration (see also `.gitlab-ci.yml`) will use any git tag
to build out the Docker images and pushing them to Artifactory.  You can check
CI progress at [https://gitlab.sri.com/race-ta1/prism-dev/pipelines](https://gitlab.sri.com/race-ta1/prism-dev/pipelines)

Note: Keep in mind that Artifactory does not replace older images with the same
version number/tag; if you want a fresh image there make sure to increment
(or change) the version number to something that does not yet exist in
[Artifactory](https://artifactory.sri.com)!

#### Git Tag Management

Note: If you do not change the version number from a prior tag then git
will complain:

```
$ git tag -am "release v1.2.3" 1.2.3
fatal: tag '1.2.3' already exists
```

Should you need to remove old tags (after testing etc.) you can use these commands:

```
$ git tag
[list of tags]
$ git push --delete origin <tagname>  # remotely
$ git tag --delete <tagname>
```

### Deploying manually

To deploy a current version manually, use `./build-all.sh -d`.


## Further Reading

The following requires git tagging for meaningful descriptions:

from: https://stackoverflow.com/a/57683700/3816489
```
import subprocess, os
VERSION = subprocess.check_output(["git", "describe", "--always"], cwd=os.path.dirname(__file__)).strip().decode()
print(f'Git version: {VERSION}')
```

* https://stackoverflow.com/questions/55416379/how-to-avoid-keeping-version-number-in-source-code
* https://stackoverflow.com/questions/5581722/how-can-i-rewrite-python-version-with-git

* https://packaging.python.org/guides/single-sourcing-package-version/#single-sourcing-the-version
* https://pypi.org/project/bump2version/

## Moving to Python 3.8

Once we are moving to Python 3.8, we are looking at some improvements:

* https://stackoverflow.com/a/58549477/3816489
  Using something like this for accessing meta data from install/deploy time:
  `from importlib-metadata import version`

* Improved string representation of Enum's will simplify code
