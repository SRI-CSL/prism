#  Copyright (c) 2019-2023 SRI International.

import json
from pathlib import Path
import random
from shutil import copy
import structlog
from typing import *
import yaml

from prism.aws.params import AWSParams
from prism.cli.repo import REPO_ROOT
from prism.config.environment.aws import generate_aws_config, generate_local_config
from prism.config.environment.kubernetes import generate_k8s_config

TEST_RUN_PATH = REPO_ROOT / "aws-tests" / "runs"
ACTIVE_TEST_FILE = TEST_RUN_PATH / "current.txt"
LOGGER = structlog.getLogger("prism.aws")
cpu_limits = {
    500: "40m",
    400: "40m",
    300: "40m",
    200: "100m",
    100: "100m"
}


def main(args):
    par = AWSParams.load_args(args)

    if not args.output_path:
        args.output_path = str(TEST_RUN_PATH / "current")

    LOGGER.info(f"\nARGS= {args}\nPAR= {par}")
    if args.lightsail:
        deployment = generate_aws_config(args, par.dropbox_count, par.clients, par.pki_root_cert)
        # copy over to scenario dir:
        config_path = Path(args.output_path) / "config"
        client_jsons = list(config_path.glob("client-*.json"))
        result_dir = Path(args.scenarios[0].name).parent
        LOGGER.info(f"writing {len(client_jsons)} client config files to {result_dir}")
        for client_json in client_jsons:
            copy(client_json, result_dir)
    elif args.local:
        deployment = generate_local_config(args, par.dropbox_count, par.clients, par.pki_root_cert)
        # now write out the docker-compose-clients.yml file (leaving out any parameterized client)...
        docker_compose = {"version": '3.6', "services": {}}
        docker_compose_parameterized = {"version": '3.6', "services": {}}
        config_path = Path(args.output_path) / "config"
        for client_d in par.clients:
            name = client_d["name"]
            client_json = config_path / f'{name}.json'
            with open(client_json) as json_fp:
                client_config = json.load(json_fp)
                if name.lower() not in ['josh']:
                    docker_compose["services"].update(client_config)
                else:
                    client_config['josh']['environment']['PRISM_whiteboards'] = "${WHITEBOARDS}"
                    docker_compose_parameterized["services"].update(client_config)
        with open(Path(args.scenarios[0].name).parent / "clients-docker-compose.json", "w") as json_fp:
            json.dump(docker_compose, json_fp, ensure_ascii=True, indent=2)
            LOGGER.info(f"wrote {json_fp.name} docker-compose file")
        if len(docker_compose_parameterized["services"]):
            with open(Path(args.scenarios[0].name).parent / "clients-docker-compose-josh.json", "w") as json_fp:
                json.dump(docker_compose_parameterized, json_fp, ensure_ascii=True, indent=2)
                LOGGER.info(f"wrote {json_fp.name} docker-compose file")
    elif args.kubernetes:
        # generate_k8s_config(args, par.dropbox_count, par.wbs, par.n_clients, par.public_params, par.pki_root_cert)
        # TODO: write StatefulSet deployment .yaml files for all batches...
        reduced_wbs = par.wbs if len(par.wbs) < 20 else random.sample(par.wbs, 20)  # limit number of whiteboards!
        for b, batch_size in par.batches.items():
            yaml_str = format_deployment(
                n_clients=batch_size,
                db_count=par.dropbox_count,
                whiteboards=f"[{','.join(reduced_wbs)}]",
                public_params=repr(par.public_params)[1:-1],
                pki_root_cert=repr(par.pki_root_cert)[1:-1],
                empty_dir="{}",
                batch=b,
                cpu_limit=cpu_limits[par.n_clients] if False and par.n_clients in cpu_limits else "40m",  # TODO: remove False and
            )
            with open(Path(args.scenarios[0].name).parent / f"clients-ss-{b}-deployment.yaml", "w") as yaml_fp:
                yaml_fp.write(yaml_str)
                LOGGER.info(f"wrote {yaml_fp.name} k8s StatefulSet file")
        yaml_str = format_service(par.test_indices)
        with open(Path(args.scenarios[0].name).parent / "clients-ss-service.yaml", "w") as yaml_fp:
            yaml_fp.write(yaml_str)
            LOGGER.info(f"wrote {yaml_fp.name} k8s Service file")


def format_service(indices: List[str]) -> str:
    # indices: List[str] = ["0-2","1-2","5-99",...]
    template = """apiVersion: v1
kind: Service
metadata:
  name: prism-client-{index}
  namespace: race-ta1
spec:
  selector:
    statefulset.kubernetes.io/pod-name: prism-client-{index}
  type: NodePort # Overrides the default 'ClusterIP' Service type
  ports:
  - port: 80 # the port that this service should serve on
    targetPort: 8080
"""
    return "---\n".join([template.format(index=i) for i in indices])


def format_deployment(**kwargs) -> str:
    # n_clients: int
    # db_count: int
    # whiteboards: str = "['http://...','...',...]"
    # public_params: str
    # pki_root_cert: str
    # empty_dir: str = "{}"
    # batch: int
    # cpu_limit: str
    template = """apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: prism-client-{batch}
  namespace: race-ta1
spec:
  selector:
    matchLabels:
      app: client-ss-{batch}-app # has to match .spec.template.metadata.labels
  serviceName: "clients-headless"
  replicas: {n_clients}
  template:
    metadata:
      labels:
        app: client-ss-{batch}-app # has to match .spec.selector.matchLabels
        exp: july23
    spec:
      terminationGracePeriodSeconds: 10
      initContainers:
        - name: init-client
          image: race-ta1-docker.cse.sri.com/prism-ibe-lookup:latest
          resources:
            limits:
              cpu: "{cpu_limit}"
              # memory: "100Mi"
          command:
            - "python"
            - "lookup_ibe.py"
            - "ibe-cache.json"
            - "/mnt/conf.d/client.json"
          env:
            - name: PRISM_NAME
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
          volumeMounts:
            - name: conf
              mountPath: /mnt/conf.d
      containers:
        - name: race-prism-client
          image: race-ta1-docker.cse.sri.com/prism:latest
          resources:
            limits:
              cpu: "{cpu_limit}"
              # memory: "500Mi"          
          command:
            - "prism"
            - "client"
            - "/mnt/conf.d/client.json"
          env:
            - name: PRISM_whiteboards
              value: "{whiteboards}"
            - name: PRISM_wbs_redundancy
              value: "1"
#            - name: PRISM_name
#              valueFrom:
#                fieldRef:
#                  fieldPath: metadata.name
#            - name: PRISM_public_params
#              value: "{public_params}"
            - name: PRISM_pki_root_cert
              value: "{pki_root_cert}"
            - name: PRISM_client_rest_api
              value: "true"
            - name: PRISM_debug
              value: "true"
            - name: PRISM_dynamic_links
              value: "false"
            - name: PRISM_dropbox_count
              value: "{db_count}"
            - name: PRISM_dropbox_poll_with_duration
              value: "false"
            - name: PRISM_dropbox_send_redundancy
              value: "2"
            - name: PRISM_poll_timing_ms
              value: "120000"
            - name: PRISM_onion_layers
              value: "3"
            - name: PRISM_is_client
              value: "true"
          ports:
            - containerPort: 8080
          volumeMounts:
            - name: conf
              mountPath: /mnt/conf.d
      volumes:
        - name: conf
          emptyDir: {empty_dir}
      imagePullSecrets:
        - name: artifactory-secret
---
# This NetworkPolicy is like a firewall rule that allows things outside your namespace to contact your pods. "Your pods"
# are matched according to the label selector "app: my-app".
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: prism-client-{batch}-policy
  namespace: race-ta1
spec:
  podSelector:
    matchLabels:
      app: client-ss-{batch}-app
  ingress:
    - ports:
        - port: 8080   # the port on the pod - not the ingress or service!
          protocol: TCP
"""
    return template.format(**kwargs)
