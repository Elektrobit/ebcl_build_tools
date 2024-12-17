FROM debian:latest

ARG CONTAINER_USER="developer"
ARG HOST_USER=1000
ARG HOST_GROUP=1000

RUN apt update
RUN apt upgrade

RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt install -y sudo

# Delete user with given UID if it exists
RUN userdel $(id -nu $HOST_USER) || true
# Delete group with given GID if it exists
RUN groupdel $(awk -F: '$3 == $HOST_GROUP' /etc/group | cut -d: -f1) || true

# Create the user
RUN groupadd --gid $HOST_GROUP $CONTAINER_USER \
    && useradd -rm -d /home/$CONTAINER_USER -s /usr/bin/bash -g $CONTAINER_USER -G sudo -u $HOST_USER $CONTAINER_USER \
    && mkdir -p /etc/sudoers.d \
    && echo $CONTAINER_USER ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$CONTAINER_USER \
    && chmod 0440 /etc/sudoers.d/$CONTAINER_USER

ENTRYPOINT /usr/bin/bash
