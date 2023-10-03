# NOTES on testing MPC stuff

## Terminals

To run a minimal MPC network in 3 terminals (no whiteboard or clients):

```bash
(venv)$ ROLE=DROPBOX_MPC DB_INDEX=5 PARTY_ID=0 COMMITTEE_MEMBERS=tcp://localhost:13578,tcp://localhost:13579,tcp://localhost:13570 ID=obdbx.0.test python -m prism.server
(venv)$ ROLE=DROPBOX_MPC PARTY_ID=1 COMMITTEE_MEMBERS=tcp://localhost:13578,tcp://localhost:13579,tcp://localhost:13570 ID=obdbx.1.test python -m prism.server
(venv)$ ROLE=DROPBOX_MPC PARTY_ID=2 COMMITTEE_MEMBERS=tcp://localhost:13578,tcp://localhost:13579,tcp://localhost:13570 ID=obdbx.2.test python -m prism.server
```

In order to test multi-role setups, we use the new way of declaring multiple roles and party IDs like s:

```bash
(venv)$ PRISM_SERVER_ROLES="['EMIX','DROPBOX_MPC','DROPBOX_MPC']" DB_INDEX=0 PRISM_SERVER_PARTY_IDS=[2,0] COMMITTEE_MEMBERS=tcp://localhost:7381,tcp://localhost:7382,tcp://localhost:7381 ID=obdbx.02 python -m prism.server
(venv)$ ROLE=DROPBOX_MPC PRISM_SERVER_PARTY_IDS=[1] COMMITTEE_MEMBERS=tcp://localhost:7381,tcp://localhost:7382,tcp://localhost:7381 ID=obdbx.1 python -m prism.server
```

## Docker 

We now use the `../integration-tests` framework to generate Docker-Compose files to be used, like so:

    $ cd ../integration-tests
    $ source venv/bin/activate
    (venv)$ python -m prism.testbed scenarios/mpc3.json --generate ../prism-server/integration-tests/mpc3.json
    (venv)$ python -m prism.testbed scenarios/mpc3.json scenarios/jaeger.json --generate ../prism-server/integration-tests/mpc3_jaeger.json

Possibly edit the `.json` file to suppress logging from Bebo, like so:

    "whiteboard0": {
      "image": "race-ta1-docker.cse.sri.com/prism-bebo",
      "command": ["python", "-m", "bebo.server", "-L", "/tmp/bebo.log"],
      ...

Running:

    $ ./build.sh  # if needed
    [...]   
    $ docker-compose -f integration-tests/mpc3_jaeger.json up
    [...]
    $ docker-compose -f integration-tests/mpc3_jaeger.json down

Testing with MPC Malicious:

    $ DEBUG=True PRISM_SERVER_MPC_MALICIOUS=True docker-compose -f <compose-file> up | grep prism-server
    ^C 
    $ docker-compose -f <compose-file> down

## Clients 

The standard client personas are `prism-client-0` (port 7000) and `prism-client-1` (7001).
Messages can be sent from the command line:

    $ echo '{"command": "send", "sender": "prism-client-0", "receiver": "prism-client-1", "message": "hi there"}' | nc 127.0.0.1 7000
    ^C

and on the receiving end:

    $ nc 127.0.0.1 7001
    ...

## Inducing random sending delays

To test some failure modes where we need to recover from delayed messaging in MPC, we can induce a random delay 
for TCP like so:

    $ PRISM_SERVER_MPC_MODULUS_TIMEOUT=8 PRISM_SERVER_SOCKET_TEST_DELAY=9 \
      docker-compose -f <compose-file> up | grep prism_server
