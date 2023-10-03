# Open Source PRISM Components

Source code for PRISM components and Docker image creation

## Development dependencies

* Python 3.7+ (tested with 3.8) with the pip and venv modules
* Docker 20.0+ (tested with CPUs: 4, Memory: 16GB, Swap: 1GB, Disk image size: 256GB)
* Git

## Setting up for development

Install a Python 3.7+ virtual environment, for example with:
```
$ python3 -m venv venv
```

Then activate and install requirements like so:
```
$ source venv/bin/activate
(venv)$ pip install -r requirements.txt
(venv)$ pip install -e .
(venv)$ pip install -e rib  # if you want RiB tools such as `prt`
```

## Component Documentation

* [Boneh-Franklin IBE Implementation](./bfibe/README.md)
* [Testbed](./integration-tests/README.md)
* [BEBO](./bebo/README.rst)
* [SimpleProxy Demo App](./tools/simpleproxy/README.txt)
* [RIB Plugin](./rib/README.md)

## License

See the file `LICENSE.txt` for details.  Also included as a file in Docker images.
