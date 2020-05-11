FROM registry.access.redhat.com/ubi8:latest

RUN dnf install -y --nodocs python3
RUN ln -s /usr/bin/python3 /usr/bin/python
COPY . /opt/kernel_cache_dropper
