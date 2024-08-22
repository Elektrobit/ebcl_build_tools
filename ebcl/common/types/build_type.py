""" Build type for the root filesystem build. """
from enum import Enum
from typing import Optional


class BuildType(Enum):
    """ Build type for the root filesystem build. """
    ELBE = 1
    KIWI = 2

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
        else:
            return None

    def __str__(self) -> str:
        if self.value == 1:
            return "elbe"
        elif self.value == 2:
            return "kiwi-ng"
        else:
            return "UNKNOWN"
