#!/usr/bin/env python3

#  Copyright (c) 2019-2023 SRI International.

import argparse
from typing import Dict, List, Optional, Union
import os
import shutil
import sys
from pathlib import Path
import subprocess

from .command import CLICommand
from .repo import VERSION, REPO_ROOT

DEFAULT_REPO = 'race-ta1-docker.cse.sri.com'


class BuildTarget:
    def __init__(self, name: str, dockerfile=None,
                 context_path: Optional[str] = None, parent: Optional[str] = None):
        self.name = name
        self.image_name = name
        if dockerfile:
            self.dockerfile = REPO_ROOT / dockerfile
        else:
            self.dockerfile = REPO_ROOT / "docker" / name / "Dockerfile"
        if context_path:
            self.context = REPO_ROOT / Path(context_path)
        else:
            self.context = REPO_ROOT
        self.dockerfile_dir = self.dockerfile.parent
        self.parent = parent
        self.repo = DEFAULT_REPO

        # Files for local-mode builds. A local mode build builds the target locally,
        # and merely copies files into the docker container. This can mean
        # faster builds, but not necessarily repeatable outside the dev
        # environment. Specifically, this is meant to speed up Gradle builds
        # for the client, because Gradle has an enormous startup cost if it
        # can't use a persistent daemon.
        self.dockerfile_local = self.dockerfile_dir / "Dockerfile.local"
        self.local_build_script = self.dockerfile_dir / "build_local.sh"
        self.local_clean_script = self.dockerfile_dir / "clean_local.sh"

    def __repr__(self):
        return self.name

    def exists(self) -> bool:
        return self.dockerfile.exists()

    def tag(self, repo: Optional[str], version: str) -> str:
        if repo:
            return f"{repo}/{self.image_name}:{version}"
        else:
            return f"{self.image_name}:{version}"

    def local_build_available(self, args) -> bool:
        return not args.no_local and \
            self.dockerfile_local.exists() and \
            self.local_build_script.exists()

    def local_build(self, env) -> bool:
        return run_cmd([self.local_build_script], cwd=self.context, env=env)

    def local_clean(self, env) -> bool:
        if self.local_clean_script.exists():
            return run_cmd([self.local_clean_script], cwd=self.context, env=env)

    def build(self, args, env: Dict[str, str]) -> bool:
        dockerfile = self.dockerfile
        repo = args.repo or self.repo

        if self.local_build_available(args):
            dockerfile = self.dockerfile_local
            result = self.local_build(env)

            if not result:
                return False

        cmd = ['docker', 'build', '-t', self.image_name, '-f', dockerfile]

        if args.no_cache:
            cmd.append('--no-cache')

        for k, v in env.items():
            cmd.extend(["--build-arg", f"{k}={v}"])

        cmd.append(self.context)

        result = run_cmd(cmd, cwd=self.context, env={"DOCKER_BUILDKIT": "1"})

        if self.local_build_available(args):
            self.local_clean(env)

        if not result:
            return False

        run_cmd(['docker', 'tag', self.image_name,
                 self.tag(repo, env['VERSION'])])
        run_cmd(['docker', 'tag', self.image_name,
                 self.tag(repo, 'latest')])
        run_cmd(['docker', 'tag', self.image_name,
                 self.tag(None, 'dev')])

        return True

    def deploy(self, args, env):
        repo = args.repo or self.repo
        print(f"Deploying {self.tag(repo, env['VERSION'])}")
        run_cmd(['docker', 'push', self.tag(repo, env['VERSION'])])
        run_cmd(['docker', 'push', self.tag(repo, 'latest')])


# When adding new BuildTargets, make sure to place them *after* any parent images in the list.
# The dependency resolver assumes that images are listed in order of dependencies.
TARGETS = [
    BuildTarget('prism-base'),
    BuildTarget('prism-bebo', parent='prism-base'),
    BuildTarget('prism', parent='prism-base'),
    # BuildTarget('prism-client', parent='prism'),
]


def run_cmd(cmd: List[Union[str, Path]], cwd=REPO_ROOT, capture=False, env=None):
    if env:
        full_env = os.environ.copy()
        full_env.update(env)
        env = full_env

    print('Running: ' + ' '.join(str(w) for w in cmd))
    result = subprocess.run(cmd, cwd=cwd, capture_output=capture, env=env)
    if capture:
        return result.stdout.decode('utf-8').strip()
    else:
        return result.returncode == 0


def build_environment(args) -> Dict[str, str]:
    env = {
        "REPO_ROOT": str(REPO_ROOT),
        "VERSION": VERSION,
        "GIT_COMMIT": run_cmd(['git', 'rev-parse', '--verify', 'HEAD'],
                              capture=True),
        "GIT_BRANCH": run_cmd(['git', 'symbolic-ref', '--short', '-q', 'HEAD'],
                              capture=True),
    }

    if args.repo:
        env['SRI_CONTAINER_REGISTRY'] = args.repo

    return env


def resolve_dependencies(args) -> List[BuildTarget]:
    target_map = {target.name: target for target in TARGETS}

    explicit_targets = [target.name for target in TARGETS
                        if (not args.targets or target.name in args.targets)]

    if not args.skip_deps:
        explicit_targets.reverse()

        for target_name in explicit_targets:
            target = target_map[target_name]
            if target.parent and target.parent not in explicit_targets:
                explicit_targets.append(target.parent)

        explicit_targets.reverse()

    return [target_map[name] for name in explicit_targets]


def check_build_dependencies() -> bool:
    if not shutil.which("unzip"):
        print("Unzip is required for building the client.")
        return False
    if not shutil.which("javac"):
        print("Java is required for building the client.")
        return False
    if not shutil.which("docker"):
        print("Docker is required for builds.")
        return False
    return True


def build_images(args):
    if not check_build_dependencies():
        sys.exit(1)

    env = build_environment(args)

    targets = resolve_dependencies(args)

    if args.list:
        for target in targets:
            print(target)
        return

    print(f"Building PRISM Version {env['VERSION']}\n"
          f"Branch: {env['GIT_BRANCH']}\n"
          f"Commit: {env['GIT_COMMIT']}")

    for target in targets:
        if not target.exists():
            print(f"Warning: Skipping target {target.name} "
                  f"because {target.dockerfile} does not exist.")
            continue

        if not target.build(args, env):
            print(f"Error building {target.name}:{env['VERSION']}")
            sys.exit(1)

    for target in targets:
        if args.deploy:
            target.deploy(args, env)


def build_parser(parser):
    parser.add_argument('-c', '--no-cache', action='store_true', dest='no_cache',
                        help='Add --no-cache to Docker build command.')
    parser.add_argument('-d', '--deploy', action='store_true',
                        help='Deploy built images to Artifactory.')
    parser.add_argument('--skip-deps', action='store_true',
                        help='Skip building dependency images when debugging.')
    parser.add_argument('--no-local', action='store_true',
                        help='Do not perform build steps outside of Docker.')
    parser.add_argument('--list', action='store_true',
                        help='List build targets and quit.')
    parser.add_argument('--repo',
                        help=f"Specify a non-default docker repository to deploy (Default: {DEFAULT_REPO})",
                        default=None)
    parser.add_argument('targets', metavar='TARGETS', nargs='*', default=None,
                        help='Targets to build.')


def empty_args():
    p = argparse.ArgumentParser("test")
    build_parser(p)
    return p.parse_args([])


cli_command = CLICommand("build", build_parser, build_images, help="Build PRISM Docker images.")
