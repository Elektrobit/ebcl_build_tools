#!/bin/bash

# install the build tools
source /build/venv/bin/activate && pip install -e .

# install dev dependencies
source /build/venv/bin/activate && pip install -r dev-requirements.txt

ln -sf /build build
ln -sf /build/venv .venv
