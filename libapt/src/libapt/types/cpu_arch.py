""" CPU architecture type. """
from __future__ import annotations

from enum import Enum
from typing import Optional


class UnsupportedCpuArchitecture(Exception):
    """ Raised if a version string is requested for an unsupported architecture. """


class CpuArch(Enum):
    """ Enum for supported CPU architectures. """
    UNDEFINED = 0
    AMD64 = 1
    ARM64 = 2
    ARMHF = 3
    ANY = 4
    ALL = 5

    @classmethod
    def from_str(cls, arch: Optional[str]) -> CpuArch | None:
        """ Get ImageType from str. """
        if not arch:
            return cls.ARM64

        if isinstance(arch, cls):
            return arch

        if arch == 'amd64':
            return cls.AMD64
        elif arch == 'arm64':
            return cls.ARM64
        elif arch == 'armhf':
            return cls.ARMHF
        elif arch == 'any':
            return cls.ANY
        elif arch == 'all':
            return cls.ALL
        else:
            return None

    def __str__(self) -> str:
        if self == self.AMD64:
            return "amd64"
        elif self == self.ARM64:
            return "arm64"
        elif self == self.ARMHF:
            return "armhf"
        elif self == self.ANY:
            return "any"
        elif self == self.ALL:
            return "all"
        else:
            return "UNKNOWN"

    def get_arch(self) -> str:
        """ Get the arch string used by compilers and QEMU. """
        if self == self.AMD64:
            return "x86_64"
        elif self == self.ARM64:
            return "aarch64"

        raise UnsupportedCpuArchitecture(
            f'Unsupported CPU architecture {str(self)} for kiwi-ng build!')

    def get_package_arch(self) -> str:
        """ Get the arch string used by Debian packages. """
        if self == self.AMD64:
            return "amd64"
        elif self == self.ARM64:
            return "arm64"

        raise UnsupportedCpuArchitecture(
            f'Unsupported CPU architecture {str(self)} for berrymill build!')
