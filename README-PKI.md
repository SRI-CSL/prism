# README on PKI approximations


## Python Command Line (single PRISM server)

Install OpenSSL for CLI use, e.g., `brew install openssl`

TODO


## For Local Integration Tests

Using the `prism test` framework, we can do the following.  Use `--generate` to only generate deployments but not 
running them.  Use `--no-test` to generate and bring up the Docker deployment, then prod at containers such as 
Jaeger and BEBO (for ARK details).

Note `--param pki=true` is no longer necessary as this is the default now.  To see things without signing, simply 
set `--param pki=false`.

```bash
# create Root CA cert and 1 epochs worth of <cert, key> pairs for all servers:
prism test --param pki_epochs=1  # [ --no-test | --generate ]

# create only Root CA key + cert for each server to self-sign runtime certificates:
prism test  # [ --no-test | --generate ]
```

To check minimum and maximum of ARK packet sizes:
```bash
find integration-tests/runs/current/logs -name replay.log -exec grep "ARK" {} \; | jq .size | sort -n | uniq
```

To see that ARKs are now signed, run with `--no-test` and then open Bebo dashboard at http://localhost:8081 
and click on any message labeled "ARK" to see a field called `signature`. 


To see debug messages related to the loading of PKI from testbed configs, run these:
```bash
# see if and how PKI got established (via configs or files or queues):
find integration-tests/runs/current/logs -name prism.server.log.out -exec grep "Loaded PRISM Root CA " {} \;
# see if and how PKI Root CA got created:
find integration-tests/runs/current/logs -name "prism.*.log.out" -exec grep "Created PRISM " {} \;
# see the `signature` field populated in own ARK messages:
find integration-tests/runs/current/logs -name prism.server.log.out -exec grep "Updated own ARK" {} \;
```


## In RiB

Only RiB (at the moment) supports epoch switches, so to test PKI with epochs other than genesis, do:

```bash
prt override pki=true  # no longer needed, as it is the default now
prt override pki=false  # if we need to revert back to unsigned ARK messages (e.g., due to performance reasons)
prt override pki_epochs=0  # anything else than zero here (or do not override this one) won't work!
prt create -vf
```

Once running, check that epoch switching works (per usual commands).

To check the size of ARK messages, do:
```bash
export DEPLOY=5x20
# see sizes of batched ARKs:
find $HOME/.race/rib/deployments/local/$DEPLOY/logs/ -name replay.log -exec grep "ARKs" {} \; | jq .size | sort -n | uniq
# see sizes of individual LSP messages (note matching the closing double quotes):
find $HOME/.race/rib/deployments/local/$DEPLOY/logs/ -name replay.log -exec grep "LSP\"" {} \; | jq .size | sort -n | uniq
# see if and how PKI got established (no match if not PKI):
prt log s | grep "Loaded PRISM Root CA "
prt log s | grep "Created PRISM "
prt log c | grep "Created PRISM "
# see `signature` field for servers:
prt log s | grep "Updated own ARK"
```
