""" CPU architecture type. """
from enum import Enum
from typing import Optional


class UnsupportedCpuArchitecture(Exception):
    """ Raised if a version string is requested for an unsupported architecture. """


class CpuArch(Enum):
    """ Enum for supported CPU architectures. """
    AMD64 = 1
    ARM64 = 2
    ARMHF = 3
    ANY = 4

    @classmethod
    def from_str(cls, arch: Optional[str]):
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
        else:
            return None

    def __str__(self) -> str:
        if self.value == 1:
            return "amd64"
        elif self.value == 2:
            return "arm64"
        elif self.value == 3:
            return "armhf"
        elif self.value == 4:
            return "any"
        else:
            return "UNKNOWN"
