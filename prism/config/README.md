# PRISM Configuration Generator

## Requirements

- Docker (`prism-config` image is built as part of our standard set of Docker images)

OR

- Prism Local Dev Setup (as described in the [top-level README](../../README.md))

## Usage (Standalone)

After creating a new deployment in RIB, run

```shell script
sudo chown -R `id -u`:`id -g` ~/.race/rib/deployments/local/
```

To give yourself ownership over the deployment's files. Then

```shell script
python -m prism.config --deployment <DEPLOYMENT_NAME> scenarios/mpc.json
```

To configure it with our standard configuration.

To configure a test range without a corresponding local deployment,
pass the `--config PATH_TO_RANGE_CONFIG.json` and `--out PATH_TO_WRITE_CONFIG_FILES` command line arguments, e.g.

```shell script
python -m prism.config --config test_range.json --out range_config/test_range/ scenarios/mpc.json
```

## Usage (Docker -- recommended)

Using the utility script in our 
[plugin repository](https://gitlab.race.twosixlabs.com/race-ta1-sri/plugin-ta1-twosix-python),

```shell script
util/config.sh --deployment <DEPLOYMENT_NAME>
```

The main differences are in permissions and volume mounts for configuring non-local deployments. Because Docker comes
with root privileges built in, you don't need to assign yourself ownership of the deployment directory. The utility
script mounts `~/.race/rib/deployments/` to the same path inside the image, this directory to`/opt/prism/`, and
`../tools/config/scenarios` to `/opt/prism/scenarios`, with `/opt/prism` being the working directory inside the image.

So, if you had a range JSON file in `range_defs/test_range.json`, and wanted output in `rangeconfigs/test_range/`, and
wanted to use the `mpc.json` scenario, you would run

```shell script
util/config.sh --config range_defs/test_range.json \
    --out range_defs/test_range.json scenarios/mpc.json
```

## Configuration Options

The generator has a number of command line options, which you may peruse with the `-h` flag. In addition, it supports
loading configuration from any number of JSON files, listed at the end of the arguments. Command line flags take
precedence over JSON-configured options, and JSON files listed later on the command line take precedence over earlier
ones.

In addition to the CLI options, JSON files may also specify common parameters for clients and servers, by including
`server_common` or `client_common` sub-objects. An example file is provided as [scenarios/mpc.json](scenarios/mpc.json).
To see what parameters are supported, check the [client.toml](../common/config/client.toml) and 
[server.toml](../common/config/server.toml).

In general, it is preferable to specify all configuration parameters through version-controlled JSON files and only 
override them on CLI for rapid testing purposes.
