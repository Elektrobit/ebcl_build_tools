""" Fakeroot and subprocess helper. """
import logging
import os
import subprocess
import tempfile

from io import BufferedWriter
from pathlib import Path
from subprocess import PIPE
from typing import Tuple, Optional, Any


class CommandFailed(Exception):
    """ Raised if a command returns and returncode which is not 0. """


class Fake:
    """ Fakeroot and subprocess helper. """

    def __init__(self, state: Optional[str] = None) -> None:
        """ Set state directory. """
        if state is None:
            self.state: Path = Path(tempfile.mktemp())
            self.state.touch()
        else:
            self.state = Path(state)

    def __del__(self) -> None:
        """ Remove state directory. """
        if self.state:
            if os.path.isfile(self.state):
                os.remove(self.state)

    def run_cmd(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        stdout: Optional[BufferedWriter] = None,
        check=True,
        capture_output=False,
    ) -> Tuple[Optional[str], Optional[str], int]:
        """ Run a command. """
        logging.info('Running command: %s', cmd)

        out: Any
        if capture_output:
            err = PIPE
            if stdout is None:
                out = PIPE
            else:
                out = stdout
        else:
            err = None
            out = None

        if stdout is not None:
            out = stdout

        p = subprocess.run(
            cmd,
            check=False,
            shell=True,
            stdout=out,
            stderr=err,
            cwd=cwd
        )

        pout: Optional[str]
        perr: Optional[str]
        if capture_output:
            if stdout is None:
                pout = p.stdout.decode('utf8')
                if pout.strip():
                    logging.info('STDOUT: %s', pout)

            perr = p.stderr.decode('utf8')
            if perr.strip():
                logging.error('%s has stderr output.\nSTDERR: %s', cmd, perr)
        else:
            pout = None
            perr = None

        if p.returncode != 0:
            logging.info('Returncode: %s', p.returncode)
            if check:
                logging.critical(
                    'Execution of command %s failed with returncode %s!', cmd, p.returncode)
                raise CommandFailed(
                    f'Execution of command {cmd} failed with returncode {p.returncode}!\n'
                    f'returncode: {p.returncode}\n'
                    f'STDOUT:\n{pout}'
                    f'STDERR:\n{perr}')

        return (pout, perr, p.returncode)

    def run_fake(
        self,
        cmd: str,
        cwd: Optional[str] = None,
        stdout: Optional[BufferedWriter] = None,
        check=True,
        capture_output=False,
    ) -> Tuple[Optional[str], Optional[str], int]:
        """ Run a command using fakeroot. """
        return self.run_cmd(
            cmd=f'fakeroot -i {self.state} -s {self.state} -- {cmd}',
            cwd=cwd,
            stdout=stdout,
            check=check,
            capture_output=capture_output
        )

    def run_chroot(
        self,
        cmd: str,
        chroot: str,
        check=True,
        capture_output=False
    ) -> Tuple[Optional[str], Optional[str], int]:
        """ Run a command using sudo and chroot. """
        (out, err, returncode) = self.run_cmd(
            cmd=f'sudo chroot {chroot} {cmd}',
            check=check,
            capture_output=capture_output
        )

        if out is None:
            out = ''

        return (out, err, returncode)

    def run_sudo(
            self, cmd: str,
            cwd: Optional[str] = None,
            stdout: Optional[BufferedWriter] = None,
            check=True,
            capture_output=False,
    ) -> Tuple[Optional[str], Optional[str], int]:
        """ Run a command using sudo. """
        cmd = cmd.replace('"', r'\"')
        return self.run_cmd(
            cmd=f'sudo bash -c \"{cmd}\"',
            cwd=cwd,
            stdout=stdout,
            check=check,
            capture_output=capture_output
        )
