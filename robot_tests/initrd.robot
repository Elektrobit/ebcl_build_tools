*** Settings ***
Library  lib/Fakeroot.py
Library  lib/Initrd.py
Library  String
Library  Collections
Library  OperatingSystem
Suite Setup  Build
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
    Initrd.File Should Exist    /dev/console    character special file
    Initrd.File Should Exist    /dev/mmcblk1    block special file

Rootfs should be set up
    Initrd.Directory Should Exist  /proc
    Initrd.Directory Should Exist  /sys
    Initrd.Directory Should Exist  /dev
    Initrd.Directory Should Exist  /sysroot
    Initrd.Directory Should Exist  /var
    Initrd.Directory Should Exist  /tmp
    Initrd.Directory Should Exist  /run
    Initrd.Directory Should Exist  /root
    Initrd.Directory Should Exist  /usr
    Initrd.Directory Should Exist  /sbin
    Initrd.Directory Should Exist  /lib
    Initrd.Directory Should Exist  /etc

File dummy.txt should be OK
    Should Be Owned By   /root/dummy.txt    0    0
    Should Have Mode     /root/dummy.txt    664

File other.txt should be OK
    Should Be Owned By   /root/other.txt    123    456
    Should Have Mode     /root/other.txt    777

Modules are installed
    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/modules.dep
    
    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/kernel/drivers/net/virtio_net.ko
    # Dependencies of virtio_net
    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/core/failover.ko
    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/kernel/drivers/net/net_failover.ko

    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/bridge/bridge.ko
    # Dependencies of bridge
    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/802/stp.ko
    Initrd.File Should Exist  /lib/modules/5.15.0-113-generic/kernel/net/llc/llc.ko

Check modules loaded by init
    @{modules}=  Get Loaded Modules
    Lists Should Be Equal  ${modules}  ${EXPECTED_MODULES}

Check reproducible Build
    Set Environment Variable  SOURCE_DATE_EPOCH  0
    ${initrd1_result} =     Build Initrd    ${CONFIG}
    ${initrd2_result} =     Build Initrd    ${CONFIG}
    ${rc} =     Run and Return RC    diffoscope ${initrd1_result}/initrd.img ${initrd2_result}/initrd.img
    Should Be Equal As Integers     ${rc}   0


*** Keywords ***
Build
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
