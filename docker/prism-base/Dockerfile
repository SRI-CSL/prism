FROM debian:buster-slim

COPY apt-requirements.txt /

RUN apt-get update --allow-insecure-repositories \
    && bash -c "xargs -a <(awk '! /^ *(#|$)/' /apt-requirements.txt) -r -- \
       apt-get install -y --no-install-recommends" \
    && rm -rf /var/lib/apt/lists/*

RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.7 2
RUN pip3 install setuptools wheel

# download and compile PBC:
WORKDIR /usr/local/src
RUN curl -o pbc-0.5.14.tar.gz https://crypto.stanford.edu/pbc/files/pbc-0.5.14.tar.gz; \
    tar xzvf pbc-0.5.14.tar.gz;
WORKDIR /usr/local/src/pbc-0.5.14
RUN ./configure; make -j8; make install

# compile BFIBE
RUN mkdir -p /usr/local/src/bfibe/build
COPY bfibe /usr/local/src/bfibe
WORKDIR /usr/local/src/bfibe/build
RUN cmake -DOPENSSL_ROOT_DIR=/usr/include/openssl/ ..; make; make install

# install Python dependencies
COPY requirements.txt /
RUN pip3 install -r /requirements.txt

RUN mkdir -p /usr/local/src
RUN mkdir -p /opt/prism/lib
RUN mkdir -p /log
RUN mkdir -p /config

ENV LD_LIBRARY_PATH=/usr/lib/x86_64-linux-gnu:/usr/local/lib
ENV CLASSPATH="/opt/prism/lib/*"

COPY LICENSE.txt /
COPY README.md /

ARG VERSION
ARG GIT_COMMIT=unspecified
ARG GIT_BRANCH=unspecified
ENV VERSION=$VERSION
ENV GIT_COMMIT=$GIT_COMMIT
LABEL version=$VERSION
LABEL git_commit=$GIT_COMMIT
LABEL git_branch=$GIT_BRANCH

WORKDIR /opt/prism
RUN echo "version=${VERSION}\ngit_commit=${GIT_COMMIT}\ngit_branch=${GIT_BRANCH}" > /opt/prism/VERSION
