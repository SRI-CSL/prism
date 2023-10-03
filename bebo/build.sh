#!/usr/bin/env bash
#
# Copyright (c) 2019-2023 SRI International.
#

# building and tagging Docker images:
#  $ ./build.sh -c  # => builds afresh, not using any caches
#  $ ./build.sh -d  # => deploys image after building

DO_DEPLOY=
NO_CACHE=

# 1) get options and arguments
while getopts "cdh" opt; do
  case ${opt} in
    h )
      echo "Usage: $0 [options]"
      echo "  where"
      echo -e "    -h  Display this help message"
      echo -e "    -c  Add --no-cache to Docker build command"
      echo -e "    -d  Also deploy the image to Artifactory after building"
      exit 0
      ;;
    d )
      DO_DEPLOY=1
      ;;
    c)
      NO_CACHE="--no-cache"
      ;;
    \? )
      echo "Invalid Option: -$OPTARG" 1>&2
      exit 1
      ;;
  esac
done

# 2) get VERSION number and set image name
VERSION=`cat ../VERSION`
GIT_COMMIT=`git rev-parse --short HEAD`
GIT_BRANCH=`git rev-parse --abbrev-ref HEAD`
IMAGE=prism-bebo

# 3) build image
echo " -- building image ${IMAGE}:${VERSION}:"
docker build -t ${IMAGE} -f docker/Dockerfile ${NO_CACHE} \
   --build-arg=VERSION=${VERSION} \
   --build-arg=GIT_COMMIT=${GIT_COMMIT} \
   --build-arg=GIT_BRANCH=${GIT_BRANCH} .

docker tag ${IMAGE} race-ta1-docker.cse.sri.com/${IMAGE}:${VERSION}
docker tag ${IMAGE} race-ta1-docker.cse.sri.com/${IMAGE}:latest

# 4) [optional] deploy image
if [[ ${DO_DEPLOY} ]]; then
  echo " -- deploying image ${IMAGE}:${VERSION}:"

  docker push race-ta1-docker.cse.sri.com/${IMAGE}:${VERSION}
  docker push race-ta1-docker.cse.sri.com/${IMAGE}:latest
fi
