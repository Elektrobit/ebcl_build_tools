""" Build type for the root filesystem build. """
from enum import Enum
from typing import Optional


class BuildType(Enum):
    """ Build type for the root filesystem build. """
    KIWI = 2
    DEBOOTSTRAP = 3

    @classmethod
    def from_str(cls, build_type: Optional[str]):
        """ Get ImageType from str. """
        if not build_type:
            return cls.DEBOOTSTRAP

        if isinstance(build_type, cls):
            return build_type

        elif build_type == 'kiwi':
            return cls.KIWI
        elif build_type == 'debootstrap':
            return cls.DEBOOTSTRAP
        else:
            return None

    def __str__(self) -> str:
        if self.value == 2:
            return "kiwi-ng"
        elif self.value == 3:
            return "debootstrap"
        else:
            return "UNKNOWN"
