#!/bin/bash

GIT_ROOT=$(git rev-parse --show-toplevel)

cd $GIT_ROOT

# Install curl
sudo apt install -y curl

# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash

export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion

# Install node LTS version
nvm install --lts

# Update PATH
source ~/.bashrc

node -v

# Install Antora and plugins
cd $GIT_ROOT
npm install
