""" APT helper functions """
import glob
import gzip
import logging
import lzma
import os
import tempfile
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from pathlib import Path
from types import NotImplementedType
from typing import Any, overload
from urllib.parse import urlparse

import requests
from typing_extensions import Self

from . import get_cache_folder
from .deb import Package
from .deb_metadata import DebPackagesInfo, DebReleaseInfo
from .fake import Fake
from .types.cpu_arch import CpuArch


class AptCache:
    """
    Cache for the Apt and AptRepo classes
    """
    _cache_dir: Path
    _max_age: int

    def __init__(self, cache_dir: Path, max_age: int = 24 * 60 * 60) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._max_age = max_age

    def _get_cache_path(self, url: str) -> Path:
        return self._cache_dir / urlparse(url).path.replace('/', '_')

    def _get_local(self, path: Path) -> bytes:
        with path.open("rb") as f:
            return f.read()

    def _get_from_cache(self, url: str) -> bytes | None:
        cache_file_path = self._get_cache_path(url)
        cache_files = glob.glob(f'{cache_file_path}_*')
        if cache_files:
            cache_files.sort()
            cache_file = cache_files[-1]

            logging.debug('Cache file found for %s: %s', url, cache_file)

            ts_str = cache_file.split('_')[-1]
            ts = float(ts_str)
            age = time.time() - ts

            if age > self._max_age:
                # older than max age
                logging.debug('Removing outdated cache file %s', cache_file)
                try:
                    os.remove(cache_file)
                except Exception as e:
                    logging.error(
                        'Removing old cache file %s failed! %s', cache_file, e)
            else:
                # Read cached data
                logging.debug('Reading cached data from %s...', cache_file)
                try:
                    return self._get_local(Path(cache_file))
                except Exception as e:
                    logging.error(
                        'Reading cached data from %s failed! %s', cache_file, e)
        else:
            logging.info('No cache file found for %s', url)
        return None

    def _download(self, url: str) -> bytes | None:
        try:
            result = requests.get(url, allow_redirects=True, timeout=10, stream=True)
        except Exception as e:
            logging.error('Downloading %s failed! %s', url, e)
            return None

        if result.status_code != requests.codes.ok:
            return None

        cache_file = f'{self._get_cache_path(url)}_{time.time()}'

        file_bytes: list[bytes] = []
        with open(cache_file, 'wb') as f:
            for chunk in result.iter_content(chunk_size=512 * 1024):
                file_bytes.append(chunk)
                f.write(chunk)
        return b''.join(file_bytes)

    @overload
    def get(self, url: str, encoding: None = None) -> bytes | None:
        ...

    @overload
    def get(self, url: str, encoding: str) -> str | None:
        ...

    def get(self, url: str, encoding: str | None = None) -> str | bytes | None:
        """
        Download the given url or get it from the cache.

        If encoding is specified the content will be returned as str, otherwise bytes
        """

        data: str | bytes | None = None
        parsed_url = urlparse(url)
        if parsed_url.scheme == "file":
            data = self._get_local(Path(parsed_url.path))
        else:
            data = self._get_from_cache(url)
            if not data:
                data = self._download(url)

        if data and encoding:
            data = data.decode(encoding, errors="ignore")
        return data


class AptRepo(ABC):
    """Base class for repository description."""

    PACKAGES_FILES = ['Packages.xz', 'Packages.gz']

    _url: str
    _arch: CpuArch
    _packages: dict[str, list[Package]]

    def __init__(self, url: str, arch: CpuArch) -> None:
        self._url = url
        self._arch = arch
        self._packages = defaultdict(list)

    @property
    @abstractmethod
    def _meta_path(self) -> str:
        """Returns the path/url to the directory where the metadata files (InRelease) are located."""
        raise NotImplementedError()

    @property
    def id(self) -> str:
        """Returns a string that uniquely identified this repository."""
        return f'{self._url}_{self._get_id()}'

    @abstractmethod
    def sources_list_deb_entry(self, trusted: bool = False) -> str:
        """Returns a string that can be used to define the repo in an apt sources list file."""
        raise NotImplementedError()

    @property
    def url(self) -> str:
        return self._url

    @property
    def arch(self) -> CpuArch:
        return self._arch

    @property
    def packages(self) -> dict[str, list[Package]]:
        return self._packages

    @property
    def loaded(self) -> bool:
        return bool(self._packages)

    def __repr__(self) -> str:
        return f"AptDebRepo<url: {self.url}, {self._get_repr()}>"

    def __str__(self) -> str:
        return repr(self)

    def __eq__(self, other) -> bool | NotImplementedType:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return self._arch == other._arch and self._url == other._url and self._is_eq(other)

    def load_index(self, cache: AptCache) -> None:
        """Load the packages index from the repository."""
        release_file = cache.get(f"{self._url}/{self._meta_path}/InRelease", encoding="utf-8")
        if release_file:
            self._parse_release_file(cache, DebReleaseInfo(release_file))

    def _apt_source_parameters(self, trusted: bool = False):
        """ Returns the parameters for the apt sources.list entry. """
        if trusted:
            return f'[arch={self.arch} trusted=yes]'
        else:
            return f'[arch={self.arch}]'

    @abstractmethod
    def _get_id(self) -> str:
        """Returns the repo id part speciifc for the derived repository type."""
        raise NotImplementedError()

    @abstractmethod
    def _get_repr(self) -> str:
        raise NotImplementedError()

    @abstractmethod
    def _is_eq(self, other: Self) -> bool:
        raise NotImplementedError()

    @abstractmethod
    def _parse_release_file(self, cache: AptCache, releaseInfo: DebReleaseInfo) -> None:
        """
        Parses the release file for the derived repository.

        The implementation should call _parse_packages for every Packages file.
        """
        raise NotImplementedError()

    def _parse_packages(self, cache: AptCache, path: str) -> None:
        """Parse a single Packages file"""
        data: bytes | None = cache.get(f"{self._url}/{self._meta_path}/{path}")
        if not data:
            logging.error("Unable to fetch %s (%s)", path, self)
            return

        if path.endswith('.xz'):
            data = lzma.decompress(data)
        elif path.endswith('.gz'):
            data = gzip.decompress(data)
        else:
            logging.error('Unknown compression of index %s (%s)! Cannot parse index.', path, self)
            return
        content = data.decode(encoding="utf-8", errors="ignore")
        packages_info = DebPackagesInfo(content)
        for package in packages_info.packages:
            package.repo = self.id
            package.file_url = f"{self._url}/{package.file_url}"
            self._packages[package.name].append(package)


class AptFlatRepo(AptRepo):
    """
    Implementation of a flat apt repo.

    A flat repo has no disttribution folder.
    Se: https://wiki.debian.org/DebianRepository/Format#Flat_Repository_Format
    """
    _directory: str

    def __init__(
        self,
        url: str,
        directory: str,
        arch: CpuArch
    ) -> None:
        super().__init__(url, arch)
        self._directory = directory

    @property
    def _meta_path(self) -> str:
        return f'{self._directory}'

    def sources_list_deb_entry(self, trusted: bool = False) -> str:
        params = super(AptFlatRepo, self)._apt_source_parameters(trusted)
        return f"deb {params} {self._url} {self._directory}/"

    def _is_eq(self, other: Self) -> bool:
        return self._directory == other._directory

    def _get_id(self) -> str:
        return f'{self._directory}'

    def _get_repr(self) -> str:
        return f"directory: {self._directory}"

    def _parse_release_file(self, cache: AptCache, releaseInfo: DebReleaseInfo) -> None:
        for hash in releaseInfo.hashes.values():
            for file in hash:
                if file[2] in self.PACKAGES_FILES:
                    self._parse_packages(cache, file[2])


class AptDebRepo(AptRepo):
    """
    Implementation of a normal apt repo.

    See: https://wiki.debian.org/DebianRepository/Format#Debian_Repository_Format
    """

    _dist: str
    _components: set[str]

    def __init__(
        self,
        url: str,
        dist: str,
        components: list[str],
        arch: CpuArch
    ) -> None:
        super().__init__(url, arch)
        self._dist = dist
        self._components = set(components)

    @property
    def _meta_path(self) -> str:
        return f'dists/{self._dist}'

    def sources_list_deb_entry(self, trusted: bool = False) -> str:
        params = super(AptDebRepo, self)._apt_source_parameters(trusted)
        return f"deb {params} {self._url} {self._dist} {' '.join(self._components)}"

    @property
    def dist(self) -> str:
        return self._dist

    @property
    def components(self) -> set[str]:
        return self._components

    def _get_id(self) -> str:
        return f'{self._dist}_{"_".join(self._components)}'

    def _get_repr(self) -> str:
        return f"dist: {self._dist}, components: {' '.join(self._components)}"

    def _is_eq(self, other: Self) -> bool:
        return self._dist == other._dist \
            and self._components == other._components

    def _find_package_file(self, releaseInfo: DebReleaseInfo, component: str) -> str | None:
        name = [
            f'{component}/binary-{self._arch}/{p}'
            for p in self.PACKAGES_FILES
        ]
        for hash in releaseInfo.hashes.values():
            for file in hash:
                if file[2] in name:
                    return file[2]
        return None

    def _parse_release_file(self, cache: AptCache, releaseInfo: DebReleaseInfo) -> None:
        for component in self._components:
            if component not in releaseInfo.components:
                logging.warning('No package index for component %s found!', component)
                continue
            package_file = self._find_package_file(releaseInfo, component)
            if not package_file:
                logging.warning('No package index for component %s found!', component)
            else:
                self._parse_packages(cache, package_file)


class Apt:
    """Get packages from apt repositories."""

    _repo: AptRepo
    _cache: AptCache

    @classmethod
    def from_config(cls, repo_config: dict[str, Any], arch: CpuArch) -> None | Self:
        """
        Get an apt repositry for a config entry.

        Two formats are supported:
         1. normal apt repo:
            This must contain a distro key and can contain compoonents
         2. flat apt repo:
            This must contain a directory key
        """
        if 'apt_repo' not in repo_config:
            return None

        repo: AptRepo
        if 'distro' in repo_config:
            repo = AptDebRepo(
                url=repo_config['apt_repo'],
                dist=repo_config['distro'],
                components=repo_config.get('components', 'main'),
                arch=arch
            )
        elif 'directory' in repo_config:
            repo = AptFlatRepo(
                url=repo_config['apt_repo'],
                directory=repo_config['directory'],
                arch=arch
            )
        else:
            return None

        return cls(
            repo=repo,
            key_url=repo_config.get('key', None),
            key_gpg=repo_config.get('gpg', None)
        )

    def __init__(
        self,
        repo: AptRepo,
        key_url: str | None = None,
        key_gpg: str | None = None,
        state_folder: str | None = None
    ) -> None:
        self._repo = repo
        self._cache = AptCache(Path(state_folder and state_folder or get_cache_folder("apt")))

        self.key_url: str | None = key_url
        self.key_gpg: str | None = key_gpg

        if not key_gpg and 'ubuntu.com/ubuntu' in self._repo.url:
            self.key_gpg = '/etc/apt/trusted.gpg.d/ubuntu-keyring-2018-archive.gpg'
            logging.info('Using default Ubuntu key %s for %s.',
                         self.key_gpg, self._repo.url)

    def __eq__(self, value: object) -> bool:
        if not isinstance(value, Apt):
            return False

        return self._repo == value._repo

    @property
    def id(self) -> str:
        """Get a unique identifier for this repo."""
        return self._repo.id

    @property
    def arch(self) -> CpuArch:
        return self._repo.arch

    @property
    def deb_repo(self) -> AptDebRepo | None:
        """Return a normal Debian repo or None if this is a flat repo."""
        return isinstance(self._repo, AptDebRepo) and self._repo or None

    @property
    def repo(self) -> AptRepo:
        return self._repo

    def load_packages(self) -> None:
        """Download repo metadata and parse package indices."""
        if self._repo.loaded:
            return
        self._repo.load_index(self._cache)

        logging.info('Repo %s provides %s packages.', self._repo, len(self._repo.packages))

    def find_package(self, package_name: str) -> list[Package] | None:
        """Find a binary deb package."""
        self._load_packages()

        return self._repo.packages.get(package_name, None)

    def __str__(self) -> str:
        return f'Apt<{self._repo}, key: {self.key_url}, gpg: {self.key_gpg}>'

    def __repr__(self) -> str:
        return self.__str__()

    def get_key(self) -> str | None:
        """Get key for this repo."""
        if not self.key_url:
            return None

        key_url = self.key_url
        if key_url.startswith('file://'):
            key_url = key_url[7:]

        contents = None

        if os.path.isfile(key_url):
            # handle local file
            logging.info('Reading key for %s from %s', self, key_url)
            with open(key_url, encoding='utf8') as f:
                contents = f.read()
        elif key_url.startswith('http://') or key_url.startswith('https://'):
            # download key
            logging.info('Downloading key for %s from %s', self, key_url)
            data = self._cache.get(key_url)
            if data:
                contents = data.decode(encoding='utf8', errors='ignore')
            else:
                logging.error(
                    'Download of key %s for %s failed!', key_url, self)
        else:
            logging.error(
                'Unknown key url %s, cannot download key!', self.key_url)
            return None

        return contents

    def get_key_files(self, output_folder: str | None = None) -> tuple[str | None, str | None]:
        """Get gpg key file for repo key."""
        if not self.key_url:
            return (None, self.key_gpg)

        contents = self.get_key()
        if not contents:
            return (None, self.key_gpg)

        key_pub_file = tempfile.mktemp(suffix=".pub", dir=output_folder)
        key_gpg_file = tempfile.mktemp(suffix=".gpg", dir=output_folder)

        try:
            with open(key_pub_file, 'w', encoding='utf8') as f:
                f.write(contents)
        except Exception as e:
            logging.error('Writing pub key of %s to %s failed! %s', self, key_pub_file, e)
            return (None, self.key_gpg)

        if not self.key_gpg:
            fake = Fake()
            try:
                fake.run_cmd(f'cat {key_pub_file} | gpg --dearmor > {key_gpg_file}')
            except Exception as e:
                logging.error('Dearmoring key %s of %s as %s failed! %s',
                              key_pub_file, self, key_gpg_file, e)
                return (key_pub_file, None)
        else:
            key_gpg_file = self.key_gpg

        return (key_pub_file, key_gpg_file)
