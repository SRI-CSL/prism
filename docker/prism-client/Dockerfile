FROM bfibe:latest

# Cache Gradle wrapper, for non-dev build
RUN mkdir -p /usr/local/src/prism/client
COPY *.gradle gradle.* gradlew /usr/local/src/prism
COPY gradle /usr/local/src/prism/gradle
WORKDIR /usr/local/src/prism
RUN ./gradlew --version

COPY client /usr/local/src/prism/client

# compile PRISM client sources:
WORKDIR /usr/local/src/prism/client/cli
RUN bash setup.sh
