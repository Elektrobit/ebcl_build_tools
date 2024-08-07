#!/usr/bin/env python
""" EBcL boot generator. """
import argparse
import logging
import os
import tempfile

from pathlib import Path
from typing import Optional, Any

from ebcl.common import init_logging, promo, log_exception
from ebcl.common.apt import Apt
from ebcl.common.config import load_yaml
from ebcl.common.fake import Fake
from ebcl.common.files import Files, parse_scripts, parse_files, reslove_file
from ebcl.common.proxy import Proxy
from ebcl.common.version import VersionDepends, parse_package_config, parse_package


class FileNotFound(Exception):
    """ Raised if a command returns and returncode which is not 0. """


class BootGenerator:
    """ EBcL boot generator. """

    # config file
    config: str
    # config values
    packages: list[VersionDepends]
    files: list[dict[str, str]]
    host_files: list[dict[str, str]]
    boot_tarball: Optional[str]
    scripts: list[dict[str, Any]]
    arch: str
    archive_name: str
    target_dir: str
    archive_path: str
    download_deps: bool
    tar: bool
    use_ebcl_apt: bool

    # proxy
    proxy: Proxy
    # fakeroot helper
    fake: Fake
    # files helper
    fh: Files

    @log_exception(call_exit=True)
    def __init__(self, config_file: str):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        config = load_yaml(config_file)

        self.config = config_file

        config_dir = os.path.dirname(config_file)

        self.archive_name = config.get('archive_name', 'boot.tar')
        self.download_deps = config.get('download_deps', True)
        self.tar = config.get('tar', True)

        # do not resolve names!
        self.files = config.get('files', [])

        self.host_files = parse_files(
            config.get('host_files', None),
            relative_base_dir=config_dir)

        self.boot_tarball = config.get('boot_tarball', None)
        if isinstance(self.boot_tarball, dict):
            self.boot_tarball = reslove_file(
                file=self.boot_tarball['name'],
                file_base_dir=self.boot_tarball.get('base_dir', None),
                relative_base_dir=config_dir
            )

        self.scripts = parse_scripts(
            config.get('scripts', None),
            relative_base_dir=config_dir)

        self.arch = config.get('arch', 'arm64')

        self.packages = parse_package_config(
            config.get('boot_packages', []), self.arch)

        use_packages = config.get('use_packages', True)
        if use_packages:
            ps = parse_package_config(config.get('packages', []), self.arch)
            if ps:
                self.packages += ps

        kernel = parse_package(config.get('kernel', None), self.arch)
        if kernel:
            self.packages.append(kernel)

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

        logging.debug('Using apt repos: %s', self.proxy.apts)

        self.fake = Fake()
        self.fh = Files(self.fake)

    def download_deb_packages(self, package_dir: str):
        """ Download all needed deb packages. """
        (_debs, _contents, missing) = self.proxy.download_deb_packages(
            packages=self.packages,
            contents=package_dir
        )

        if missing:
            logging.critical('Not found packages: %s', missing)

    def copy_files(self,
                   relative_base_dir: str,
                   files: list[dict[str, str]],
                   target_dir: str,
                   output_path: str,
                   fix_ownership: bool = False):
        """ Copy files to be used. """

        logging.debug('Files: %s', files)

        for entry in files:
            logging.info('Processing entry: %s', entry)

            src = entry.get('source', None)
            if not src:
                logging.error(
                    'Invalid file entry %s, source is missing!', entry)

            if '$$RESULTS$$' in src:
                logging.debug(
                    'Replacing $$RESULTS$$ with %s for file %s.', output_path, entry)
                parts = src.split('$$RESULTS$$/')
                src = os.path.abspath(os.path.join(output_path, parts[-1]))

            src = Path(relative_base_dir) / src

            dst = Path(target_dir)
            file_dest = entry.get('destination', None)
            if file_dest:
                dst = dst / file_dest

            mode: str = entry.get('mode', '600')
            uid: int = int(entry.get('uid', '0'))
            gid: int = int(entry.get('gid', '0'))

            logging.debug('Copying files %s', src)

            copied_files = self.fh.copy_file(
                src=str(src),
                dst=str(dst),
                uid=uid,
                gid=gid,
                mode=mode,
                delete_if_exists=True,
                fix_ownership=fix_ownership
            )

            if not copied_files:
                raise FileNotFound(f'File {src} not found!')

    def run_scripts(self,
                    relative_base_dir: str,
                    cwd: str,
                    output_path: str):
        """ Run scripts. """
        logging.debug('Target dir: %s', self.target_dir)
        logging.debug('Relative base dir: %s', relative_base_dir)
        logging.debug('CWD: %s', cwd)

        for script in self.scripts:
            logging.info('Running script %s.', script)

            if 'name' not in script:
                logging.error(
                    'Invalid script entry %s, name is missing!', script)

            if '$$RESULTS$$' in script['name']:
                logging.debug(
                    'Replacing $$RESULTS$$ with %s for script %s.', output_path, script)
                parts = script['name'].split('$$RESULTS$$/')
                script['name'] = os.path.abspath(
                    os.path.join(output_path, parts[-1]))

            file = os.path.join(relative_base_dir, script['name'])

            self.fh.run_script(
                file=file,
                params=script.get('params', None),
                environment=script.get('env', None),
                cwd=cwd
            )

    @log_exception()
    def create_boot(self, output_path: str) -> Optional[str]:
        """ Create the boot.tar.  """

        self.target_dir = tempfile.mkdtemp()
        logging.debug('Target directory: %s', self.target_dir)

        # Use target_dir as default cwd/chroot for file operations
        self.fh.target_dir = self.target_dir

        package_dir = tempfile.mkdtemp()
        logging.debug('Package directory: %s', package_dir)

        output_path = os.path.abspath(output_path)
        logging.debug('Output directory: %s', output_path)
        if not os.path.isdir(output_path):
            logging.critical('Output path %s is no folder!', output_path)
            exit(1)

        logging.info('Download deb packages...')
        self.download_deb_packages(package_dir)

        if self.boot_tarball:
            if '$$RESULTS$$' in self.boot_tarball:
                parts = self.boot_tarball.split('$$RESULTS$$/')
                self.boot_tarball = os.path.abspath(
                    os.path.join(output_path, parts[-1]))

            logging.info('Extracting boot tarball...')
            boot_tar_temp = tempfile.mkdtemp()

            logging.debug(
                'Temporary folder for boot tarball: %s', boot_tar_temp)

            tarball = os.path.join(os.path.dirname(
                self.config), self.boot_tarball)

            logging.debug('Extracting boot tarball %s to %s',
                          tarball, boot_tar_temp)

            self.fh.extract_tarball(
                archive=tarball,
                directory=boot_tar_temp
            )

            # Merge deb content and boot tarball
            self.fake.run(cmd=f'rsync -av {boot_tar_temp}/* {package_dir}')

            # Delete temporary tar folder
            self.fake.run(f'rm -rf {boot_tar_temp}', check=False)

        # Copy host files to target_dir folder
        logging.info('Copy host files to target dir...')
        self.copy_files(os.path.dirname(self.config), self.host_files,
                        self.target_dir, output_path=output_path)

        # Copy host files package_dir folder
        logging.info('Copy host files package dir...')
        self.copy_files(os.path.dirname(self.config),
                        self.host_files, package_dir, output_path=output_path)

        logging.info('Running config scripts...')
        self.run_scripts(relative_base_dir=os.path.dirname(
            self.config), cwd=package_dir, output_path=output_path)

        # Copy files and directories specified in the files
        logging.info('Copy result files...')
        self.copy_files(package_dir, self.files, target_dir=self.target_dir,
                        fix_ownership=True, output_path=output_path)

        # Remove package temporary folder
        logging.info('Remove temporary package contents...')
        self.fake.run(f'rm -rf {package_dir}', check=False)

        if self.tar:
            # create tar archive
            logging.info('Creating tar...')

            return self.fh.pack_root_as_tarball(
                output_dir=output_path,
                archive_name=self.archive_name,
                root_dir=self.target_dir,
                use_fake_chroot=False
            )

        # copy to output folder
        logging.info('Copying files...')
        self.fh.copy_file(f'{self.target_dir}/*',
                          output_path,
                          move=True,
                          delete_if_exists=True)
        return output_path

    @log_exception()
    def finalize(self):
        """ Finalize output and cleanup. """

        # delete temporary folder
        logging.debug('Remove temporary folder...')
        self.fake.run(f'rm -rf {self.target_dir}', check=False)


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL boot generator. """
    init_logging()

    logging.info('\n===================\n'
                 'EBcL Boot Generator\n'
                 '===================\n')

    parser = argparse.ArgumentParser(
        description='Create the content of the boot partiton as boot.tar.')
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('output', type=str,
                        help='Path to the output directory')

    args = parser.parse_args()

    logging.debug('Running boot_generator with args %s', args)

    # Read configuration
    generator = BootGenerator(args.config_file)

    image = None

    # Create the boot.tar
    image = generator.create_boot(args.output)

    generator.finalize()

    if image:
        print(f'Results were written to {image}.')
        promo()
    else:
        print('Build failed!')
        exit(1)


if __name__ == '__main__':
    main()
