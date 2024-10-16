""" Build type for the root filesystem build. """
from enum import Enum
from typing import Optional


class BuildType(Enum):
    """ Build type for the root filesystem build. """
    ELBE = 1
    KIWI = 2
    DEBOOTSTRAP = 3
    MULTISTRAP = 4

    @classmethod
    def from_str(cls, build_type: Optional[str]):
        """ Get ImageType from str. """
        if not build_type:
            return cls.ELBE

        if isinstance(build_type, cls):
            return build_type

        if build_type == 'elbe':
            return cls.ELBE
        elif build_type == 'kiwi':
            return cls.KIWI
        elif build_type == 'debootstrap':
            return cls.DEBOOTSTRAP
        elif build_type == 'multistrap':
            return cls.MULTISTRAP
        else:
            return None

    def __str__(self) -> str:
        if self.value == 1:
            return "elbe"
        elif self.value == 2:
            return "kiwi-ng"
        elif self.value == 3:
            return "debootstrap"
        elif self.value == 4:
            return "multistrap"
        else:
            return "UNKNOWN"
