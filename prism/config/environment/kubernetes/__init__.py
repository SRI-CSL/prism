#  Copyright (c) 2019-2023 SRI International.

from pathlib import Path
import structlog
import sys
from typing import List

from prism.config.config import Configuration
from prism.config.error import ConfigError
from prism.config.generate import run
from prism.config.ibe import GeneratedIBE
from .deployment import KubernetesDeployment
from .k8s_range import KubernetesRange

LOGGER = structlog.getLogger("prism.config.environment.kubernetes")


def generate_k8s_config(args, db_count: int, wbs: List[str], n_clients: int, pps: str, root_cert: str):
    LOGGER.info(f"generate k8s config with db_count={db_count} and {n_clients} clients, whiteboards={wbs}")
    # test_clients = [f"prism-client-{index}" for index in range(1, n_clients + 1)]

    # TODO:



    deploy = KubernetesDeployment(
        k8s_range=KubernetesRange(db_count, f"[{','.join(wbs)}]"),
        output_path=Path(args.output_path)
    )

    try:
        deploy.output_path.mkdir(parents=True, exist_ok=True)

        config = Configuration.load_args(args)
        # Apply AWS-specific config settings
        config.bootstrapping = False
        # config.prism_client["dynamic_links"] = False

        ibe = GeneratedIBE(config.ibe_shards, config.ibe_dir, config.ibe_level)
        run(deploy, ibe, config)
        ibe.dump(deploy.output_path / "generated_IBE.json")
        LOGGER.info(f"written Generated IBE to {deploy.output_path / 'generated_IBE.json'}")
        return deploy
    except ConfigError as e:
        print(f"AWS Config generation failed: {e}")
        sys.exit(1)

def format_ss_yaml():

    """apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: prism-client
  namespace: race-ta1
spec:
  selector:
    matchLabels:
      app: client-ss-app # has to match .spec.template.metadata.labels
  serviceName: "clients-headless"
  replicas: TODO
  template:
    metadata:
      labels:
        app: client-ss-app # has to match .spec.selector.matchLabels
    spec:
      terminationGracePeriodSeconds: 10
      initContainers:
        - name: init-client
          image: race-ta1-docker.cse.sri.com/prism-ibe-lookup:latest
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
          command:
            - "prism"
            - "client"
            - "/mnt/conf.d/client.json"
          env:
            - name: PRISM_whiteboards
              value: TODO "['http://44.225.11.17:4000','http://52.60.222.9:4000','http://18.185.165.154:4000','http://15.206.237.123:4000','http://54.66.161.159:4000']"
            - name: PRISM_wbs_redundancy
              value: "1"
            - name: PRISM_name
              valueFrom:
                fieldRef:
                  fieldPath: metadata.name
            - name: PRISM_public_params
              value: TODO "security 3\n[264501626081316699891602189894630962194483708348471574075521657756599682874689710047999660002617211540013281075889100583213927459984371341591466036408349463222503554732492388149379473642618485967547012798792968188752470186305924941710946819449612221980077089911818123509622823955998188606612115108681747532896602816828826661276671115022603622540607262247203892098438311483797137754253538235223483619830685915058672087117385558612452073422418878232702333190629372, 1230130776717612109553496232414352076765126700631093278402386211059515325738348523638134044315122290020475531563379635995867054290437266824806770201231622324971667768721166132656377133302016896889584436718606115623127549447724252948457335412164670959023539027934212503812638652994170495540203571075639562229772140206946778707287819557997055780836578327374965775338895456221587363766426545596078089946073290411873962840493185801030538441297750732338458196920416480]\n[1783470602763056157910858343771231902377201506610338938808404251541484542228381614594211427228218374851264920128801144755432760351922456379339032347025467109848446906454638758539840317949432943174411721594678921442364553740566254832066396300010439393397624451490207228704249648352164376759626557690352144894412523039742978122273621391974203390652312229334193324347521444758106230827909901896792360975531580281984039350649824300866205647441112713376669243185940351, 1032794573931313911073941843247208513432706741926770521925647879282607856136711127266013417979613875410163173339378813996901901416902714407571083014801942569375045409138859657126752609272141329372882118073881590782996903829767766189169625461975881005469431486333748577730488497277371428742098149244786215680230314061689416401733860655356266493217441530253092920317849615341054850620015391884772543650290383720557342567301494060567157193623876034666865221591188564]\n6dp5qcb22im1wonf1nar2dhkia4yw9xnifz16z7f090lpcifpb\ntype a\nq 1832664568807455739096375674251912748150527956510179599009422026475239611278794438372136897676251938353060243172442341244643152860477952476978454163956740326767704562726744792972411013171328220491560572532574980229063886602367477782131821637385898783039789582500723040133818551067809078159686635043519483016335915605169510190188314064783520280396265350506324651278044112077290384193513344172840598138840280236079616237211012688896765494033729873940477644269593687\nh 15827200121170668425630240888118614188052872532337599761443855160064541487776208289031393950321548098994268637182898470182675101247534618215325538958883912931412224942393668890835042886050642129543311846916234808681526273370325210911932328609125803406978782490072261389859308826005621528449984385250181963219484585796403776751194968611271476012367698255449432480890358308128098851838888\nr 115792089237316195398462578067141184797926826972809898375048162230056991588351\nexp2 256\nexp1 194\nsign1 -1\nsign0 -1\n"
            - name: PRISM_pki_root_cert
              value: TODO "-----BEGIN CERTIFICATE-----\nMIIC0TCCAbmgAwIBAgIUHVUDiNfEb9YUWamVbqj9Y0KBiTIwDQYJKoZIhvcNAQEL\nBQAwGDEWMBQGA1UEAwwNUFJJU00gUm9vdCBDQTAeFw0yMzA2MDcxMzMwMTZaFw0y\nNDA2MDYxMzMwMTZaMBgxFjAUBgNVBAMMDVBSSVNNIFJvb3QgQ0EwggEiMA0GCSqG\nSIb3DQEBAQUAA4IBDwAwggEKAoIBAQDqHYmE8E8lAJhMrUaFPxH04PCeyQAHuFpA\nKZre8VMqnVWwfKoyGj07B8896n/oXwiAAgnO7jv6ULYa+egSh/KM0in9gQ+A6/fw\nNqkcqAasvum+kT9hI7jvoVLSzt5pAtHozj/3bGFgVKrN+157zulFXgsZxeW+zMGW\noAIMSYtIWhTE5z7L129no9JbBtGfMXLfYPlX0ENyXTBjjwzimLZh5AjadH29mLAr\nb61GKewcIMoXQCJnRL5FqGMVVyINsegwT05FEY5dXrkOOkl/HbjKrnikBwa86414\nxR3OFWx29TPNE5lIUT1pQwMDVZsGUk9zMRVo4DNnYrN0wCwG8dQPAgMBAAGjEzAR\nMA8GA1UdEwEB/wQFMAMBAf8wDQYJKoZIhvcNAQELBQADggEBAGG3VEqN/B9+1jDI\nRDAvzh8KGT7181zq6qrCDHDnC4Po9WsDQseqJJJLlrEuMrn0jKxEFlwyFlALmuFU\n4rZmuzVH9PDZ25+tsZz8viu05ux33zrKT5aucPPyBQbGhvUDu9sIOTVvd1xJsrHX\n/Rs5F0ekiEf9puNGo3ewNZBmBte9lAGihq1O+sVDYISlCkPxeMYnF+WL0510p2Hm\nIa+ZNZ+ypHYGTIlC0Gcw4NRmLY5a67h6LQxqT70TGhSH5L1anLybD6Of4CpjDa3F\nR0XR+kZKRPoBkA2t97+9LaP24GA6veMCP6j4e1ezmG0mPrWNuL9L2xgAHhcDNPOV\nAKJ0Btc=\n-----END CERTIFICATE-----\n"
            - name: PRISM_client_rest_api
              value: "true"
            - name: PRISM_debug
              value: "true"
            - name: PRISM_dynamic_links
              value: "false"
            - name: PRISM_dropbox_count
              value: TODO "5"
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
          volumeMounts:
            - name: conf
              mountPath: /mnt/conf.d
      volumes:
        - name: conf
          emptyDir: {}
      imagePullSecrets:
        - name: artifactory-secret
---
# This NetworkPolicy is like a firewall rule that allows things outside your namespace to contact your pods. "Your pods"
# are matched according to the label selector "app: my-app".
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: prism-client-policy
  namespace: race-ta1
spec:
  podSelector:
    matchLabels:
      app: client-ss-app
  ingress:
    - ports:
        - port: 8080   # the port on the pod - not the ingress or service!
          protocol: TCP
    """