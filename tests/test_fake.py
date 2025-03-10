""" Tests for the fake functions. """
import os
import tempfile

import pytest

from ebcl.common.apt import Apt, AptDebRepo
from ebcl.common.fake import Fake
from ebcl.common.proxy import Proxy
from ebcl.common.types.cpu_arch import CpuArch


class TestFake:
    """ Tests for the fake functions. """

    fake: Fake
    apt: Apt
    proxy: Proxy

    @classmethod
    def setup_class(cls):
        """ Prepare apt repo object. """
        cls.fake = Fake()
        cls.apt = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                components=['main'],
                arch=CpuArch.AMD64
            )
        )
        cls.proxy = Proxy()
        cls.proxy.add_apt(cls.apt)

    def test_run_cmd(self):
        """ Run a command using a default shell. """
        (stdout, stderr, _returncode) = self.fake.run_cmd('id')
        assert stdout is not None
        assert f'uid={os.getuid()}' in stdout
        assert f'gid={os.getgid()}' in stdout
        assert stderr is not None
        assert not stderr.strip()

    def test_run_fake(self):
        """ Run a command using fakeroot. """
        (stdout, stderr, _returncode) = self.fake.run_fake('id')
        assert stdout is not None
        assert 'uid=0(root)' in stdout
        assert 'gid=0(root)' in stdout
        assert stderr is not None
        assert not stderr.strip()

    def test_chroot_special_folders(self):
        """ Check that the special filesystems are available in the chroot env. """
        # Prepare fakeroot
        # Get busybox
        ps = self.apt.find_package('busybox-static')
        assert ps
        p = ps[0]

        chroot = tempfile.mkdtemp()

        pkg = self.proxy.download_package(self.apt.arch, p)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

        pkg.extract(chroot)

        # Install busybox
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            '/bin/busybox --install -s /bin', chroot)
        assert stderr is not None
        assert not stderr.strip()

        # Create resolv.conf symlink
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            'ln -sf etc etc/resolv.conf', chroot)
        assert stderr is not None
        assert not stderr.strip()

        # Check proc is mounted
        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%u %g\' /proc/cmdline', chroot)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

        # Check sysfs is mounted
        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%u %g\' /sys/dev', chroot)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

        # Check dev/pts is mounted
        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%u %g\' /dev/pts', chroot)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

        # Check DNS config
        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%u %g\' /etc/resolv.conf', chroot)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%u %g\' /etc/gai.conf', chroot)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

        # Check reslov.conf symlink still exists
        (stdout, stderr, _returncode) = self.fake.run_sudo(
            'stat -c \'%u %g\' /etc/resolv.conf', chroot)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

    @pytest.mark.requires_download
    def test_ping_eb_apt(self):
        """ Check that the ping to eb apt works form chroot. """
        # Prepare fakeroot
        # Get busybox
        ps = self.apt.find_package('busybox-static')
        assert ps
        p = ps[0]

        chroot = tempfile.mkdtemp()

        pkg = self.proxy.download_package(self.apt.arch, p)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

        pkg.extract(chroot)

        # Install busybox
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            '/bin/busybox --install -s /bin', chroot)
        assert stderr is not None
        assert not stderr.strip()

        (stdout, stderr, returncode) = self.fake.run_chroot(
            'ping -c 1 linux.elektrobit.com', chroot)
        assert returncode == 0
        assert stderr is not None
        assert not stderr.strip()

    def test_run_chroot(self):
        """ Run a command using fakechroot. """
        # Prepare fakeroot
        # Get busybox
        ps = self.apt.find_package('busybox-static')
        assert ps
        p = ps[0]

        chroot = tempfile.mkdtemp()

        pkg = self.proxy.download_package(self.apt.arch, p)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

        pkg.extract(chroot)

        # Install busybox
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            '/bin/busybox --install -s /bin', chroot)
        assert stderr is not None
        assert not stderr.strip()

        self.fake.run_sudo(f'rm -rf {chroot}')

    def test_run_sudo(self):
        """ Run a command using sudo. """
        (stdout, stderr, _returncode) = self.fake.run_sudo(
            'id')
        assert stdout is not None
        assert 'uid=0(root)' in stdout
        assert 'gid=0(root)' in stdout
        assert stderr is not None
        assert not stderr.strip()
