#!/usr/bin/env python
""" Download and extract deb packages. """
import argparse
import logging
import os
import tempfile

from typing import Optional

from ebcl import __version__
from ebcl.common import init_logging, promo, log_exception
from ebcl.common.config import Config
from ebcl.common.version import VersionDepends

from ebcl.common.types.cpu_arch import CpuArch


class PackageDownloader:
    """ Download and extract deb packages. """

    @log_exception(call_exit=True)
    def __init__(self, config_file: str, output_path: str):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        self.config: Config = Config(config_file, output_path)

    @log_exception(call_exit=True)
    def download_packages(
        self,
        packages: str,
        output_path: Optional[str] = None,
        arch: Optional[str] = None,
        download_depends: bool = False
    ) -> None:
        """ Download the packages.  """
        if not output_path:
            output_path = tempfile.mkdtemp()
            assert output_path

        if arch:
            cpu_arch = CpuArch.from_str(arch)
        else:
            cpu_arch = self.config.arch

        content_path = os.path.join(output_path, 'contents')
        os.makedirs(content_path, exist_ok=True)

        package_names = [p.strip() for p in packages.split(' ')]

        if not package_names:
            logging.error('No package names given.')
            exit(1)

        vds: list[VersionDepends] = [VersionDepends(
            name=name,
            package_relation=None,
            version_relation=None,
            version=None,
            arch=cpu_arch
        ) for name in package_names]

        (_debs, _contents, missing) = self.config.proxy.download_deb_packages(
            packages=vds,
            extract=True,
            debs=output_path,
            contents=content_path,
            download_depends=download_depends
        )

        if missing:
            logging.error('Not found packages: %s', missing)

        print(f'The packages were downloaded to:\n{output_path}')
        print(f'The packages were extracted to:\n{content_path}')


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL boot generator. """
    init_logging()

    logging.info('\n=============================\n'
                 'EBcL Package downloader %s\n'
                 '=============================\n', __version__)

    parser = argparse.ArgumentParser(
        description='Download and extract the given packages.')
    parser.add_argument('config', type=str,
                        help='Path to the YAML configuration file containing the apt repository config.')
    parser.add_argument('packages', type=str,
                        help='List of packages separated by space.')
    parser.add_argument('-o', '--output', type=str,
                        help='Path to the output directory')
    parser.add_argument('-a', '--arch', type=str,
                        help='Architecture of the packages.')
    parser.add_argument('-d', '--download-depends', action='store_true',
                        help='Download all package dependencies recursive.')

    args = parser.parse_args()

    downloader = PackageDownloader(args.config, args.output)

    # Download and extract the packages
    downloader.download_packages(
        args.packages, args.output, args.arch, args.download_depends)

    promo()


if __name__ == '__main__':
    main()
