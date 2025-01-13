""" Unit tests for the EBcL apt proxy. """
from pathlib import Path

import pytest

from ebcl.common.apt import Apt, AptDebRepo
from ebcl.common.proxy import Proxy

from ebcl.common.types.cpu_arch import CpuArch
from ebcl.common.version import parse_depends


class TestProxy:
    """ Unit tests for the EBcL apt proxy. """

    @property
    def ubuntu_jammy_repo(self) -> AptDebRepo:
        return AptDebRepo(
            url='http://archive.ubuntu.com/ubuntu',
            dist='jammy',
            components=['main'],
            arch=CpuArch.AMD64
        )

    def test_init(self) -> None:
        """ Test proxy initalization. """
        proxy = Proxy()
        assert proxy.apts == []
        assert proxy.cache is not None

    def test_apt_repos(self) -> None:
        """ Test apt repo handling. """
        proxy = Proxy()
        a = Apt(
            AptDebRepo(
                url='ports.ubuntu.com/ubuntu-ports',
                dist='jammy',
                arch=CpuArch.ARM64,
                components=['main', 'universe']
            )
        )
        b = Apt(
            AptDebRepo(
                url='https://linux.elektrobit.com/eb-corbos-linux/1.2',
                dist='ebcl',
                arch=CpuArch.ARM64,
                components=['prod', 'dev']
            )
        )

        assert len(proxy.apts) == 0

        res = proxy.add_apt(Apt(self.ubuntu_jammy_repo))
        assert res
        assert len(proxy.apts) == 1

        res = proxy.add_apt(Apt(self.ubuntu_jammy_repo))
        assert not res
        assert len(proxy.apts) == 1

        res = proxy.add_apt(a)
        assert res
        assert len(proxy.apts) == 2

        res = proxy.add_apt(b)
        assert res
        assert len(proxy.apts) == 3

        res = proxy.remove_apt(a)
        assert res
        assert len(proxy.apts) == 2

        res = proxy.remove_apt(a)
        assert not res
        assert len(proxy.apts) == 2

    def test_find_package_busybox(self) -> None:
        """ Test that busybox-static package is found. """
        proxy = Proxy([Apt(self.ubuntu_jammy_repo)])

        vds = parse_depends('busybox-static', CpuArch.AMD64)
        assert vds
        p = proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64

        a = Apt(
            AptDebRepo(
                url='http://ports.ubuntu.com/ubuntu-ports',
                dist='jammy',
                arch=CpuArch.ARM64,
                components=['main', 'universe']
            )
        )

        proxy.add_apt(a)

        vds = parse_depends('busybox-static', CpuArch.ARM64)
        assert vds
        p = proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.ARM64

    def test_find_linux_image_generic(self) -> None:
        proxy = Proxy([Apt(self.ubuntu_jammy_repo)])

        vds = parse_depends('linux-image-generic', CpuArch.AMD64)
        assert vds
        p = proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'linux-image-generic'
        assert p.arch == CpuArch.AMD64
        assert p.depends

    def test_find_bootstrap_package(self) -> None:
        """ Test that bootstrap-root-ubuntu-jammy package is found. """
        proxy = Proxy([Apt.ebcl_apt(CpuArch.AMD64, '1.4')])

        vds = parse_depends('bootstrap-root-ubuntu-jammy', CpuArch.AMD64)
        assert vds
        p = proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'bootstrap-root-ubuntu-jammy'
        assert p.arch == CpuArch.AMD64

        proxy = Proxy([Apt.ebcl_apt(CpuArch.ARM64, '1.4')])

        vds = parse_depends('bootstrap-root-ubuntu-jammy', CpuArch.ARM64)
        assert vds
        p = proxy.find_package(vds[0])
        assert p is not None
        assert p.name == 'bootstrap-root-ubuntu-jammy'
        assert p.arch == CpuArch.ARM64

    def test_find_not_existing(self) -> None:
        """ Test that tries to find a non-existing package. """
        vds = parse_depends('some-not-existing-package', CpuArch.AMD64)
        assert vds
        p = Proxy().find_package(vds[0])
        assert p is None

    @pytest.mark.requires_download
    def test_download_and_extract_linux_image(self) -> None:
        """ Extract data content of multiple debs. """
        proxy = Proxy([Apt(self.ubuntu_jammy_repo)])

        vds = parse_depends('linux-image-generic', CpuArch.AMD64)
        assert vds
        (debs, content, missing) = proxy.download_deb_packages(vds)

        assert not missing

        deb_path = Path(debs)
        packages = list(deb_path.glob('*.deb'))

        assert len(packages) > 0

        assert content
        content_path = Path(content)
        boot = content_path / 'boot'
        kernel_images = list(boot.glob('vmlinuz*'))

        assert len(kernel_images) > 0
