FROM prism-base

COPY setup.py VERSION /usr/local/src/prism/
COPY bin /usr/local/src/prism/bin
COPY ./prism /usr/local/src/prism/prism
RUN pip3 install -e /usr/local/src/prism
