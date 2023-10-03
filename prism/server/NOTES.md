# Developer Notes for PRISM Server

## Deployment 

### Artifactory

#### Manual Deployment

Build and deploy with `-d` with:

    $ ./build.sh [-c] -d

Help:

    $ ./build.sh -h
    Usage: ./build.sh [options]
      where
        -h  Display this help message
        -c  Add --no-cache to Docker build command
        -d  Also deploy the image to Artifactory after building
    
#### Using GitLab CI/CD

See `../versions.md`.

### On Kubernetes Cluster

Deploy latest Docker image to Artifactory per the above, then follow instructions in the `../k8s/` directory 
to stand up PRISM server and whiteboard machines.  Make sure to match the version numbers for the Docker 
images with the ones used in the deployment `.yaml` scripts.


## Docker Cheat Sheet

Checking status:

    $ docker ps -a
    $ docker images
    $ docker network ls
    $ docker-compose up|stop|down
    [...]

CLeaning up:

    $ docker system df
    $ docker image prune -f  # to remove reclaimable space
    $ docker rmi $(docker images -q -f dangling=true)  # sometimes we can free up extra space with this
    
## Links

* "Run while loop concurrently with Flask server" [https://stackoverflow.com/a/39337670/3816489]
* "Shutdown The Simple Server" [http://flask.pocoo.org/snippets/67/]
* Docker volumes for persisting logs: [https://www.digitalocean.com/community/tutorials/how-to-work-with-docker-data-volumes-on-ubuntu-14-04]
* Docker CMD vs. ENTRYPOINT tutorial: [https://blog.codeship.com/understanding-dockers-cmd-and-entrypoint-instructions/]
* ENTRYPOINT + CMD: [https://aws.amazon.com/blogs/opensource/demystifying-entrypoint-cmd-docker/]
* env variables in docker-compose.yml with CATALINA_OPTS: [https://stackoverflow.com/a/46058817/3816489]
* multiple docker-compose instances: [https://pspdfkit.com /blog/2018/how-to-use-docker-compose-to-run-multiple-instances-of-a-service-in-development/]
* HTTP requests [https://2.python-requests.org/en/master/]
* tail -f log file in Flask template: [https://stackoverflow.com/a/35541970/3816489]
