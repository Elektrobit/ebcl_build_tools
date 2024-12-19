# This base container adds a container user called "developer".
# Please adapt the HOST_USER and HOST_GROUP to your UID and GID
# to avoid access rights issues. You can find out your UID and
# GID using the `id` command.

# Starting from the latest Debian container.
# Any other Debian or Ubuntu container should also work.
FROM debian:latest

ARG CONTAINER_USER="developer"
ARG HOST_USER=1000
ARG HOST_GROUP=1000

RUN apt update
RUN apt upgrade

# Install sudo, to allow privileged command execution.
RUN DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC apt install -y sudo

# Delete user with given UID if it exists
RUN userdel $(id -nu $HOST_USER) || true
# Delete group with given GID if it exists
RUN groupdel $(awk -F: '$3 == $HOST_GROUP' /etc/group | cut -d: -f1) || true

# Create the user
# and allow using `sudo` without password.
RUN groupadd --gid $HOST_GROUP $CONTAINER_USER \
    && useradd -rm -d /home/$CONTAINER_USER -s /usr/bin/bash -g $CONTAINER_USER -G sudo -u $HOST_USER $CONTAINER_USER \
    && mkdir -p /etc/sudoers.d \
    && echo $CONTAINER_USER ALL=\(root\) NOPASSWD:ALL > /etc/sudoers.d/$CONTAINER_USER \
    && chmod 0440 /etc/sudoers.d/$CONTAINER_USER

# Create mount point for stand-alone usage
RUN mkdir -p /workspace

# Run bash as default entry command.
ENTRYPOINT /usr/bin/bash
