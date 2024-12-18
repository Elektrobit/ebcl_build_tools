#!/usr/bin/env python
""" Download and extract deb packages. """
import argparse
import logging
import os

from ebcl import __dependencies__, __version__, __ebcl_repo_key__
from ebcl.common import init_logging, promo, log_exception
from ebcl.common.fake import Fake


class CoreTool:
    """ Some core helper functions. """

    @log_exception(call_exit=True)
    def install_dependencies(self) -> None:
        """ Install the required system packages.  """
        logging.info('Installing the required system packages: %s',
                     __dependencies__)
        fake = Fake()
        fake.run_sudo(f'apt install -y {__dependencies__}')

    @log_exception(call_exit=True)
    def system_configuration(self) -> None:
        """ Apply the required system configuration.  """
        logging.info('Applying required system configuration...')
        fake = Fake()

        key_url = os.environ.get('EBCL_REPO_KEY', __ebcl_repo_key__)
        key_name = key_url.split('/')[-1]

        get_key_cmd = f'wget {key_url}'
        if key_url.startswith('file://'):
            key_url = key_url.replace('file: // ', '')
            get_key_cmd = f'cp {key_url} {key_name}'

        fake.run_sudo(
            'cd /etc/apt/trusted.gpg.d; '
            'rm -f elektrobit.*; '
            f'rm -f {key_name}*; '
            f'{get_key_cmd}; '
            f'gpg --dearmor {key_name}; '
            f'mv {key_name} elektrobit.pub; '
            f'mv {key_name}.gpg elektrobit.gpg')


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of the core tool. """
    init_logging()

    logging.info('\n======================\n'
                 'Core Tool %s\n'
                 '=======================\n', __version__)

    parser = argparse.ArgumentParser(
        description='The core tool provides helper functions.')
    parser.add_argument('-d', '--depends', action='store_true',
                        help='Install required system packages.')
    parser.add_argument('-c', '--config-host', action='store_true',
                        help='Apply required host configuration.')

    args = parser.parse_args()

    core = CoreTool()

    if args.depends:
        core.install_dependencies()

    if args.config_host:
        core.system_configuration()

    promo()


if __name__ == '__main__':
    main()
