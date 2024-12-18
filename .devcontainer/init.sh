#!/bin/bash

# Link the venv, so that the WolfiesHorizon.python-auto-venv
# VS Code plugin will use it by default.
ln -sf /build/venv .venv

UID=$(id -u)
if [ $UID -ne 0 ]; then
    # Change ownership of the venv and the installed tool
    # to allow installation of further Python packages and
    # live hacking of the tools.
    echo "Fixing permissions of /build"
    sudo chown -R $(id -un):$(id -gn) /build
fi

# Install the build tools from the local repository.
source /build/venv/bin/activate && pip install -e .

# Install the development dependencies.
source /build/venv/bin/activate && pip install -r dev-requirements.txt

# Link the build folder to the workspace, so that the tools
# can be inspected using the VS Code file browser.
ln -sf /build build
