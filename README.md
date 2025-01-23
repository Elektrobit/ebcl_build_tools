# EBcL build helpers

## How to develop?

The recommended way to develop ebcl_build_tools is using the devcontainer.
It can used by loading the workspace into vscode and executing the command "Dev Containers: Reopen in Container".
This will download the dev container that contains all required tools,
install useful extensions (python, flake8, mypy, robot framework and pytest) and setup a virtual environment for development.

### Tests

#### pytest
The pytests are mostly unit tests but cross over into integration tests for some modules.
Some of these tests download packages from debian repositories. They should be marked with `@pytest.mark.requires_download`.

Test can be executed using ptest, either on the command line or using the testing integration.

#### robot framework
The robot framework tests are black box integration tests.
They take a long time to execute and download files from debian repositories.

To execute the tests either  the robot command line utility or the vscode integration can be used.
