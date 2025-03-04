*** Settings ***
Library  lib/Fakeroot.py
Library  lib/Root.py
Suite Setup  Setup
Suite Teardown  Teardown

*** Test Cases ***
Systemd should exist
    File Should Exist    /usr/bin/systemd    symbolic link

Fakeoot config executed
    File Should Exist    /fake

Fakechroot config was executed
    File Should Exist    /sudo

Chroot config was executed
    File Should Exist    /chroot

Resolv.conf symlink should exist
    File Should Exist    /usr/bin/systemd    symbolic link

*** Keywords ***
Setup
    Build Root
    Load

Teardown
    Cleanup
