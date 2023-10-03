# How to manage stand-alone, PRISM-only OSS version

This file contains instructions on how to prepare an Open-Source Software release and manage it.


## Creating Snapshot

```bash
export GIT_REPO=prism-oss
git archive -o ../${GIT_REPO}.tgz -v --worktree-attributes HEAD .
```


## Testing Snapshot

Requirements:
* Python 3.8 - 3.10 (3.11 did not work for `pip` dependencies)
* Docker Engine

For testing, create the tar archive above and extract it in the `~/tmp/junk` directory.
```bash
rm -rf ~/tmp/junk
git archive --format=tar --prefix=junk/ --worktree-attributes HEAD | (cd ~/tmp/ && tar xf -)
```
Now one can open terminal in `~/tmp/junk` and run these commands to prepare the development environment:
```bash
python3 -m venv venv  # Python 3.8 or newer
source venv/bin/activate
pip install -r requirements.txt
pip install -e .
```
Now it is time to build and test:
```bash
prism build  # this may take a while upon the first invocation as Docker pulls needed images
prism test  # should take somewhere between 30s and 2m to finish
```


## Pushing to Public Repo

Here are the options where we can publish under SRI's brand name:
* https://github.com/SRI-CSL
* https://gitlab.sri.com/ ()