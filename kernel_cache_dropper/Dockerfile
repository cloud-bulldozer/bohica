FROM fedora:31

RUN dnf install -y --nodocs python3 python3-cherrypy
RUN ln -s /usr/bin/python3 /usr/bin/python
COPY . /opt/kernel_cache_drop
