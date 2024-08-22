#!/usr/bin/env python
""" EBcL boot generator. """
import argparse
import logging
import os
import tempfile

from typing import Optional

from ebcl.common import init_logging, promo, log_exception
from ebcl.common.config import Config
from ebcl.common.files import resolve_file


class BootGenerator:
    """ EBcL boot generator. """

    @log_exception(call_exit=True)
    def __init__(self, config_file: str, output_path: str):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        self.config: Config = Config(config_file, output_path)

        self.proxy = self.config.proxy
        self.fake = self.config.fake
        self.fh = self.config.fh

        if self.config.name:
            self.name: str = self.config.name + '.tar'
        else:
            self.name = 'boot.tar'

        if self.config.kernel:
            self.config.packages.append(self.config.kernel)

        logging.debug('Using apt repos: %s', self.proxy.apts)

    def download_deb_packages(self, package_dir: str):
        """ Download all needed deb packages. """
        (_debs, _contents, missing) = self.proxy.download_deb_packages(
            packages=self.config.packages,
            contents=package_dir
        )

        if missing:
            logging.critical('Not found packages: %s', missing)

    @log_exception()
    def create_boot(self) -> Optional[str]:
        """ Create the boot.tar.  """
        logging.debug('Target directory: %s', self.config.target_dir)

        package_dir = tempfile.mkdtemp()
        logging.debug('Package directory: %s', package_dir)

        output_path = os.path.abspath(self.config.output_path)
        logging.debug('Output directory: %s', self.config.output_path)
        if not os.path.isdir(self.config.output_path):
            logging.critical('Output path %s is no folder!',
                             self.config.output_path)
            exit(1)

        logging.info('Download deb packages...')
        self.download_deb_packages(package_dir)

        if self.config.base_tarball:
            base_tarball = self.config.base_tarball

            logging.info('Extracting base tarball %s...', base_tarball)
            boot_tar_temp = tempfile.mkdtemp()

            logging.debug('Extracting bsae tarball %s to %s',
                          base_tarball, boot_tar_temp)

            self.fh.extract_tarball(
                archive=base_tarball,
                directory=boot_tar_temp,
                use_sudo=not self.config.use_fakeroot
            )

            if self.config.use_fakeroot:
                run_fn = self.fake.run_fake
            else:
                run_fn = self.fake.run_sudo

            # Merge deb content and boot tarball
            run_fn(cmd=f'rsync -a {boot_tar_temp}/* {package_dir}')

            # Delete temporary tar folder
            run_fn(f'rm -rf {boot_tar_temp}', check=False)

        # Copy host files to target_dir folder
        logging.info('Copy host files to target dir...')
        self.fh.copy_files(self.config.host_files,
                           self.config.target_dir)

        # Copy host files package_dir folder
        logging.info('Copy host files package dir...')
        self.fh.copy_files(self.config.host_files, package_dir)

        logging.info('Running config scripts...')
        self.fh.run_scripts(self.config.scripts, package_dir)

        # Copy files and directories specified in the files
        logging.info('Copy result files...')
        files = [{'source': resolve_file(f, package_dir)}
                 for f in self.config.files]
        self.fh.copy_files(files, self.config.target_dir,
                           fix_ownership=True)

        # Remove package temporary folder
        logging.info('Remove temporary package contents...')
        self.fake.run_cmd(f'rm -rf {package_dir}', check=False)

        if self.config.tar:
            # create tar archive
            logging.info('Creating tar...')

            return self.fh.pack_root_as_tarball(
                output_dir=output_path,
                archive_name=self.name,
                root_dir=self.config.target_dir,
                use_sudo=not self.config.use_fakeroot
            )

        # copy to output folder
        logging.info('Copying files...')
        self.fh.copy_file(f'{self.config.target_dir}/*',
                          output_path,
                          move=True,
                          delete_if_exists=True,
                          fix_ownership=True)
        return output_path


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL boot generator. """
    init_logging()

    logging.info('\n===================\n'
                 'EBcL Boot Generator\n'
                 '===================\n')

    parser = argparse.ArgumentParser(
        description='Create the content of the boot partiton.')
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('output', type=str,
                        help='Path to the output directory')

    args = parser.parse_args()

    logging.debug('Running boot_generator with args %s', args)

    # Read configuration
    generator = BootGenerator(args.config_file, args.output)

    image = None

    # Create the boot.tar
    image = generator.create_boot()

    if image:
        print(f'Results were written to {image}.')
        promo()
    else:
        print('Build failed!')
        exit(1)


if __name__ == '__main__':
    main()
