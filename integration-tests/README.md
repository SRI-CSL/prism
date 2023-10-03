# README on Integration Tests (Automated Test Framework)

## Dependencies

- Docker
- docker-compose
- Prism local dev environment set up [as described in the top-level README](../README.md).

Make sure you've built the latest docker images for the PRISM system.

    (venv)$ prism build

## Running

Run a test with:

    (venv)$ prism test

The framework will generate a configuration according to the
specified parameters, bring up the containers, and send messages between
each pair of clients. After all messages are received, or after a timeout, it
will bring down the containers and print out a report. Data for each run is stored in the `runs` subdirectory.

It is safe to interrupt the test process with Ctrl-C. Running containers will be
gracefully shut down, though you won't get a report.

You can also force re-builing as part of running a test:

    (venv)$ prism test -b

Other options are explained in the help text:

    (venv)$ prism test -h

## Monitoring

You can run a test with a specific output directory:

    (venv)$ prism test -o runs/test

And point the monitor to that directory to read log files from:

    (venv)$ prism monitor --dir runs/test/logs

## Overrides

You can override parameters of the testbed or the prism configuration by passing in `-Pkey=value` on the command line. 
For example, to run a test with 4 clients, `-Pclient_count=4`. 
Testbed specific parameters are defined in [params.py](../prism/testbed/params.py). 
PRISM system parameters are defined in [config.py](../prism/common/config/config.py).

## Web Mode

If web clients are enabled, no automatic testing will be done, but you will be
able to connect to the web clients with your browser at http://localhost:700X/docs/
where X is the client number.
