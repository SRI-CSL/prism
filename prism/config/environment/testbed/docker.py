#  Copyright (c) 2019-2023 SRI International.

import copy
from pathlib import Path

from prism.config.node import Bebo, Client, Server, Node

JAEGER_UDP_PORT = 6831
JAEGER_UI_PORT = 16686

JAEGER_HOST = "testbed_jaeger"
IMAGE_PREFIX = "race-ta1-docker.cse.sri.com"


def docker_image(name):
    return f"{IMAGE_PREFIX}/{name}"


# A placeholder for template fields that need to be filled in.
FILL_ME = '...'

JAEGER_CONFIG = {
    'image': 'jaegertracing/all-in-one:latest',
    "container_name": JAEGER_HOST,
    'ports': [
        f"{JAEGER_UI_PORT}:{JAEGER_UI_PORT}",
        f"{JAEGER_UDP_PORT}:{JAEGER_UDP_PORT}/udp"
    ]
}

BEBO_TEMPLATE = {
    'image': docker_image('prism-bebo'),
    'container_name': FILL_ME,
    'environment': {
        'NAME': FILL_ME,
    },
    'ports': [FILL_ME]
}

PRISM_SERVER_TEMPLATE = {
    'image': docker_image('prism'),
    'container_name': FILL_ME,
    'depends_on': [JAEGER_HOST],
}

PRISM_CLIENT_TEMPLATE = {
    'image': docker_image('prism'),
    'container_name': FILL_ME,
    'depends_on': [JAEGER_HOST],
    'ports': FILL_ME,
    'environment': {},
}

JAEGER_COMMON_ENV = {
    'PRISM_JAEGER_AGENT_HOST': JAEGER_HOST,
    # 'PRISM_JAEGER_AGENT_PORT': JAEGER_UDP_PORT,
    # 'JAEGER_SAMPLER_TYPE': 'const',
    # 'JAEGER_SAMPLER_PARAM': '1'
}


def flatten_env(cfg):
    """Flattens the environment variables in a config,
    changing 'environment' from a map to a list
    Note that if the value is empty, we have to omit the '='
    in order for actual env variables to override."""
    def null_or_empty(v):
        return (v is None) or (v == "")

    def flatten_item(k, v):
        if null_or_empty(v):
            return str(k)
        else:
            return f'{k}={v}'

    cfg['environment'] = [flatten_item(k, v)
                          for k, v in sorted(cfg['environment'].items())]

    return cfg


def node_service(node: Node, template: dict, base_dir: Path, service_params: dict = None, environment: dict = None):
    service = copy.deepcopy(template)
    service["container_name"] = node.name

    if service_params:
        service = {
            **service,
            **service_params,
            "volumes": [
                str(base_dir.absolute() / "logs" / node.name) + ":/log",
                str(base_dir.absolute() / "config") + ":/config"
            ]
        }

    if not environment:
        environment = {}

    service["environment"] = {
        **service.get("environment", {}),
        **JAEGER_COMMON_ENV,
        "PRISM_JAEGER_SERVICE_NAME": node.name,
        **environment
    }

    return flatten_env(service)


def bebo_service(bebo: Bebo, base_dir: Path):
    params = {
        # "command": ["python", "-m", "bebo.server", "-L", "/log/bebo.log"],
        "ports": [f"{bebo.outside_port}:{bebo.BEBO_PORT}"],
    }

    env = {
        'NAME': bebo.name,
    }
    if bebo.neighbors:
        env['NEIGHBORS'] = ','.join(node.name for node in bebo.neighbors)

    return node_service(node=bebo, template=BEBO_TEMPLATE, base_dir=base_dir, service_params=params, environment=env)


def client_service(client: Client, base_dir: Path, test_range):
    configs = ["/config/prism.json", "/config/client.json", f"/config/{client.name}.json"]
    env = {
        "CONTACTS": ",".join(node.name for node in test_range.clients if node != client)
    }

    params = {
        "command": ["prism", "client", *configs],
        "ports": [f"{client.outside_port}:8080"],
    }
    return node_service(node=client, template=PRISM_CLIENT_TEMPLATE, base_dir=base_dir, service_params=params, environment=env)


def server_service(server: Server, base_dir: Path):
    configs = ["/config/prism.json", "/config/server.json", f"/config/{server.name}.json"]
    params = {
        "command": ["prism", "server", *configs]
    }
    return node_service(node=server, template=PRISM_SERVER_TEMPLATE, base_dir=base_dir, service_params=params)


def generate_docker_compose(test_range, base_dir: Path):
    services = {
        JAEGER_HOST: JAEGER_CONFIG,
    }

    for bebo in test_range.bebos:
        services[bebo.name] = bebo_service(bebo, base_dir)
    for client in test_range.clients:
        services[client.name] = client_service(client, base_dir, test_range)
    for server in test_range.servers:
        services[server.name] = server_service(server, base_dir)

    compose = {
        'version': "3.6",
        'services': services,
    }

    return compose
