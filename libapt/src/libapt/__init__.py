"""
Libapt provides a generic pure Python interface for Debian APT repositories.
"""
import logging
import os

from pathlib import Path
from typing import Callable, Literal, TypeVar, overload


__version__ = "0.1.0"


class ImplementationError(Exception):
    """ Raised if a assumption is not met. """


def init_logging(level: str = 'INFO') -> None:
    """ Initialize the logging for the APT Browser. """
    log_format = '[{asctime}] {levelname:<6s} {filename:s}:{lineno:d} - {message:s}'
    log_date_format = '%m/%d/%Y %I:%M:%S %p'
    used_level = level

    env_level = os.getenv('LOG_LEVEL', None)
    if env_level:
        used_level = env_level

    logging.basicConfig(
        level=used_level,
        format=log_format,
        style='{',
        datefmt=log_date_format
    )

    logging.info('Setting log level to %s. (default: %s, env: %s)',
                 used_level, level, env_level)


def bug(bug_url: str = 'https://github.com/thir820/apt_browser/issues') -> None:
    """ Print bug hint. """
    text = "Seems you hit a bug!\n"
    text += f"Please provide a bug ticket at {bug_url}."
    text += f"You are using APT Browser version {__version__}."

    print(text)


def promo() -> None:
    """ Print promo hint. """
    text = f'Thanks for using APT Browser {__version__}!'
    text += '\n'
    text += "=========================================================================\n"
    text += "Do you need embedded (Linux) engineering services?\n"
    text += "Do you need 15 year maintenance for your embedded solution?\n"
    text += "Elektrobit can help! Contact us at https://www.elektrobit.com/contact-us/\n"
    text += "=========================================================================\n"
    text += '\n'

    print(text)


RT = TypeVar('RT')


@overload
def log_exception(call_exit: Literal[True] = True, code: int = 1) -> Callable[[Callable[..., RT]], Callable[..., RT]]:
    ...


@overload
def log_exception(
    call_exit: Literal[False] = False, code: int = 1
) -> Callable[[Callable[..., RT]], Callable[..., RT | None]]:
    ...


def log_exception(call_exit: bool = False, code: int = 1) -> Callable[[Callable[..., RT]], Callable[..., RT | None]]:
    """ Catch and log exceptions. """
    def _log_exception(func: Callable[..., RT]) -> Callable[..., RT | None]:
        def inner_function(*args, **kwargs) -> RT | None:
            result = None

            try:
                result = func(*args, **kwargs)
            except Exception as e:
                logging.critical(e, exc_info=True)
                bug()
                if call_exit:
                    exit(code)

            return result

        return inner_function

    return _log_exception


def get_cache_folder(folder: str) -> str:
    """ Get the shared cache folder.  """
    if os.path.isdir('/workspace/state'):
        cache = f'/workspace/state/{folder}'
    else:
        home = Path.home()
        cache_folder = home / ".cache" / folder
        cache = str(cache_folder.absolute())

    if not os.path.isdir(cache):
        os.makedirs(cache, exist_ok=True)

    return cache
