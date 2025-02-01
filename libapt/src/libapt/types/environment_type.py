""" Enum for supported environment types. """
from __future__ import annotations

from enum import Enum
from typing import Optional


class EnvironmentType(Enum):
    """ Enum for supported environment types. """
    FAKEROOT = 1
    CHROOT = 3
    SUDO = 4
    SHELL = 5

    @classmethod
    def from_str(cls, script_type: Optional[str]) -> EnvironmentType | None:
        """ Get ImageType from str. """
        if not script_type:
            return cls.FAKEROOT

        if isinstance(script_type, cls):
            return script_type

        if script_type == 'fake':
            return cls.FAKEROOT
        elif script_type == 'chroot':
            return cls.CHROOT
        elif script_type == 'sudo':
            return cls.SUDO
        elif script_type == 'shell':
            return cls.SHELL
        else:
            return None

    def __str__(self) -> str:
        if self.value == 1:
            return "fake"
        elif self.value == 3:
            return "chroot"
        elif self.value == 4:
            return "sudo"
        elif self.value == 5:
            return "shell"
        else:
            return "UNKNOWN"
