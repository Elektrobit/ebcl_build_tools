*** Settings ***
Library  lib/Fakeroot.py
Library  lib/Boot.py
Suite Setup  Setup
Suite Teardown  Teardown

*** Test Cases ***
Kernel exists
    File Should Exist    /vmlinuz*

Config is OK
    File Should Exist    /config*

Script was executed
    File Should Exist    /some_config    regular empty file

*** Keywords ***
Setup
    Build Boot
    Load

Teardown
    Cleanup
