""" Tests for the apt functions. """
import os

from pathlib import Path

from libapt.apt import Apt, AptDebRepo, AptFlatRepo
from libapt.proxy import Proxy
from libapt.version import Version, VersionRelation, parse_depends

from libapt.types.cpu_arch import CpuArch


test_data = Path(__file__).parent / "data"


class TestApt:
    """ Tests for the apt functions. """

    apt: Apt
    proxy: Proxy

    @classmethod
    def setup_class(cls):
        """ Prepare apt repo object. """
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

    def test_find_busybox_default(self):
        """ Search busybox package in default apt repository. """
        p = self.apt.find_package('busybox-static')
        assert p is not None
        assert len(p) == 1
        assert p[0].name == 'busybox-static'
        assert p[0].file_url is not None

    def test_trusted_repo(self):
        """ Test that repo is trusted. """
        apt = AptDebRepo(
            url='http://localhost',
            dist='local',
            components=['main'],
            arch=CpuArch.AMD64
        )

        deb = apt.sources_entry(trusted=True)
        assert 'trusted=yes' in deb

        apt_flat = AptFlatRepo(
            url='http://localhost',
            directory='',
            arch=CpuArch.AMD64
        )

        deb = apt_flat.sources_entry(trusted=True)
        assert 'trusted=yes' in deb

    def test_repo_arch(self):
        """ Test that repo provides arch parameter. """
        apt = AptDebRepo(
            url='http://localhost',
            dist='local',
            components=['main'],
            arch=CpuArch.AMD64
        )

        deb = apt.sources_entry(trusted=True)
        assert 'arch=amd64' in deb

        apt_flat = AptFlatRepo(
            url='http://localhost',
            directory='',
            arch=CpuArch.ARM64
        )

        deb = apt_flat.sources_entry(trusted=True)
        assert 'arch=arm64' in deb

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
            AptDebRepo(
                url='https://linux.elektrobit.com/eb-corbos-linux/1.2',
                dist='ebcl',
                components=['prod', 'dev'],
                arch=CpuArch.ARM64
            )
        )

        p = apt.find_package('busybox-static')
        assert p
        assert p[0].name == 'busybox-static'
        assert p[0].file_url is not None

    def test_flat_apt(self):
        apt = Apt(
            AptFlatRepo(
                url='file://' + (test_data / "flat_repo").as_posix(),
                directory=".",
                arch=CpuArch.AMD64
            )
        )
        p = apt.find_package('busybox-static')
        assert p
        assert p[0].name == 'busybox-static'
        assert p[0].file_url is not None

        pkg = self.proxy.download_package(self.apt.arch, p[0])
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

    def test_local_file_download(self, tmp_path: Path):
        apt = Apt(
            AptFlatRepo(
                url='file://' + (test_data / "flat_repo").as_posix(),
                directory=".",
                arch=CpuArch.AMD64
            )
        )
        p = apt.find_package('busybox-static')
        assert p
        assert p[0].name == 'busybox-static'
        assert p[0].file_url is not None

        pkg = self.proxy.download_package(self.apt.arch, p[0], location=tmp_path.as_posix())
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)
        assert (tmp_path / Path(pkg.local_file).name).exists()

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
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                arch=CpuArch.AMD64,
                components=['main', 'universe']
            )
        )

        b = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                arch=CpuArch.AMD64,
                components=['main', 'universe']
            )
        )
        assert a == b

        b = Apt(
            AptDebRepo(
                url='http://ports.ubuntu.com/ubuntu-ports',
                dist='jammy',
                arch=CpuArch.AMD64,
                components=['main', 'universe']
            )
        )
        assert a != b

        b = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                arch=CpuArch.AMD64,
                components=['main']
            )
        )
        assert a != b

        b = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                arch=CpuArch.AMD64,
                components=['main', 'other']
            )
        )
        assert a != b

        b = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='noble',
                arch=CpuArch.AMD64,
                components=['main', 'universe']
            )
        )
        assert a != b

        b = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                arch=CpuArch.ARM64,
                components=['main', 'universe']
            )
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
