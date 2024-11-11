#!/usr/bin/env python
""" EBcL root filesystem generator. """
import argparse
import logging
import os
import tempfile

from typing import Optional

from ebcl import __version__
from ebcl.common import init_logging, promo, log_exception
from ebcl.common.apt import Apt
from ebcl.common.config import Config
from ebcl.common.version import parse_package_config
from ebcl.tools.root.elbe import build_elbe_image
from ebcl.tools.root.kiwi import build_kiwi_image
from ebcl.tools.root.debootstrap import DebootstrapRootGenerator

from ebcl.common.types.cpu_arch import CpuArch
from ebcl.common.types.build_type import BuildType

from . import config_root


class FileNotFound(Exception):
    """ Raised if a command returns and returncode which is not 0. """


class RootGenerator:
    """ EBcL root filesystem generator. """

    @log_exception(call_exit=True)
    def __init__(self, config_file: str, output_path: str, sysroot_build: bool):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        self.config: Config = Config(config_file, output_path)

        # folder to collect build results
        self.result_dir: str = tempfile.mkdtemp()
        # flag for sysroot build
        self.sysroot: bool = sysroot_build

        if self.config.name:
            self.name: str = self.config.name
        else:
            self.name = 'root'

        if not self.config.console:
            if self.config.arch == CpuArch.AMD64:
                self.config.console = 'ttyS0,115200'
            else:
                self.config.console = 'ttyAMA0,115200'

        use_primary_repo = self.config.type == BuildType.ELBE or \
            self.config.type == BuildType.DEBOOTSTRAP
        if self.config.primary_repo:
            use_primary_repo = True

        if not self.config.primary_distro:
            # Default primary distro
            self.config.primary_distro = 'jammy'

        self.primary_repo: Optional[Apt] = None
        if use_primary_repo:
            if not self.config.primary_repo:
                # Default primary repo
                if self.config.arch == CpuArch.AMD64:
                    self.config.primary_repo = 'http://archive.ubuntu.com/ubuntu'
                else:
                    self.config.primary_repo = 'http://ports.ubuntu.com/ubuntu-ports/'

            primary_apt = Apt(
                url=self.config.primary_repo,
                distro=self.config.primary_distro,
                components=['main'],
                arch=self.config.arch
            )

            logging.info('Adding primary repo %s...', primary_apt)

            self.config.proxy.add_apt(primary_apt)
            self.primary_repo = primary_apt
            self.config.apt_repos = [primary_apt] + self.config.apt_repos

    @log_exception()
    def create_root(
        self,
        run_scripts: bool = True
    ) -> Optional[str]:
        """ Create the root image.  """

        if self.sysroot:
            logging.info('Running build in sysroot mode.')

            if self.config.sysroot_defaults:
                sysroot_default_packages = parse_package_config(
                    ['build-essential', 'g++'],
                    self.config.arch
                )
                logging.info('Adding sysroot default packages %s.',
                             sysroot_default_packages)
                self.config.sysroot_packages += sysroot_default_packages

            if self.config.sysroot_packages:
                logging.info(
                    'Adding sysroot packages %s to package list.', self.config.sysroot_packages)
                self.config.packages += self.config.sysroot_packages

            sysroot_image_name = f'{self.name}_sysroot'
            logging.info('Adding sysroot suffix to image name %s: %s',
                         self.name, sysroot_image_name)
            self.name = sysroot_image_name

        logging.debug('Target directory: %s', self.config.target_dir)
        logging.debug('Result directory: %s', self.result_dir)

        image_file = None
        if self.config.type == BuildType.ELBE:
            image_file = build_elbe_image(
                self.config,
                self.primary_repo,
                self.name,
                self.result_dir
            )
        elif self.config.type == BuildType.KIWI:
            image_file = build_kiwi_image(
                self.config,
                self.name,
                self.result_dir
            )
        elif self.config.type == BuildType.DEBOOTSTRAP:
            generator = DebootstrapRootGenerator(self.config, self.result_dir)
            image_file = generator.build_debootstrap_image(self.name)

        if not image_file:
            logging.critical('Image build failed!')
            return None

        if run_scripts:
            if self.config.name:
                name = self.config.name + '.tar'
            else:
                name = 'root.tar'
            archive_out = os.path.join(self.result_dir, name)
            image_file = config_root(self.config, image_file, archive_out)

            if not image_file:
                logging.critical('Configuration failed!')
                return None
        else:
            logging.info(
                'Skipping the config script execution and copying host files.')

        # Move image tar to output folder
        image_name = os.path.basename(image_file)
        ext = None
        if image_name.endswith('.tar'):
            ext = '.tar'
        elif '.tar.' in image_name:
            ext = '.tar.' + image_name.split('.tar.', maxsplit=1)[-1]
        else:
            ext = '.' + image_name.split('.', maxsplit=1)[-1]

        out_image = f'{self.config.output_path}/{self.name}{ext}'
        if image_file != out_image:
            self.config.fake.run_fake(f'mv {image_file} {out_image}')

        return out_image

    @log_exception()
    def finalize(self):
        """ Finalize output and cleanup. """

        logging.info('Finalizing image build...')

        # Fix ownership
        try:
            self.config.fake.run_sudo(
                f'chown -R ebcl:ebcl {self.result_dir}')
        except Exception as e:
            logging.error('Fixing ownership failed! %s', e)

        try:
            self.config.fake.run_fake(
                f'cp -R {self.result_dir}/* {self.config.output_path}')
        except Exception as e:
            logging.error('Copying all artefacts failed! %s', e)

        if logging.root.level == logging.DEBUG:
            logging.debug(
                'Log level set to debug, skipping cleanup of build artefacts.')
            logging.debug('Target folder: %s', self.config.target_dir)
            logging.debug('Results folder: %s', self.result_dir)
            return

        # delete temporary folders
        try:
            if self.result_dir:
                self.config.fake.run_fake(f'rm -rf {self.result_dir}')
        except Exception as e:
            logging.error('Removing temp result dir failed! %s', e)


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL root generator. """
    init_logging('DEBUG')

    logging.info('\n=========================\n'
                 'EBcL Root Generator %s\n'
                 '=========================\n', __version__)

    parser = argparse.ArgumentParser(
        description='Create the content of the root partiton as root.tar.')
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('output', type=str,
                        help='Path to the output directory')
    parser.add_argument('-n', '--no-config', action='store_true',
                        help='Skip the config script execution.')
    parser.add_argument('-s', '--sysroot', action='store_true',
                        help='Skip the config script execution.')

    args = parser.parse_args()

    logging.debug('Running root_generator with args %s', args)

    # Read configuration
    generator = RootGenerator(args.config_file, args.output, args.sysroot)

    # Create the root.tar
    image = None

    run_scripts = not bool(args.no_config)
    image = generator.create_root(run_scripts=run_scripts)

    generator.finalize()

    if image:
        print(f'Image was written to {image}.')
        promo()
    else:
        exit(1)


if __name__ == '__main__':
    main()
