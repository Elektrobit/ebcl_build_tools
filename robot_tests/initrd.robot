*** Settings ***
Library  lib/Fakeroot.py
Library  lib/Initrd.py
Library  String
Library  Collections
Suite Setup  Setup
Suite Teardown  Teardown

*** Variables ***
${CONFIG}    ../data/initrd.yaml
@{EXPECTED_MODULES}
...    virtio_net
...    bridge
...    stp

*** Test Cases ***
Root Device is Mounted
    Device should be mounted  /dev/mmcblk0p2    /sysroot

Devices are Created
    File Should Exist    /dev/console    character special file
    File Should Exist    /dev/mmcblk1    block special file

Rootfs should be set up
    Directory Should Exist  /proc
    Directory Should Exist  /sys
    Directory Should Exist  /dev
    Directory Should Exist  /sysroot
    Directory Should Exist  /var
    Directory Should Exist  /tmp
    Directory Should Exist  /run
    Directory Should Exist  /root
    Directory Should Exist  /usr
    Directory Should Exist  /usr/sbin
    Directory Should Exist  /usr/lib
    Directory Should Exist  /usr/bin
    Directory Should Exist  /etc

File dummy.txt should be OK
    Should Be Owned By   /root/dummy.txt    0    0
    Should Have Mode     /root/dummy.txt    664

File other.txt should be OK
    Should Be Owned By   /root/other.txt    123    456
    Should Have Mode     /root/other.txt    777

Modules are installed
    File Should Exist  /lib/modules/5.15.0-113-generic/modules.dep
    
    File Should Exist  /lib/modules/5.15.0-113-generic/kernel/drivers/net/virtio_net.ko
    # Dependencies of virtio_net
    File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/core/failover.ko
    File Should Exist  /lib/modules/5.15.0-113-generic/kernel/drivers/net/net_failover.ko

    File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/bridge/bridge.ko
    # Dependencies of bridge
    File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/802/stp.ko
    File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/llc/llc.ko

Check modules loaded by init
    @{modules}=  Get Loaded Modules
    Lists Should Be Equal  ${modules}  ${EXPECTED_MODULES}


*** Keywords ***
Setup
    Build Initrd    ${CONFIG}
    Load

Teardown
    Cleanup

Get Loaded Modules
    ${init} =     Get File  /init
    @{lines} =    Split To Lines  ${init}
    @{matches} =  Get Matches  ${lines}  regexp=^\\s*modprobe\\s+.*$
    @{modules}=   Create List
    FOR  ${match}  IN  @{matches}
        ${match} =  Replace String Using Regexp  ${match}  ^\\s*modprobe\\s+(.*)$  \\1
        Append To List  ${modules}  ${match}
    END
    RETURN  @{modules}
