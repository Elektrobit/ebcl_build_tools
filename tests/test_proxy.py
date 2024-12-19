""" Unit tests for the EBcL apt proxy. """
import platform
import pytest

from pathlib import Path

from ebcl.common.apt import Apt, parse_depends
from ebcl.common.proxy import Proxy

from ebcl.common.types.cpu_arch import CpuArch


class TestProxy:
    """ Unit tests for the EBcL apt proxy. """

    proxy: Proxy

    @classmethod
    def setup_class(cls):
        """ Prepare proxy. """
        cls.proxy = Proxy()

    def test_init(self):
        """ Test proxy initalization. """
        assert self.proxy.apts == []
        assert self.proxy.cache is not None

    def test_apt_repos(self):
        """ Test apt repo handling. """
        a = Apt(
            url='ports.ubuntu.com/ubuntu-ports',
            distro='jammy',
            arch=CpuArch.ARM64,
            components=['main', 'universe']
        )
        b = Apt(
            url='https://linux.elektrobit.com/eb-corbos-linux/1.2',
            distro='ebcl',
            arch=CpuArch.ARM64,
            components=['prod', 'dev']
        )

        assert len(self.proxy.apts) == 0

        res = self.proxy.add_apt(Apt())
        assert res
        assert len(self.proxy.apts) == 1

        res = self.proxy.add_apt(Apt())
        assert not res
        assert len(self.proxy.apts) == 1

        res = self.proxy.add_apt(a)
        assert res
        assert len(self.proxy.apts) == 2

        res = self.proxy.add_apt(b)
        assert res
        assert len(self.proxy.apts) == 3

        res = self.proxy.remove_apt(a)
        assert res
        assert len(self.proxy.apts) == 2

        res = self.proxy.remove_apt(a)
        assert not res
        assert len(self.proxy.apts) == 2

    def test_find_package_busybox(self):
        """ Test that busybox-static package is found. """
        self.proxy.add_apt(Apt())

        vds = parse_depends('busybox-static', CpuArch.AMD64)
        assert vds
        p = self.proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64

        a = Apt(
            url='http://ports.ubuntu.com/ubuntu-ports',
            distro='jammy',
            arch=CpuArch.ARM64,
            components=['main', 'universe']
        )

        self.proxy.add_apt(a)

        vds = parse_depends('busybox-static', CpuArch.ARM64)
        assert vds
        p = self.proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.ARM64

    def test_find_linux_image_generic(self):
        """ Test that busybox-static package is found. """
        self.proxy.add_apt(Apt())

        vds = parse_depends('linux-image-generic', CpuArch.AMD64)
        assert vds
        p = self.proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'linux-image-generic'
        assert p.arch == CpuArch.AMD64
        assert p.depends

    def test_find_bootstrap_package(self):
        """ Test that bootstrap-root-ubuntu-jammy package is found. """
        self.proxy.add_apt(Apt.ebcl_apt(CpuArch.AMD64, '1.2'))

        vds = parse_depends('bootstrap-root-ubuntu-jammy', CpuArch.AMD64)
        assert vds
        p = self.proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'bootstrap-root-ubuntu-jammy'
        assert p.arch == CpuArch.AMD64

        self.proxy.add_apt(Apt.ebcl_apt(CpuArch.ARM64, '1.2'))

        vds = parse_depends('bootstrap-root-ubuntu-jammy', CpuArch.ARM64)
        assert vds
        p = self.proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'bootstrap-root-ubuntu-jammy'
        assert p.arch == CpuArch.ARM64

    def test_find_not_existing(self):
        """ Test that tries to find a non-existing package. """
        vds = parse_depends('some-not-existing-package', CpuArch.AMD64)
        assert vds
        p = self.proxy.find_package(vds[0])
        assert p is None

    @pytest.mark.requires_download
    def test_download_and_extract_linux_image(self):
        """ Extract data content of multiple debs. """
        self.proxy.add_apt(Apt())

        kernel_package = 'linux-image-generic'

        vds = parse_depends(kernel_package, CpuArch.AMD64)
        assert vds
        (debs, content, missing) = self.proxy.download_deb_packages(vds)

        assert not missing

        deb_path = Path(debs)
        packages = list(deb_path.glob('*.deb'))

        assert len(packages) > 0

        assert content
        content_path = Path(content)
        boot = content_path / 'boot'
        kernel_images = list(boot.glob('vmlinuz*'))

        assert len(kernel_images) > 0
