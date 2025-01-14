""" Tests for the eb functions. """
import os
import tempfile

from pathlib import Path

from ebcl.common.apt import Apt, AptDebRepo
from ebcl.common.fake import Fake
from ebcl.common.proxy import Proxy
from ebcl.common.version import parse_depends

from ebcl.common.types.cpu_arch import CpuArch


class TestDeb:
    """ Tests for the deb functions. """

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

    def test_download_and_extract_busybox(self):
        """ Extract data content of deb. """
        ps = self.apt.find_package('busybox-static')
        assert ps

        ps.sort()
        p = ps[-1]

        d = tempfile.mkdtemp()

        pkg = self.proxy.download_package(CpuArch.AMD64, p)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

        location = pkg.extract(d)
        assert location
        assert location == d

        location = pkg.extract(None)
        assert location is not None
        assert os.path.isdir(os.path.join(location))
        assert os.path.isfile(os.path.join(
            location, 'bin', 'busybox'))

        fake = Fake()
        fake.run_sudo(f'rm -rf {d}', check=False)

    def test_download_deb_packages(self):
        """ Test download busybox and depends. """
        proxy = Proxy()
        proxy.add_apt(Apt.ebcl_apt(CpuArch.ARM64))
        proxy.add_apt(Apt(
            AptDebRepo(
                url='http://ports.ubuntu.com/ubuntu-ports',
                dist='jammy',
                components=['main', 'universe'],
                arch=CpuArch.ARM64
            )
        ))
        proxy.add_apt(Apt(
            AptDebRepo(
                url='http://ports.ubuntu.com/ubuntu-ports',
                dist='jammy-security',
                components=['main', 'universe'],
                arch=CpuArch.ARM64
            )
        ))

        packages = parse_depends('busybox', CpuArch.ARM64)
        assert packages

        (debs, contents, missing) = proxy.download_deb_packages(
            packages=packages
        )

        assert not missing
        assert os.path.isdir(debs)
        assert contents
        assert os.path.isdir(contents)

        bb = Path(contents) / 'bin' / 'busybox'
        assert bb.is_file()
