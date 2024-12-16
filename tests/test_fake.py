""" Tests for the fake functions. """
import os
import tempfile

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
        (stdout, stderr, _returncode) = self.fake.run_cmd(
            'id', capture_output=True)
        assert stdout is not None
        assert f'uid={os.getuid()}' in stdout
        assert f'gid={os.getgid()}' in stdout
        assert stderr is not None
        assert not stderr.strip()

    def test_run_fake(self):
        """ Run a command using fakeroot. """
        (stdout, stderr, _returncode) = self.fake.run_fake(
            'id', capture_output=True)
        assert stdout is not None
        assert 'uid=0(root)' in stdout
        assert 'gid=0(root)' in stdout
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
            '/bin/busybox --install -s /bin', chroot, capture_output=True)
        assert stderr is not None
        assert not stderr.strip()

        # Prepare dev folder
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            'mkdir -p dev', chroot, capture_output=True)
        assert stderr is not None
        assert not stderr.strip()

        # Check folder
        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%u %g\' /dev', chroot, capture_output=True)
        assert stdout
        assert stdout.strip() == '0 0'
        assert stderr is not None
        assert not stderr.strip()

        # Create device node
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            'mknod -m 777 /dev/console c 1234 1234', chroot, capture_output=True)
        assert stderr is not None
        assert not stderr.strip()

        # Check device node
        (stdout, stderr, _returncode) = self.fake.run_chroot(
            'stat -c \'%A %u %g\' /dev/console', chroot, capture_output=True)
        assert stdout
        assert stdout.strip() == 'crwxrwxrwx 0 0'
        assert stderr is not None
        assert not stderr.strip()

        self.fake.run_sudo(f'rm -rf {chroot}')

    def test_run_sudo(self):
        """ Run a command using sudo. """
        (stdout, stderr, _returncode) = self.fake.run_sudo(
            'id', capture_output=True)
        assert stdout is not None
        assert 'uid=0(root)' in stdout
        assert 'gid=0(root)' in stdout
        assert stderr is not None
        assert not stderr.strip()
