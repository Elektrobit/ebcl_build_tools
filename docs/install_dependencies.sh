#!/bin/bash

GIT_ROOT=$(git rev-parse --show-toplevel)

cd $GIT_ROOT

# Install curl
sudo apt install -y curl

# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

# Update PATH
source ~/.bashrc

# Install node LTS version
nvm install --lts

# Update PATH
source ~/.bashrc

node -v

# Install Antora and plugins
cd $GIT_ROOT
npm install
