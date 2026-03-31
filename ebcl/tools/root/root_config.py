#!/usr/bin/env python
""" EBcL root filesystem config helper. """
import argparse
import logging
import os

from typing import Optional

from ebcl.common import add_loging_arguments, init_logging, promo, log_exception
from ebcl.common.config import Config

from . import config_root


class RootConfig:
    """ EBcL root filesystem config helper. """

    @log_exception(call_exit=True)
    def __init__(self, config_file: str, output_path: str) -> None:
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        self.config: Config = Config(config_file, output_path)

    @log_exception()
    def config_root(self, archive_in: str, archive_out: str) -> Optional[str]:
        """ Config the tarball.  """
        return config_root(self.config, archive_in, archive_out)


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL root filesystem config helper. """
    parser = argparse.ArgumentParser(
        description='Configure the given root tarball.')
    add_loging_arguments(parser)
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('archive_in', type=str, help='Root tarball.')
    parser.add_argument('archive_out', type=str, help='New tarball.')

    args = parser.parse_args()

    init_logging(args)

    logging.info('\n=====================\n'
                 'EBcL Root Configurator\n'
                 '======================\n')

    logging.debug('Running root_configurator with args %s', args)

    # Read configuration
    generator = RootConfig(args.config_file, os.path.dirname(args.archive_out))

    archive = generator.config_root(args.archive_in, args.archive_out)

    if archive:
        logging.info('Archive was written to %s.', archive)
        promo()
    else:
        exit(1)


if __name__ == '__main__':
    main()
