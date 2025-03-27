#!/usr/bin/env python
""" EBcL initrd generator. """

from __future__ import annotations

import argparse
import glob
import logging
import os
import shutil
import tempfile

from pathlib import Path
from typing import Any, Callable, Optional

from ebcl.common import init_logging, promo, log_exception
from ebcl.common.config import Config, InvalidConfiguration
from ebcl.common.files import EnvironmentType
from ebcl.common.templates import render_template
from ebcl.common.version import parse_package


class Module:
    path: Path
    """Relative path of the module"""
    dependencies: list[Module]
    """List of all recursive dependencies of the module"""
    is_builtin: bool
    """Module is built into the kernel"""

    @staticmethod
    def get_module_name(modpath: Path) -> str:
        """ Get the module name form the path. """
        mod_name = modpath.stem.split('.')[0]
        return mod_name

    def __init__(self, path: Path) -> None:
        self.path = path
        self.dependencies = []
        self.is_builtin = False

    @property
    def name(self) -> str:
        """The name of the module (e.g. 'foo' for 'foo.ko')"""
        return Module.get_module_name(self.path)

    @property
    def dependency_string(self) -> str:
        return f"{self.path}: {' '.join(map(lambda x: str(x.path), self.dependencies))}"


class Modules:
    """Kernel Module registry"""
    _modules: dict[str, Module]

    def __init__(self, base: Path, create_depmod: Callable[[], Any]) -> None:
        self._modules = {}

        depmod_file = base / "modules.dep"
        if not depmod_file.exists():
            create_depmod()
        if not depmod_file.exists():
            logging.error("Unable to create depmod file!")
            self._modules = {}
        else:
            self._parse_depmod(depmod_file)

        builtinmod_file = base / "modules.builtin"
        if builtinmod_file.exists():
            self._parse_builtinmod(builtinmod_file)

    def find(self, name: str) -> Module | None:
        """Find a module from a filename or module name"""
        if '.ko' in name:
            mod_name = Module.get_module_name(Path(name))
            logging.warning(
                "Using deprecated filename format for modules (%s). Please use only the module name: %s",
                name,
                mod_name
            )
            name = mod_name
        module = self._modules.get(name, None)

        if module is None:
            mod_names = list(self._modules.keys())
            mod_names.sort()
            logging.debug('Available modules: %s', mod_names)
            logging.debug('Missing module: %s', name)

        return module

    def __get_or_create(self, mod: str,) -> Module:
        modpath = Path(mod)
        mod_name = Module.get_module_name(modpath)
        module = self._modules.get(mod_name, None)
        if not module:
            module = Module(modpath)
            self._modules[module.name] = module
        return module

    def _parse_depmod(self, depmod: Path) -> None:
        with depmod.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#"):
                    continue  # Skip comments
                try:
                    (mod, depends) = line.split(':', 1)
                except ValueError:
                    continue  # If there is no colon, the line is malformed
                module = self.__get_or_create(mod)
                for dependency in depends.split():
                    module.dependencies.append(self.__get_or_create(dependency))

    def _parse_builtinmod(self, builtinmod: Path) -> None:
        with builtinmod.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line.startswith("#"):
                    continue  # Skip comments
                module = self.__get_or_create(line)
                module.is_builtin = True


class InitrdGenerator:
    """ EBcL initrd generator. """

    @log_exception(call_exit=True)
    def __init__(self, config_file: str, output_path: str) -> None:
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

        (debs, _contents, missing) = self.proxy.download_deb_packages(
            packages=[self.config.busybox],
            contents=self.target_dir,
            download_depends=True
        )

        if missing:
            return False

        busybox_path: Path | None = None
        for path in [Path('bin/busybox'), Path('usr/bin/busybox')]:
            if (self.target_dir / path).is_file():
                busybox_path = path

        if not busybox_path:
            logging.critical(
                'Busybox binary is missing! target: %s package: %s',
                self.target_dir, package)
            return False

        self.config.fake.run_chroot(
            f'{"/" / busybox_path} --install -s /bin', self.target_dir)

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

    def copy_modules(self, mods_dir: str) -> list[Module]:
        """ Copy the required modules.

        Args:
            mods_dir (str): Folder containing the modules.

        @return The modules that are requested and available
        """
        if not self.config.modules:
            logging.info('No modules defined.')
            return []

        logging.debug('Modules tmp folder: %s.', mods_dir)
        logging.debug('Target tmp folder: %s.', self.target_dir)

        kversion = self.find_kernel_version(mods_dir)
        if not kversion:
            logging.error('Kernel version not found, extracting modules failed!')
            raise InvalidConfiguration('Kernel version not found, extracting modules failed!')

        logging.info('Using kernel version %s.', kversion)

        mods_src_base = Path(mods_dir).absolute()
        mods_src = mods_src_base / 'lib' / 'modules' / kversion
        mods_dst = Path(self.target_dir).absolute() / 'lib' / 'modules' / kversion
        mods_dep_dst = mods_dst / 'modules.dep'

        modules = Modules(
            mods_src,
            lambda: self.config.fake.run_sudo(f'depmod -b {mods_src_base} -C /dev/null {kversion}')
        )

        logging.debug('Mods src: %s', mods_src)
        logging.debug('Mods dst: %s', mods_dst)

        self.config.fake.run_sudo(f'mkdir -p {mods_dst}')

        requested_modules: list[Module] = []
        all_modules: set[Module] = set()
        for module_name in self.config.modules:
            mod = modules.find(module_name)
            if not mod:
                raise InvalidConfiguration(f'Module {module_name} not found!')

            if mod.is_builtin:
                logging.info("Module %s is built into the kernel.", mod.name)
            else:
                all_modules.add(mod)
                all_modules.update(mod.dependencies)
                requested_modules.append(mod)

        for module in all_modules:
            logging.info('Processing module %s...', module.name)

            src = mods_src / module.path
            dst = mods_dst / module.path

            self.config.fh.copy_file(
                src=str(src),
                dst=str(dst),
                environment=EnvironmentType.SUDO,
                uid=0,
                gid=0,
                mode='644'
            )

            # Create entry in modules.dep file
            self.config.fake.run_sudo(f'echo {module.dependency_string} >> {mods_dep_dst}')

        return requested_modules

    def add_devices(self) -> None:
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

    def download_deb_packages(self, allow_missing=False) -> None:
        """ Download all needed deb packages. """
        (debs, _contents, missing) = self.proxy.download_deb_packages(
            packages=self.config.packages,
            contents=self.target_dir,
            download_depends=True
        )

        shutil.rmtree(debs)

        if not allow_missing and missing:
            logging.critical('Not found packages: %s', missing)
            raise InvalidConfiguration(f'Not found packages: {missing}')

    @log_exception()
    def create_initrd(self) -> Optional[str]:
        """ Create the initrd image.  """
        image_path = os.path.join(self.config.output_path, self.name)

        # Create necessary directories
        for dir_name in ['proc', 'sys', 'dev', 'sysroot', 'var', 'usr/bin',
                         'tmp', 'run', 'root', 'usr', 'usr/sbin', 'usr/lib', 'etc']:
            self.config.fake.run_sudo(
                f'mkdir -p --mode=0755 {os.path.join(self.target_dir, dir_name)}')

        # Create lib and bin folder symlinks
        self.config.fake.run_sudo(f'ln -sf usr/lib {self.target_dir}/lib')
        self.config.fake.run_sudo(f'ln -sf usr/lib32 {self.target_dir}/lib32')
        self.config.fake.run_sudo(f'ln -sf usr/lib64 {self.target_dir}/lib64')
        self.config.fake.run_sudo(f'ln -sf usr/libx32 {self.target_dir}/libx32')
        self.config.fake.run_sudo(f'ln -sf usr/bin {self.target_dir}/bin')
        self.config.fake.run_sudo(f'ln -sf usr/sbin {self.target_dir}/sbin')

        logging.info('Installing busybox...')

        success = self.install_busybox()
        if not success:
            return None

        self.download_deb_packages()

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
            (debs, _contents, missing) = self.config.proxy.download_deb_packages(
                packages=[self.config.kernel],
                contents=mods_dir
            )
            shutil.rmtree(debs)

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
            requested_modules = self.copy_modules(mods_dir)
        else:
            logging.info('No modules defined.')
            requested_modules = []

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
            'mods': [m.name for m in requested_modules]
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
    def finalize(self) -> None:
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
