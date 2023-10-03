#!/usr/bin/env bash
#
# Copyright (c) 2019-2023 SRI International.
#

set -euo pipefail

pushd $REPO_ROOT/client/cli &> /dev/null

rm -rf dev-lib

$REPO_ROOT/gradlew assembleDist

pushd build/distributions &> /dev/null
unzip -o cli.zip &> /dev/null
popd &> /dev/null

cp -r build/distributions/cli/lib/ dev-lib

popd &> /dev/null
