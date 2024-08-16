""" Enum for supported image types. """
from enum import Enum


class ImageType(Enum):
    """ Enum for supported image types. """
    ELBE = 1
    KIWI = 2

    @classmethod
    def from_str(cls, image_type: str):
        """ Get ImageType from str. """
        if image_type == 'elbe':
            return cls.ELBE
        elif image_type == 'kiwi':
            return cls.KIWI
        else:
            return None

    def __str__(self) -> str:
        if self.value == 1:
            return "elbe"
        elif self.value == 2:
            return "kiwi"
        else:
            return "UNKNOWN"
