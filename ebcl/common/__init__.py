"""
Common functions of the EBcL build tools.
"""

import logging
import os
import sys

from pathlib import Path
from typing import Callable, Literal, TypeVar, overload

import ebcl


class ImplementationError(Exception):
    """Raised if a assumption is not met."""


def init_logging(level: str = "INFO") -> None:
    """
    Initialize the logging for the EBcL build tools.

    Args:
        level:
            Log level to use. If a log level is provided using environment
            variable LOG_LEVEL, it will overwrite this parameter.
    """
    log_format = "[{asctime}] {levelname:<6s} {filename:s}:{lineno:d} - {message:s}"
    log_date_format = "%m/%d/%Y %I:%M:%S %p"
    used_level = level

    env_level = os.getenv("LOG_LEVEL", None)
    if env_level:
        used_level = env_level

    logging.basicConfig(level=used_level, format=log_format, style="{", datefmt=log_date_format)

    logging.info("Setting log level to %s. (default: %s, env: %s)", used_level, level, env_level)


def bug(bug_url: str = "https://github.com/Elektrobit/ebcl_build_tools/issues") -> None:
    """
    Print bug hint.

    Args:
        bug_url: URL of the bug tracker.
    """
    text = "Seems you hit a bug!\n"
    text += f"Please provide a bug ticket at {bug_url}."
    text += f"You are using EBcl build tooling version {ebcl.__version__},"
    text += f"and EB corbos Linux workspace version {os.getenv('RELEASE_VERSION', None)}"

    print(text)


def promo() -> None:
    """Print promo hint."""
    release_version = os.getenv("RELEASE_VERSION", None)

    if release_version:
        print(f"Thanks for using EB corbos Linux workspace {release_version}!")
    else:
        text = "\n"
        text += "=========================================================================\n"
        text += "Do you need embedded (Linux) engineering services?\n"
        text += "Do you need 15 year maintenance for your embedded solution?\n"
        text += "Elektrobit can help! Contact us at https://www.elektrobit.com/contact-us/\n"
        text += "=========================================================================\n"
        text += "\n"

        print(text)


RT = TypeVar("RT")


@overload
def log_exception(
    call_exit: Literal[True] = True, code: int = 1
) -> Callable[[Callable[..., RT]], Callable[..., RT]]: ...  # pragma: no cover


@overload
def log_exception(
    call_exit: Literal[False] = False, code: int = 1
) -> Callable[[Callable[..., RT]], Callable[..., RT | None]]: ...  # pragma: no cover


def log_exception(call_exit: bool = False, code: int = 1) -> Callable[[Callable[..., RT]], Callable[..., RT | None]]:
    """
    Catch and log exceptions. This is function intended as an annotation.

    Args:
        call_exit:
            Call exit with the given exit code if an exception happens.
        code:
            Exit code in case of an exception.

    Returns:
        Callable.
    """

    def _log_exception(func: Callable[..., RT]) -> Callable[..., RT | None]:
        def inner_function(*args, **kwargs) -> RT | None:
            result = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logging.critical(e, exc_info=True)
                bug()
                if call_exit:
                    sys.exit(code)

            return result

        return inner_function

    return _log_exception


def get_cache_folder(folder: str | Path) -> Path:
    """
    Get the shared cache folder.

    Args:
        folder:
            Name of the folder.

    Returns:
        Path to the cache folder.
    """
    workspace_state = Path("/workspace/state")

    if workspace_state.is_dir():
        cache = workspace_state / folder
    else:
        home = Path.home()
        cache_folder = home / ".ebcl_build_cache" / folder
        cache = cache_folder.absolute()

    if not cache.is_dir():
        os.makedirs(cache, exist_ok=True)

    return cache
