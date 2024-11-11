#!/usr/bin/env python
""" EBcL initrd generator. """
import argparse
import glob
import logging
import os
import queue
import tempfile

from pathlib import Path
from typing import Optional

from ebcl.common import init_logging, promo, log_exception
from ebcl.common.config import Config, InvalidConfiguration
from ebcl.common.files import EnvironmentType
from ebcl.common.templates import render_template
from ebcl.common.version import parse_package


class InitrdGenerator:
    """ EBcL initrd generator. """

    @log_exception(call_exit=True)
    def __init__(self, config_file: str, output_path: str):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        self.config: Config = Config(config_file, output_path)
        self.target_dir: str = self.config.target_dir

        if self.config.name:
            self.name: str = self.config.name + '.img'
        else:
            self.name = 'initrd.img'

        if not self.config.busybox:
            self.config.busybox = parse_package(
                'busybox-static', self.config.arch)

        self.proxy = self.config.proxy

    def install_busybox(self) -> bool:
        """Get busybox and add it to the initrd. """
        package = None

        if not self.config.busybox:
            logging.critical('No busybox!')
            return False

        success = self.config.extract_package(self.config.busybox)
        if not success:
            return False

        if not os.path.isfile(os.path.join(self.target_dir, 'bin', 'busybox')):
            logging.critical(
                'Busybox binary is missing! target: %s package: %s',
                self.target_dir, package)
            return False

        self.config.fake.run_chroot(
            '/bin/busybox --install -s /bin', self.target_dir)

        return True

    def find_kernel_version(self, mods_dir: str) -> Optional[str]:
        """ Find the right kernel version. """
        if self.config.kernel_version:
            return self.config.kernel_version

        kernel_dirs = os.path.abspath(os.path.join(mods_dir, 'lib', 'modules'))
        versions = glob.glob(f'{kernel_dirs}/*')

        if not versions:
            logging.critical(
                'Kernel version not found! mods_dir: %s, kernel_dirs: %s', mods_dir, kernel_dirs)
            return None

        versions.sort()

        return os.path.basename(versions[-1])

    def copy_modules(self, mods_dir: str):
        """ Copy the required modules.

        Args:
            mods_dir (str): Folder containing the modules.
        """
        if not self.config.modules:
            logging.info('No modules defined.')
            return

        logging.debug('Modules tmp folder: %s.', mods_dir)
        logging.debug('Target tmp folder: %s.', self.target_dir)

        kversion = self.find_kernel_version(mods_dir)
        if not kversion:
            logging.error(
                'Kernel version not found, extracting modules failed!')
            raise InvalidConfiguration(
                'Kernel version not found, extracting modules failed!')

        logging.info('Using kernel version %s.', kversion)

        mods_src = os.path.abspath(os.path.join(
            mods_dir, 'lib', 'modules', kversion))

        mods_dep_src = os.path.join(mods_src, 'modules.dep')

        mods_dst = os.path.abspath(os.path.join(
            self.target_dir, 'lib', 'modules', kversion))

        mods_dep_dst = os.path.join(mods_dst, 'modules.dep')

        logging.debug('Mods src: %s', mods_src)
        logging.debug('Mods dst: %s', mods_dst)

        logging.debug('Create modules target...')
        self.config.fake.run_sudo(f'mkdir -p {mods_dst}')

        orig_deps: dict[str, list[str]] = {}

        # TODO: fix depends

        if os.path.isfile(mods_dep_src):
            with open(mods_dep_src, encoding='utf8') as f:
                lines = f.readlines()
                for line in lines:
                    parts = line.split(':', maxsplit=1)
                    key = parts[0].strip()
                    values = []
                    if len(parts) > 1:
                        vs = parts[1].strip()
                        if vs:
                            values = [dep.strip()
                                      for dep in vs.split(' ') if dep != '']
                    orig_deps[key] = values

        mq: queue.Queue[str] = queue.Queue(maxsize=-1)

        for module in self.config.modules:
            mq.put_nowait(module)

        while not mq.empty():
            module = mq.get_nowait()

            logging.info('Processing module %s...', module)

            src = os.path.join(mods_src, module)
            dst = os.path.join(mods_dst, module)
            dst_dir = os.path.dirname(dst)

            logging.debug('Copying module %s to folder %s.', src, dst)

            if not os.path.isfile(src):
                logging.error('Module %s not found.', module)
                continue

            self.config.fake.run_sudo(f'mkdir -p {dst_dir}')

            self.config.fh.copy_file(
                src=src,
                dst=dst,
                environment=EnvironmentType.SUDO,
                uid=0,
                gid=0,
                mode='644'
            )

            # Find module dependencies.
            deps = ''
            if module in orig_deps:
                mdeps = orig_deps[module]
                deps = ' '.join(mdeps)
                for mdep in mdeps:
                    mq.put_nowait(mdep)

            self.config.fake.run_sudo(
                f'echo {module}: {deps} >> {mods_dep_dst}')

    def add_devices(self):
        """ Create device files. """
        self.config.fake.run_sudo(f'mkdir -p {self.target_dir}/dev')

        dev_folder = os.path.join(self.target_dir, 'dev')

        for device in self.config.devices:
            major = (int)(device['major'])
            minor = (int)(device['major'])

            if device['type'] == 'char':
                dev_type = 'c'
                mode = '200'
            elif device['type'] == 'block':
                dev_type = 'b'
                mode = '600'
            else:
                logging.error('Unsupported device type %s for %s',
                              device['type'], device['name'])
                continue

            self.config.fake.run_sudo(
                f'mknod -m {mode} {dev_folder}/{device["name"]} {dev_type} {major} {minor}')

            uid = device.get('uid', '0')
            gid = device.get('uid', '0')
            self.config.fake.run_sudo(
                f'chown {uid}:{gid} {dev_folder}/{device["name"]}')

    def download_deb_packages(self, allow_missing=False):
        """ Download all needed deb packages. """
        (_debs, _contents, missing) = self.proxy.download_deb_packages(
            packages=self.config.packages,
            contents=self.target_dir,
            download_depends=True
        )

        if not allow_missing and missing:
            logging.critical('Not found packages: %s', missing)
            raise InvalidConfiguration(f'Not found packages: {missing}')

    @log_exception()
    def create_initrd(self) -> Optional[str]:
        """ Create the initrd image.  """
        image_path = os.path.join(self.config.output_path, self.name)

        logging.info('Installing busybox...')

        success = self.install_busybox()
        if not success:
            return None

        self.download_deb_packages()

        # Create necessary directories
        for dir_name in ['proc', 'sys', 'dev', 'sysroot', 'var', 'bin',
                         'tmp', 'run', 'root', 'usr', 'sbin', 'lib', 'etc']:
            self.config.fake.run_sudo(
                f'mkdir -p {os.path.join(self.target_dir, dir_name)}')
            self.config.fake.run_sudo(
                f'chown 0:0 {os.path.join(self.target_dir, dir_name)}')

        if self.config.base_tarball:
            base_tarball = self.config.base_tarball
            logging.info('Extracting base tarball %s...', base_tarball)
            self.config.fh.extract_tarball(base_tarball, self.target_dir)

        mods_dir = None
        if self.config.modules_folder:
            mods_dir = self.config.modules_folder
            logging.info('Using modules from folder %s...', mods_dir)
        elif self.config.kernel:
            mods_dir = tempfile.mkdtemp()
            logging.info('Using modules from kernel deb packages...')
            (_debs, _contents, missing) = self.config.proxy.download_deb_packages(
                packages=[self.config.kernel],
                contents=mods_dir
            )
            if missing:
                logging.error('Not found packages: %s', missing)
        elif self.config.modules:
            logging.error('No module sources defined!')
            if self.config.modules:
                raise InvalidConfiguration('No module sources defined!')
        else:
            logging.info('No module sources defined.')

        if self.config.modules and mods_dir:
            logging.info('Adding modules %s...', self.config.modules)
            self.copy_modules(mods_dir)
        else:
            logging.info('No modules defined.')

        if mods_dir and not self.config.modules_folder:
            # Remove mods temporary folder
            self.config.fake.run_sudo(f'rm -rf {mods_dir}', check=False)

        # Add device nodes
        self.add_devices()

        # Copy files and directories specified in the files
        self.config.fh.copy_files(self.config.host_files, self.target_dir)

        # Create init script
        init_script: Path = Path(self.target_dir) / 'init'

        if self.config.template:
            template = self.config.template
        else:
            # Use default template
            template = os.path.join(os.path.dirname(__file__), 'init.sh')

        params = {
            'root': self.config.root_device,
            'mods': [m.split("/")[-1] for m in self.config.modules]
        }

        (_init_file, init_script_content) = render_template(
            template_file=template,
            params=params,
            generated_file_name=f'{self.config.name}.init.sh',
            results_folder=self.config.output_path,
            template_copy_folder=self.config.output_path
        )

        if not init_script_content:
            logging.critical('Rendering init script failed!')
            return None

        init_script.write_text(init_script_content)
        os.chmod(init_script, 0o755)

        # Create initrd image
        os.makedirs(os.path.dirname(image_path), exist_ok=True)
        with open(image_path, 'wb') as img:
            self.config.fake.run_sudo(
                'find . -print0 | cpio --null -ov --format=newc', cwd=self.target_dir, stdout=img)

        return image_path

    @log_exception()
    def finalize(self):
        """ Finalize output and cleanup. """

        # delete temporary folder
        self.config.fake.run_sudo(f' rm -rf {self.target_dir}')


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL initrd generator. """
    init_logging()

    logging.info('\n====================\n'
                 'EBcL Initrd Generator\n'
                 '=====================\n')

    parser = argparse.ArgumentParser(
        description='Create an initrd image for Linux.')
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('output', type=str,
                        help='Path to the output directory')

    args = parser.parse_args()

    logging.debug('Running initrd_generator with args %s', args)

    generator = InitrdGenerator(args.config_file, args.output)

    image = None

    # Create the initrd.img
    image = generator.create_initrd()

    generator.finalize()

    if image:
        print(f'Image was written to {image}.')
        promo()
    else:
        print('Image build failed!')
        exit(1)


if __name__ == '__main__':
    main()
