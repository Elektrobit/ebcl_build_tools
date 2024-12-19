""" Tests for the apt functions. """
import os

import pytest

from ebcl.common.apt import Apt, parse_depends
from ebcl.common.proxy import Proxy
from ebcl.common.version import Version, VersionRelation

from ebcl.common.types.cpu_arch import CpuArch


class TestApt:
    """ Tests for the apt functions. """

    apt: Apt
    proxy: Proxy

    @classmethod
    def setup_class(cls):
        """ Prepare apt repo object. """
        cls.apt = Apt()
        cls.proxy = Proxy()
        cls.proxy.add_apt(cls.apt)

    def test_find_busybox_default(self):
        """ Search busybox package in default apt repository. """
        p = self.apt.find_package('busybox-static')
        assert p is not None
        assert len(p) == 1
        assert p[0].name == 'busybox-static'
        assert p[0].file_url is not None

    def test_download_busybox(self):
        """ Search busybox package in default apt repository. """
        p = self.apt.find_package('busybox-static')
        assert p

        pkg = self.proxy.download_package(self.apt.arch, p[0])
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

    def test_ebcl_apt(self):
        """ Test that EBcL apt repo works and provides busybox-static. """
        apt = Apt(
            url='https://linux.elektrobit.com/eb-corbos-linux/1.2',
            distro='ebcl',
            components=['prod', 'dev'],
            arch=CpuArch.ARM64
        )

        p = apt.find_package('busybox-static')
        assert p
        assert p[0].name == 'busybox-static'
        assert p[0].file_url is not None

    def test_find_linux_image_generic(self):
        """ Search busybox package in default apt repository. """
        p = self.apt.find_package('linux-image-generic')
        assert p
        assert p[0].name == 'linux-image-generic'
        assert p[0].file_url is not None
        assert p[0].depends is not None

        deps = p[0].get_depends()
        assert deps is not []

    def test_equal(self):
        """ Test the equal check. """
        a = Apt(
            url='http://archive.ubuntu.com/ubuntu',
            distro='jammy',
            arch=CpuArch.AMD64,
            components=['main', 'universe']
        )

        b = Apt(
            url='http://archive.ubuntu.com/ubuntu',
            distro='jammy',
            arch=CpuArch.AMD64,
            components=['main', 'universe']
        )
        assert a == b

        b = Apt(
            url='http://ports.ubuntu.com/ubuntu-ports',
            distro='jammy',
            arch=CpuArch.AMD64,
            components=['main', 'universe']
        )
        assert a != b

        b = Apt(
            url='http://archive.ubuntu.com/ubuntu',
            distro='jammy',
            arch=CpuArch.AMD64,
            components=['main']
        )
        assert a != b

        b = Apt(
            url='http://archive.ubuntu.com/ubuntu',
            distro='jammy',
            arch=CpuArch.AMD64,
            components=['main', 'other']
        )
        assert a != b

        b = Apt(
            url='http://archive.ubuntu.com/ubuntu',
            distro='noble',
            arch=CpuArch.AMD64,
            components=['main', 'universe']
        )
        assert a != b

        b = Apt(
            url='http://archive.ubuntu.com/ubuntu',
            distro='jammy',
            arch=CpuArch.ARM64,
            components=['main', 'universe']
        )
        assert a != b

    def test_perl(self):
        """ Test package name with any suffix. """
        d = parse_depends('perl:any', CpuArch.AMD64)
        assert d
        assert len(d) == 1
        assert d[0].name == 'perl'
        assert d[0].version is None
        assert d[0].arch == CpuArch.ANY

    def test_parse_depends(self):
        """ Test of the parse_depends function. """
        vds = parse_depends('init-system-helpers (>= 1.54~)', CpuArch.AMD64)
        assert vds
        assert len(vds) == 1
        assert vds[0].name == 'init-system-helpers'
        assert vds[0].version == Version('1.54~')
        assert vds[0].version_relation == VersionRelation.LARGER
        assert vds[0].package_relation is None

        vds = parse_depends(
            'libaprutil1-dbd-sqlite3 | libaprutil1-dbd-mysql '
            '| libaprutil1-dbd-odbc | libaprutil1-dbd-pgsql', CpuArch.AMD64)
        assert vds
        assert len(vds) == 4
        assert vds[0].name == 'libaprutil1-dbd-sqlite3'
        assert vds[0].version is None
        assert vds[1].name == 'libaprutil1-dbd-mysql'
        assert vds[1].version is None
        assert vds[2].name == 'libaprutil1-dbd-odbc'
        assert vds[2].version is None
        assert vds[3].name == 'libaprutil1-dbd-pgsql'
        assert vds[3].version is None

        vds = parse_depends(
            'libnghttp2-14 (>> 1.50.0) | libpcre2-8-0 (<= 10.22)', CpuArch.AMD64)
        assert vds
        assert len(vds) == 2
        assert vds[0].name == 'libnghttp2-14'
        assert vds[0].version == Version('1.50.0')
        assert vds[0].version_relation == VersionRelation.STRICT_LARGER
        assert vds[1].name == 'libpcre2-8-0'
        assert vds[1].version == Version('10.22')
        assert vds[1].version_relation == VersionRelation.SMALLER

        vds = parse_depends(
            'libnghttp2-14 | libpcre2-8-0 (<< 10.22)', CpuArch.AMD64)
        assert vds
        assert len(vds) == 2
        assert vds[0].name == 'libnghttp2-14'
        assert vds[0].version is None
        assert vds[0].version_relation is None
        assert vds[1].name == 'libpcre2-8-0'
        assert vds[1].version == Version('10.22')
        assert vds[1].version_relation == VersionRelation.STRICT_SMALLER

        vds = parse_depends(
            'libnghttp2-14 (= 1.50.0) | libpcre2-8-0 (10.22)', CpuArch.AMD64)
        assert vds
        assert len(vds) == 2
        assert vds[0].name == 'libnghttp2-14'
        assert vds[0].version == Version('1.50.0')
        assert vds[0].version_relation == VersionRelation.EXACT
        assert vds[1].name == 'libpcre2-8-0'
        assert vds[1].version == Version('10.22')
        assert vds[1].version_relation == VersionRelation.EXACT

    @pytest.mark.requires_download
    def test_flat_repo(self):
        """ Test for OBS flat apt repository parsing. """
        repo_url = 'https://download.opensuse.org/repositories/home:/ivaradi:/alpha/Debian_12/'
        repo_key_url = 'https://download.opensuse.org/repositories/home:/ivaradi:/alpha/Debian_12/Release.key'
        package_name = 'dolphin-nextcloud'

        apt = Apt(
            url=repo_url,
            key_url=repo_key_url
        )

        packages = apt.find_package(package_name)
        assert packages
        assert len(packages) == 1
        assert packages[0].name == package_name
