FROM prism-base

RUN mkdir -p /opt/bebo
COPY bebo/bebo /opt/bebo

RUN cp /opt/prism/VERSION /opt/bebo/VERSION
WORKDIR /opt

# run application
EXPOSE 4000
EXPOSE 48816
ENV DEBUG=False
ENV PRODUCTION=True
ENTRYPOINT ["python", "-m", "bebo.server"]
