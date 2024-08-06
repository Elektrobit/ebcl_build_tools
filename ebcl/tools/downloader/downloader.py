#!/usr/bin/env python
""" Download and extract deb packages. """
import argparse
import logging
import os
import tempfile

from typing import Optional

from ebcl.common import init_logging, promo, log_exception
from ebcl.common.apt import Apt
from ebcl.common.config import load_yaml
from ebcl.common.proxy import Proxy
from ebcl.common.version import VersionDepends


class PackageDownloader:
    """ Download and extract deb packages. """
    # TODO: test

    # config file
    config: str
    # config values
    arch: str
    use_ebcl_apt: bool
    # proxy
    proxy: Proxy

    @log_exception(call_exit=True)
    def __init__(self, config_file: str):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        config = load_yaml(config_file)

        self.config = config_file

        self.arch = config.get('arch', 'arm64')

        self.proxy = Proxy()
        self.proxy.parse_apt_repos(
            apt_repos=config.get('apt_repos', None),
            arch=self.arch,
            ebcl_version=config.get('ebcl_version', None)
        )

        self.use_ebcl_apt = config.get('use_ebcl_apt', False)
        if self.use_ebcl_apt:
            ebcl_apt = Apt.ebcl_apt(self.arch)
            self.proxy.add_apt(ebcl_apt)

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

        if not arch:
            arch = 'amd64'

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
            arch=arch
        ) for name in package_names]

        (_debs, _contents, missing) = self.proxy.download_deb_packages(
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

    logging.info('\n======================\n'
                 'EBcL Package downloader\n'
                 '=======================\n')

    parser = argparse.ArgumentParser(
        description='Download and extract the given packages.')
    parser.add_argument('config', type=str,
                        help='Path to the YAML configuration file containing the apt repostory config.')
    parser.add_argument('packages', type=str,
                        help='List of packages separated by space.')
    parser.add_argument('-o', '--output', type=str,
                        help='Path to the output directory')
    parser.add_argument('-a', '--arch', type=str,
                        help='Architecture of the packages.')
    parser.add_argument('-d', '--download-depends', action='store_true',
                        help='Download all package dependencies recursive.')

    args = parser.parse_args()

    downloader = PackageDownloader(args.config)

    # Download and extract the packages
    downloader.download_packages(
        args.packages, args.output, args.arch, args.download_depends)

    promo()


if __name__ == '__main__':
    main()
