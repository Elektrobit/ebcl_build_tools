#!/bin/sh

echo "chroot" >> /chroot

# Create resolv.conf symlink
ln -sf etc etc/resolv.conf
