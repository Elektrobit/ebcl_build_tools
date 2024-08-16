""" Tests for the cache functions. """
import os
import shutil
import tempfile

from ebcl.common.cache import Cache
from ebcl.common.deb import Package
from ebcl.common.version import Version, VersionRealtion

from ebcl.common.types.cpu_arch import CpuArch


class TestCache:
    """ Tests for the cache functions. """

    folder: str
    cache: Cache

    @classmethod
    def setup_class(cls):
        """ Prepare cache object. """
        cls.folder = tempfile.mkdtemp()
        cls.cache = Cache(folder=cls.folder)

    @classmethod
    def teardown_class(cls):
        """ Delete cache folder. """
        shutil.rmtree(cls.folder)

    def test_add(self):
        """ Add a pacakage. """
        deb = os.path.join(os.path.dirname(__file__), 'data',
                           'busybox-static_1.36.1-3ubuntu1_amd64.deb')
        assert os.path.isfile(deb)

        res = self.cache.add(Package.from_deb(deb, []))
        assert res

        v = Version('1.36.1-3ubuntu1')
        p = self.cache.get(CpuArch.AMD64, 'busybox-static', v,
                           relation=VersionRealtion.EXACT)
        assert p
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64
        assert p.version == v

        p = self.cache.get(CpuArch.AMD64, 'busybox-static',
                           Version('anotherversion'), VersionRealtion.EXACT)
        assert not p

    def test_get_no_version(self):
        """ Get any version of a package. """
        deb = os.path.join(os.path.dirname(__file__), 'data',
                           'busybox-static_1.36.1-3ubuntu1_amd64.deb')
        assert os.path.isfile(deb)

        res = self.cache.add(Package.from_deb(deb, []))
        assert res

        p = self.cache.get(CpuArch.AMD64, 'busybox-static')
        assert p
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64
        assert p.version == Version('1.36.1-3ubuntu1')

    def test_cache_miss(self):
        """ Package does not exist. """
        p = self.cache.get(CpuArch.AMD64, 'not-existing')
        assert p is None

        p = self.cache.get(CpuArch.AMD64, 'busybox', Version('nonversion'),
                           VersionRealtion.EXACT)
        assert p is None

    def test_restore_cache(self):
        """ Test for restoring cache index. """
        cache_dir = tempfile.mkdtemp()

        cache = Cache(cache_dir)
        deb = os.path.join(os.path.dirname(__file__), 'data',
                           'busybox-static_1.36.1-3ubuntu1_amd64.deb')
        assert os.path.isfile(deb)

        res = cache.add(Package.from_deb(deb, []))
        assert res

        del cache

        cache = Cache(cache_dir)
        p = cache.get(CpuArch.AMD64, 'busybox-static',
                      Version('1.36.1-3ubuntu1'))
        assert p
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64
        assert p.version == Version('1.36.1-3ubuntu1')

        shutil.rmtree(cache_dir)
