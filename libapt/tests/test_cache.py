""" Tests for the cache functions. """
import shutil

from pathlib import Path
from typing import TypeVar

from libapt.cache import Cache
from libapt.deb import DebFile, Package
from libapt.version import PackageRelation, Version, VersionDepends, VersionRelation

from libapt.types.cpu_arch import CpuArch

test_data = Path(__file__).parent / "data"

T = TypeVar("T")


def get_example(arch: CpuArch, version: str) -> Package:
    p = DebFile(test_data / "example_packages" / f"example_{version}_{arch}.deb").to_package()
    assert p
    return p


def not_none(val: T | None) -> T:
    assert val
    return val


class TestCache:
    """ Tests for the cache functions. """

    def test_add(self, tmp_path: Path) -> None:
        """ Add a pacakage. """
        deb = test_data / 'busybox-static_1.36.1-3ubuntu1_amd64.deb'
        assert deb.exists()
        p: Package | None = DebFile(deb).to_package()
        assert p

        cache = Cache(tmp_path)
        res = cache.add(p)
        assert res

        v = Version('1:1.36.1-3ubuntu1')
        p = cache.get(
            CpuArch.AMD64,
            'busybox-static',
            v,
            relation=VersionRelation.EXACT
        )

        assert p
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64
        assert p.version == v

        p = cache.get(
            CpuArch.AMD64,
            'busybox-static',
            Version('anotherversion'),
            VersionRelation.EXACT
        )
        assert not p

    def test_get_no_version(self, tmp_path: Path) -> None:
        """ Get any version of a package. """
        deb = test_data / 'busybox-static_1.36.1-3ubuntu1_amd64.deb'
        assert deb.exists()
        p: Package | None = DebFile(deb).to_package()
        assert p

        cache = Cache(tmp_path)
        res = cache.add(p)
        assert res

        p = cache.get(CpuArch.AMD64, 'busybox-static')
        assert p
        assert p.name == 'busybox-static'
        assert p.arch == CpuArch.AMD64
        assert p.version == Version('1:1.36.1-3ubuntu1')

    def test_get_with_version(self, tmp_path: Path) -> None:
        arm_1_0 = get_example(CpuArch.ARM64, "1.0")
        arm_1_1 = get_example(CpuArch.ARM64, "1.1")
        arm_2_0 = get_example(CpuArch.ARM64, "2.0")

        cache = Cache(tmp_path)
        cache.add(arm_1_0)
        cache.add(arm_2_0)
        cache.add(arm_1_1)

        assert cache.get(CpuArch.ARM64, "example", None, None) == arm_2_0
        assert cache.get(CpuArch.ARM64, "example", Version("1.1"), VersionRelation.EXACT) == arm_1_1
        assert cache.get(CpuArch.ARM64, "example", Version("1.1"), VersionRelation.SMALLER) == arm_1_1
        assert cache.get(CpuArch.ARM64, "example", Version("1.1"), VersionRelation.STRICT_SMALLER) == arm_1_0
        assert cache.get(CpuArch.ARM64, "example", Version("1.0"), VersionRelation.STRICT_SMALLER) is None

        # New cache
        cache.clear()
        # We need new versions, because local_file was rewritten to a path in the cache
        arm_1_0 = get_example(CpuArch.ARM64, "1.0")
        arm_1_1 = get_example(CpuArch.ARM64, "1.1")
        cache.add(arm_1_0)
        cache.add(arm_1_1)
        assert cache.get(CpuArch.ARM64, "example", Version("1.1"), VersionRelation.LARGER) == arm_1_1
        assert cache.get(CpuArch.ARM64, "example", Version("1.1"), VersionRelation.STRICT_LARGER) is None

    def test_cache_miss(self, tmp_path: Path) -> None:
        """ Package does not exist. """
        cache = Cache(tmp_path)
        p = cache.get(
            CpuArch.AMD64,
            'busybox',
            Version('nonversion'),
            VersionRelation.EXACT
        )
        assert p is None

    def test_restore_cache(self, tmp_path: Path) -> None:
        """ Test for restoring cache index. """
        deb = test_data / 'busybox-static_1.36.1-3ubuntu1_amd64.deb'
        assert deb.exists()
        p = DebFile(deb).to_package()
        assert p

        p.breaks = [
            [VersionDepends("breaks1", PackageRelation.BREAKS, None, None, CpuArch.AMD64)],
            [VersionDepends("breaks2", PackageRelation.BREAKS, VersionRelation.EXACT, Version("1.2"), CpuArch.AMD64)]
        ]
        p.conflicts = [
            [VersionDepends("conflicts1", PackageRelation.CONFLICTS, None, None, CpuArch.AMD64)],
        ]
        p.depends = [
            [
                VersionDepends("depends1", PackageRelation.DEPENDS, None, None, CpuArch.AMD64),
                VersionDepends("depends2", PackageRelation.DEPENDS, None, None, CpuArch.AMD64)
            ],
            [VersionDepends("depends3", PackageRelation.DEPENDS, None, None, CpuArch.AMD64)]
        ]
        p.enhances = [
            [VersionDepends("enhances1", PackageRelation.ENHANCES, None, None, CpuArch.AMD64)],
        ]
        p.pre_depends = [
            [VersionDepends("pre_depends1", PackageRelation.PRE_DEPENS, None, None, CpuArch.AMD64)],
        ]
        p.recommends = [
            [VersionDepends("recommends", PackageRelation.RECOMMENDS, None, None, CpuArch.AMD64)],
        ]
        p.suggests = [
            [VersionDepends("suggests", PackageRelation.SUGGESTS, None, None, CpuArch.AMD64)],
        ]

        cache = Cache(tmp_path)
        res = cache.add(p)
        assert res

        # Reload cache
        cache = Cache(tmp_path)
        cached_p = cache.get(
            CpuArch.AMD64,
            'busybox-static',
            Version('1:1.36.1-3ubuntu1')
        )
        assert cached_p
        assert cached_p.name == p.name
        assert cached_p.arch == p.arch
        assert cached_p.version == p.version
        assert cached_p.file_url == p.file_url
        assert cached_p.local_file == p.local_file
        assert list(cached_p.relations) == list(p.relations)

    def test_scan_files(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        assert cache.add(get_example(CpuArch.ARM64, "1.0"))
        assert cache.add(get_example(CpuArch.ARM64, "1.1"))
        assert cache.add(get_example(CpuArch.ALL, "1.0"))
        assert cache.add(get_example(CpuArch.AMD64, "1.0"))
        assert cache.add(get_example(CpuArch.AMD64, "1.1"))
        assert cache.size() == 5

        del cache
        (tmp_path / "index.db").unlink(True)
        (tmp_path / "index.json").unlink(True)
        cache = Cache(tmp_path)
        assert cache.size() == 5

    def test_scan_with_duplicate(self, tmp_path: Path) -> None:
        p = get_example(CpuArch.ARM64, "1.0")
        deb_1_0 = Path(not_none(p.local_file)).stem
        shutil.copy(not_none(get_example(CpuArch.ARM64, "1.1").local_file), tmp_path)
        shutil.copy(not_none(p.local_file), tmp_path)
        shutil.copy(not_none(p.local_file), tmp_path / (deb_1_0 + ".copy.deb"))
        (tmp_path / "invalid.deb").touch()
        assert (tmp_path / (deb_1_0 + ".deb")).exists() and (tmp_path / (deb_1_0 + ".copy.deb")).exists()

        cache = Cache(tmp_path)
        # The cache should delete one of the copies on load
        assert not (tmp_path / (deb_1_0 + ".deb")).exists() or not (tmp_path / (deb_1_0 + ".copy.deb")).exists()
        # Invalid packages are removed as well
        assert not (tmp_path / "invalid.deb").exists()
        assert cache.size() == 2

    def test_add_existing(self, tmp_path: Path) -> None:
        cache = Cache(tmp_path)
        assert cache.size() == 0

        assert cache.add(get_example(CpuArch.ARM64, "1.0"))
        assert cache.size() == 1
        assert cache.add(get_example(CpuArch.ARM64, "1.0"))
        assert cache.size() == 1
