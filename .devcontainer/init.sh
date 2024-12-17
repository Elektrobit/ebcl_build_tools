#!/bin/bash

ln -sf /build/venv .venv

UID=$(id -u)
if [ $UID -ne 0 ]; then
    echo "Fixing permissions of /build"
    sudo chown -R $(id -un):$(id -gn) /build
fi

# install the build tools
source /build/venv/bin/activate && pip install -e .

# install dev dependencies
source /build/venv/bin/activate && pip install -r dev-requirements.txt

ln -sf /build build
