""" Deb helper funktions. """
import logging
import os
import tempfile

from pathlib import Path
from typing import Optional

import unix_ar  # type: ignore
from typing_extensions import Self

from .fake import Fake
from .files import Files
from .version import PackageRelation, Version, VersionDepends, VersionRelation

from .types.cpu_arch import CpuArch


class Package:
    """ APT package information. """

    @classmethod
    def from_deb(cls, deb: str, depends: list[list[VersionDepends]]) -> None | Self:
        """ Create a package form a deb file. """
        if not deb.endswith('.deb'):
            return None

        filename = os.path.basename(deb)[:-4]
        parts = filename.split('_')

        if len(parts) != 3:
            return None

        name = parts[0].strip()
        version = parts[1].strip()
        arch = CpuArch.from_str(parts[2].strip())
        if not arch:
            logging.error('Unknown arch in %s, Skipping!', filename)
            return None

        p = cls(name, arch, 'local_deb')

        p.version = Version(version)
        p.depends = depends

        if os.path.isfile(deb):
            p.local_file = deb

        return p

    def __init__(self, name: str, arch: CpuArch, repo: str) -> None:
        self.name: str = name
        self.arch: CpuArch = arch
        self.repo: str = repo

        self.version: Optional[Version] = None
        self.file_url: Optional[str] = None
        self.local_file: Optional[str] = None

        self.pre_depends: list[list[VersionDepends]] = []
        self.depends: list[list[VersionDepends]] = []

        self.breaks: list[list[VersionDepends]] = []
        self.conflicts: list[list[VersionDepends]] = []

        self.recommends: list[list[VersionDepends]] = []
        self.suggests: list[list[VersionDepends]] = []
        self.enhances: list[list[VersionDepends]] = []

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

    def extract(self, location: Optional[str] = None,
                files: Optional[Files] = None,
                use_sudo: bool = True) -> Optional[str]:
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


def filter_packages(p: Package, v: Version, r: Optional[VersionRelation]) -> bool:
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
