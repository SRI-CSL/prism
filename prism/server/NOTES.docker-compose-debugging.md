# NOTES on Debugging an Integration Test Using `docker-compose`

The idea is to have an integration test with all desired components - whiteboards, clients, servers - deployed on 
localhost but not starting one server, which is to be debugged.  In order to step through the Python debugger with 
PyCharm (CE), we will start the deployment and then manually add the debugged server later.

The example could be the JSON file `base_no_db.json` which has a whiteboard, 2 clients, and 1 emix, but no dropbox.

Then, we want to start the missing dropbox in the virtual environment under the PyCharm debugger but connecting to 
the deployment via port-forwarding.

## Generate and Start `docker-compose` File

In `integration-tests/`:

```bash
(venv)$ python -m prism.testbed scenarios/base.json scenarios/no_jaeger.json --generate ../prism-server/integration-tests/base_no_jaeger.json
```

In `prism-server/`, start the generated `docker-compose` file but only 3 of the 4 PRISM nodes (the dependencies of 
whiteboards is getting started automatically).  The example below will run and debug `prism-server-1` in 
PyCharm, which is the DROPBOX.  To debug the EMIX server, simply switch both in the two commands below.

```bash
docker-compose -f integration-tests/base_no_jaeger.json prism-server-0 prism-client-0 prism-client-1
```
and in PyCharm, configure these ENVs:
```
ROLE=DROPBOX
WHITEBOARDS=http://localhost:8080
DB_INDEX=0
DELAY=1  # to speed things up
```
to run the Python module `prism.server` normally or in debug mode.

Next, we look at a more complicated MPC scenario, with 2 servers that may play multiple roles.  
In the `docker-compose` file, assume that the PRISM server specifications look like this 
(additional settings may be present).  Note the differing definitions of `COMMITTEE_MEMBERS` - 
this assumes that you bring up the `docker-compose` file with only 1 of the 2 servers requested!
Whenever a "bridged" docker container needs to reach out to host (on Mac OS X), we use the 
specific host name `host.docker.internal`.
```json
{
  "prism-server-0": {
    "image": "race-ta1-docker.cse.sri.com/prism-server",
    "container_name": "prism-server-0",
    "environment": [
      "PRISM_SERVER_ROLES=['EMIX','DROPBOX_MPC','DROPBOX_MPC']",
      "PRISM_SERVER_PARTY_IDS=[2,0]",       
      "COMMITTEE_MEMBERS=tcp://prism-server-0:7380,tcp://host.docker.internal:7381,tcp://prism-server-0:7380",
      "DB_INDEX=0",
      "THRESHOLD=2",
      "ID=obdbx.0"
    ],
    "ports": [
      "7380:7380"
    ],
    "depends_on": [
    ]
  },
  "prism-server-1": {
    "image": "race-ta1-docker.cse.sri.com/prism-server",
    "container_name": "prism-server-1",
    "environment": [
      "PRISM_SERVER_ROLES=['DROPBOX_MPC']",
      "PRISM_SERVER_PARTY_IDS=[1]",
      "COMMITTEE_MEMBERS=tcp://host.docker.internal:7380,tcp://prism-server-1:7381,tcp://host.docker.internal:7380",
      "ID=obdbx.1"
    ],
    "ports": [
      "7381:7381"
    ],
    "depends_on": [
    ]
  }
}
```

Now bring up a partial `docker-compose` like this, e.g., debugging `prism-server-0` in PyCharm:
```bash
docker-compose -f integration-tests/mpc3_schizophrenic.json up prism-server-1
```
and in PyCharm configure the other server with these ENV vars:
```
COMMITTEE_MEMBERS=tcp://localhost:7380,tcp://localhost:7381,tcp://localhost:7380
DB_INDEX=0
THRESHOLD=2
PRISM_SERVER_PARTY_IDS=[2,0]
PRISM_SERVER_ROLES=['EMIX','DROPBOX_MPC','DROPBOX_MPC']
```

To reverse the debugging setup, invoke `docker-compose` with `prism-server-0` and configure the PyCharm runtime with 
the respective ENV vars for `prism-server-1`, substituting host names in `COMMITTEE_MEMBERS` with `localhost`.

## Debugging MPC 3-2

First, in your adjusted `mpc3_debugging.json`, make sure that all `DROPBOX_MPC` containers have different ports 
assigned and exposed (since they all get mapped to localhost) and unset the `COMMITTEE_MEMBERS` environment variable, 
like so:
```json
{
  "prism-server-1": {
    "container_name": "prism-server-1",
    "environment": [
      "COMMITTEE_MEMBERS"
    ],
    "ports": [
      "7381:7381"
    ]
  }
}
```

Then, invoke `docker-compose` with only a customized `COMMITTEE_MEMBERS` in which the position of the members run 
outside of docker are using the special hostname `host.docker.internal`.  For example, to run `prism-server-2` 
container outside, omit it from the list of services to start and replace the second position in the list of members:
```bash
COMMITTEE_MEMBERS=tcp://prism-server-1:7381,tcp://host.docker.internal:7382,tcp://prism-server-3:7383 \
  docker-compose -f integration-tests/mpc3_debugging.json up \
    prism-server-0 prism-server-1 prism-server-3 prism-client-0 prism-client-1
```
(Note that `prism-server-0` in the setting above is an `EMIX`.)

Then, starting `prism-server-2` in PyCharm:
```
ROLE=DROPBOX_MPC
PARTY_ID=1                         # or {0 (leader), 2} in the MPC 3-2 scenario
COMMITTEE_MEMBERS=tcp://localhost:7381,tcp://localhost:7382,tcp://localhost:7383
THRESHOLD=2                        # only needed for running PARTY_ID=0 (leader)
DB_INDEX=0                         # only needed for running PARTY_ID=0 (leader)
WHITEBOARDS=http://localhost:8080  # only needed for running PARTY_ID=0 (leader)
```

Note: if debugging `prism-server-1` in PyCharm then make sure to bring up `docker-compose` first in order to have the 
whiteboard be instantiated before the leader tries to access it.

To kill a server rudely, do:
```bash
docker stop prism-server-3
```

To get all names of services defined in a docker-compose file:
```bash
docker-compose -f integration-tests/mpc3.json config --service
...
```
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
