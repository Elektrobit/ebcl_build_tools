import itertools
import logging
import os
import subprocess
import tempfile

from pathlib import Path
from typing import Iterable

import unix_ar  # type: ignore

from .deb_metadata import DebPackagesInfo
from .fake import Fake
from .files import Files
from .version import PackageRelation, Version, VersionDepends, VersionRelation

from .types.cpu_arch import CpuArch


class InvalidFile(Exception):
    """Invalid Debian package"""


class Package:
    """ APT package information. """

    name: str
    arch: CpuArch
    repo: str
    version: Version | None
    file_url: str | None
    local_file: str | None

    pre_depends: list[list[VersionDepends]]
    depends: list[list[VersionDepends]]
    breaks: list[list[VersionDepends]]
    conflicts: list[list[VersionDepends]]
    recommends: list[list[VersionDepends]]
    suggests: list[list[VersionDepends]]
    enhances: list[list[VersionDepends]]

    @property
    def relations(self) -> Iterable[list[VersionDepends]]:
        return itertools.chain(
            self.pre_depends,
            self.depends,
            self.breaks,
            self.conflicts,
            self.recommends,
            self.suggests,
            self.enhances
        )

    @relations.setter
    def relations(self, relations: Iterable[list[VersionDepends]]):
        self.pre_depends = []
        self.depends = []
        self.breaks = []
        self.conflicts = []
        self.recommends = []
        self.suggests = []
        self.enhances = []

        for entry in relations:
            if not entry:
                continue

            relation = entry[0].package_relation
            if relation == PackageRelation.PRE_DEPENS:
                self.pre_depends.append(entry)
            elif relation == PackageRelation.DEPENDS:
                self.depends.append(entry)
            elif relation == PackageRelation.BREAKS:
                self.breaks.append(entry)
            elif relation == PackageRelation.CONFLICTS:
                self.conflicts.append(entry)
            elif relation == PackageRelation.RECOMMENDS:
                self.recommends.append(entry)
            elif relation == PackageRelation.SUGGESTS:
                self.suggests.append(entry)
            elif relation == PackageRelation.ENHANCES:
                self.enhances.append(entry)

    def __init__(
        self,
        name: str,
        arch: CpuArch,
        repo: str,
        version: Version | None = None,
        file_url: str | None = None,
        local_file: str | None = None
    ) -> None:
        self.name: str = name
        self.arch: CpuArch = arch
        self.repo: str = repo

        self.version = version
        self.file_url = file_url
        self.local_file = local_file

        self.pre_depends = []
        self.depends = []

        self.breaks = []
        self.conflicts = []

        self.recommends = []
        self.suggests = []
        self.enhances = []

    def set_relation(self, relation: PackageRelation, value: list[list[VersionDepends]]) -> None:
        if relation == PackageRelation.PRE_DEPENS:
            self.pre_depends = value
        elif relation == PackageRelation.DEPENDS:
            self.depends = value
        elif relation == PackageRelation.BREAKS:
            self.breaks = value
        elif relation == PackageRelation.CONFLICTS:
            self.conflicts = value
        elif relation == PackageRelation.RECOMMENDS:
            self.recommends = value
        elif relation == PackageRelation.SUGGESTS:
            self.suggests = value
        elif relation == PackageRelation.ENHANCES:
            self.enhances = value

    def get_depends(self) -> list[list[VersionDepends]]:
        """ Get dependencies. """
        return self.depends + self.pre_depends

    def extract(
        self,
        location: str | None = None,
        files: Files | None = None,
        use_sudo: bool = True
    ) -> str | None:
        """ Extract a deb archive. """
        if not self.local_file:
            return None

        if not os.path.isfile(self.local_file):
            logging.error('Deb %s of package %s does not exist!',
                          self.local_file, self)
            return None

        if location is None:
            location = tempfile.mkdtemp()

        deb_content_location = tempfile.mkdtemp()

        # extract deb
        logging.debug('Extracting deb content of %s to %s.',
                      self.local_file, deb_content_location)
        try:
            file = unix_ar.open(self.local_file)
            logging.debug('ar-file: %s', file)
            file.extractall(deb_content_location)
        except Exception as e:
            logging.error('Extraction of deb %s (%s) failed! %s',
                          self.local_file, self.name, e)
            return None

        # TODO: Pure Python implementation not relying on host tools.
        # find data.tar
        data_tar = Path(deb_content_location) / 'data.tar'
        if data_tar.exists():
            tar_files = [data_tar]
        else:  # find compressed data.tar
            tar_files = list(Path(deb_content_location).glob('data.tar.*'))

        if not tar_files:
            logging.error('No tar content found in package %s!', self)
            return None

        logging.debug('Tar-Files: %s', tar_files)

        if not files:
            fake = Fake()
            files = Files(fake, location)

        for tar_file in tar_files:
            logging.debug('Processing tar file %s...', tar_file)

            logging.debug('Extracting data content of %s to %s.',
                          tar_file.absolute(), location)

            files.extract_tarball(str(tar_file.absolute()),
                                  location, use_sudo=use_sudo)

        files.fake.run_cmd(f'rm -rf {deb_content_location}', check=False)

        return location

    def __str__(self) -> str:
        return f'{self.name}:{self.arch} ({self.version})'

    def __repr__(self) -> str:
        return f'Package<{self.__str__()}>'

    def __eq__(self, o: object) -> bool:
        if not isinstance(o, Package):
            return False

        return self.arch == o.arch and \
            self.name == o.name and \
            self.version == o.version

    def __lt__(self, o: object) -> bool:
        if not isinstance(o, Package):
            return False

        if self.name != o.name:
            return self.name < o.name

        # Use package with existing local file.
        if self.version is None and o.version is None:
            if self.local_file and os.path.isfile(self.local_file):
                return False
            return True

        if self.version is None:
            return True
        if o.version is None:
            return False

        if self.version == o.version:
            # Use package with existing local file.
            if self.version is None and o.version is None:
                if self.local_file and os.path.isfile(self.local_file):
                    return False
                return True

        return self.version < o.version

    def __le__(self, o: object) -> bool:
        if not isinstance(o, Package):
            return False

        if self == o:
            return True

        return self < o


class DebFile:
    """ Binary package file handling utilities """
    _file: Path
    _package: Package | None

    def __init__(self, fileOrPackage: Path | Package) -> None:
        """
        Instantiate the class with either a path to a Debian package
        or a Package instance with a local_file path
        """
        if isinstance(fileOrPackage, Package):
            self._package = fileOrPackage
            if not fileOrPackage.local_file:
                raise InvalidFile("Cannot create a DebFile from a Package without a local_file")
            self._file = Path(fileOrPackage.local_file)
        else:
            self._file = fileOrPackage
            self._package = None

    def to_package(self) -> Package:
        """ Get a package instance for the binary file"""
        if self._package:
            return self._package
        # TODO: Pure Python implementation not relying on host tools.
        res = subprocess.run(
            [
                "dpkg-deb",
                "--info",
                str(self._file),
                "control"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            encoding="utf-8"
        )
        package = next(iter(DebPackagesInfo(res.stdout).packages), None)
        if res.returncode != 0 or not package:
            raise InvalidFile("%s is not a valid Debian file", self._file)
        package.local_file = str(self._file)
        self._package = package
        return package


def filter_packages(p: Package, v: Version, r: VersionRelation | None) -> bool:
    """ Filter for matching packages. """
    # TODO: test
    if not p.version:
        return False

    pv = p.version

    if r == VersionRelation.STRICT_LARGER:
        return pv > v
    elif r == VersionRelation.LARGER:
        return pv >= v
    elif r == VersionRelation.EXACT:
        return pv == v
    elif r == VersionRelation.SMALLER:
        return pv <= v
    elif r == VersionRelation.STRICT_SMALLER:
        return pv < v

    return False
