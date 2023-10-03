
The BEBO whiteboard server can be run with

	python -m bebo.server

The stress test can be run with

	python -m bebo.stress

but you must have interface aliases set up.  The set_aliases script
does this for the mac.

I have been using pyenv and poetry.  I use pyenv to deal with having
multiple python versions and to avoid having to call python "python3",
which poetry didn't like.

Poetry is a virtual environment and dependency system, so

	poetry install          # only have to do this once
        poetry run server

will run using the pyenv selected python in a python virtual
environment that contains only the dependencies needed by bebo.  This
keeps your python site-packages from filling up with cruft and helps
avoid dependency issues.  Poetry also provides version locking, so
everyone in testing with the same versions (as specified in the
poetry.lock file).

I've duplicated the requirements into the requirements.txt file
so that you can do a pip installation in a Dockerfile.
