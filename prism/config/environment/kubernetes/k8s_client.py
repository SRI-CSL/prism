#  Copyright (c) 2019-2023 SRI International.

from dataclasses import dataclass, field

from prism.config.config import Configuration
from prism.config.node.client import Client


def format_deployment(**kwargs) -> str:
    # name=alice, bob
    # whiteboards="['...']"
    # db_count: int
    # private_key, public_params, ibe_secret,...
    template = """apiVersion: v1
kind: Service
metadata:
  name: client-{name}-service
  namespace: race-ta1
spec:
  selector:
    app: client-{name}-app
  ports:
  - port: 80 # the port that this service should serve on
    # the container on each pod to connect to, can be a name
    # (e.g. 'www') or a number (e.g. 80)
    targetPort: 8080
    protocol: TCP

---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: client-{name}
  namespace: race-ta1
spec:
  selector:
    matchLabels:
      app: client-{name}-app
  replicas: 1
  template:
    metadata:
      labels:
        app: client-{name}-app
        experiment: client-k8s
    spec:  # this is the **Pod** spec
      containers:
        - name: prism-client
          image: race-ta1-docker.cse.sri.com/prism
          command: [ "prism", "client" ]
          env:
            - name: PRISM_whiteboards
              value: "{whiteboards}"
            - name: PRISM_wbs_redundancy
              value: "1"
            - name: PRISM_name
              value: "{name}"
            - name: PRISM_private_key
              value: "{private_key}"
            - name: PRISM_public_params
              value: "{public_params}"
            - name: PRISM_system_secret
              value: "{ibe_secret}"
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
            - name: PRISM_poll_timing_ms
              value: "120000"
            - name: PRISM_onion_layers
              value: "3"
            - name: PRISM_is_client
              value: "true"
          ports:
            - containerPort: 8080
      imagePullSecrets:
        - name: artifactory-secret

---
# This NetworkPolicy is like a firewall rule that allows things outside your namespace to contact your pods. "Your pods"
# are matched according to the label selector "app: my-app".
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: prism-{name}-policy
  namespace: race-ta1
spec:
  podSelector:
    matchLabels:
      app: client-{name}-app
  ingress:
    - ports:
      - port: 8080   # the port on the pod - not the ingress or service!
        protocol: TCP
  egress:
    - ports:
      - port: 4000
        protocol: TCP
    - ipBlock:
      - cidr: "44.226.22.29/8"
"""
    return template.format(**kwargs)


@dataclass(eq=True, unsafe_hash=True)
class KubernetesClientSet(Client):
    wbs: str = field(default="[]")
    db_count: int = field(default=1)
    yaml_str: str = field(default="")

    def config(self, config: Configuration) -> dict:
        client_config = super().config(config)
        self.yaml_str = format_deployment(
            name=self.name,
            whiteboards=self.wbs,
            private_key="",  #f"'{client_config.get('private_key')}'",
            public_params=self.ibe.public_params.replace('\\', '\\\\'),
            ibe_secret=self.ibe.ibe_secrets[0],
            db_count=self.db_count,
        )
        return {
            # "serviceName": self.name,
            # "containers": {
            #     f"container-{self.name}": {
            #         "image": f":{self.name}.prism.latest",
            #         "command": [
            #             "prism", "client"
            #         ],
            #         "environment": {
            #             "PRISM_whiteboards": self.wbs,
            #             "PRISM_wbs_redundancy": "1",
            #             "PRISM_name": self.name,
            #             "PRISM_private_key": f"'{client_config.get('private_key')}'",
            #             "PRISM_public_params": self.ibe.public_params,
            #             "PRISM_system_secret": self.ibe.ibe_secret,
            #             "PRISM_client_rest_api": "true",
            #             "PRISM_debug": "true",
            #             "PRISM_dynamic_links": "false",
            #             "PRISM_dropbox_count": f"{self.db_count}",
            #             "PRISM_dropbox_poll_with_duration": "false",
            #             "PRISM_poll_timing_ms": "120000",
            #             "PRISM_onion_layers": "3",
            #             "PRISM_is_client": "true"
            #         },
            #         "ports": {
            #             "8080": "HTTP"
            #         }
            #     }
            # },
            # "publicEndpoint": {
            #     "containerName": f"container-{self.name}",
            #     "containerPort": 8080
            # },
        }
