#!/usr/bin/env python
""" EBcL apt proxy commandline interface. """
import argparse
import logging

from ebcl.common import add_loging_arguments, init_logging

# TODO: implmement


def main() -> None:
    """ Main entrypoint of EBcL apt proxy. """
    parser = argparse.ArgumentParser(
        description='EBcL apt proxy.')
    add_loging_arguments(parser)

    args = parser.parse_args()

    init_logging(args)

    logging.info('\n=========\n'
                 'EBcL Proxy\n'
                 '==========\n')

    logging.critical('Not implemented!')


if __name__ == '__main__':
    main()
