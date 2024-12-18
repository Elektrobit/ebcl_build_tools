""" Yaml loading helpers. """
import glob
import logging
import os
import tempfile

from typing import Any, Optional

import yaml

from . import log_exception

from .apt import Apt
from .fake import Fake
from .files import Files, parse_files, parse_scripts, resolve_file, sub_output_path
from .proxy import Proxy
from .version import VersionDepends, parse_package_config, parse_package

from .types.build_type import BuildType
from .types.cpu_arch import CpuArch


class FileNotFound(Exception):
    """ Raised if a referenced file was not found. """


class InvalidConfiguration(Exception):
    """ Raised if a configuration issue is found. """


class Config:
    """ EBcL build tools config parameters. """

    # Config keywords
    keywords = [
        'arch', 'use_fakeroot', 'apt_repos', 'use_ebcl_apt', 'ebcl_version', 'host_files',
        'files', 'scripts', 'template', 'name', 'download_deps', 'base_tarball', 'packages',
        'kernel', 'tar', 'busybox', 'modules', 'root_device', 'devices', 'kernel_version',
        'modules_folder', 'image', 'root_password', 'hostname', 'domain', 'sysroot_packages',
        'sysroot_defaults', 'primary_distro', 'base', 'debootstrap_flags'
    ]

    def __init__(self, config_file: str, output_path: str):
        self.config_file = config_file
        self.proxy = Proxy()
        self.fake = Fake()

        self.target_dir = tempfile.mkdtemp()
        self.output_path = os.path.abspath(output_path)

        self.fh = Files(
            fake=self.fake,
            target_dir=self.target_dir)

        # Target CPU architecture.
        self.arch: CpuArch = CpuArch.ARM64
        # Use fakeroot where possible instead of sudo.
        self.use_fakeroot: bool = False
        # APT repositories used for building.
        self.apt_repos: list[Apt] = []
        # Use the EBcL apt repository?
        self.use_ebcl_apt: bool = True
        # EBcL version
        self.ebcl_version: str = '1.4'
        # Files to include from host env
        self.host_files: list[dict[str, Any]] = []
        # Files to extract from target environment
        self.files: list[str] = []
        # Scripts for target configuration
        self.scripts: list[dict[str, Any]] = []
        # Name of the template file
        self.template: Optional[str] = None
        # Name of the artifact
        self.name: Optional[str] = None
        # Download package dependencies
        self.download_deps: bool = True
        # Base environment as a tarball
        self.base_tarball: Optional[str] = None
        # Packages to install or extract
        self.packages: list[VersionDepends] = []
        # Kernel package
        self.kernel: Optional[VersionDepends] = None
        # Pack result as tar
        self.tar: bool = True
        # Busybox package for minimal environment
        self.busybox: Optional[VersionDepends] = None
        # Modules files to copy.
        self.modules: list[str] = []
        # Name of the root device
        self.root_device: Optional[str] = None
        # List of device nodes
        self.devices: list[dict[str, Any]] = []
        # Kernel version string
        self.kernel_version: Optional[str] = None
        # Modules folder in host environment
        self.modules_folder: Optional[str] = None
        # Image description file
        self.image: Optional[str] = None
        # Primary repo for debootstrap
        self.primary_distro: Optional[str] = None
        # Additional debootstrap parameters
        self.debootstrap_flags: Optional[str] = '--include=ca-certificates'
        # Password for the root user
        self.root_password: Optional[str] = 'linux'
        # Hostname for the root filesystem
        self.hostname: str = 'ebcl'
        # Domain for the root filesystem
        self.domain: str = 'elektrobit.com'
        # Additional sysroot packages.
        self.sysroot_packages: list[VersionDepends] = []
        # Add default extensions for sysroot builds
        self.sysroot_defaults: bool = True

        self.parse()

    @log_exception()
    def __del__(self):
        """ Cleanup. """
        if self.use_fakeroot:
            self.fake.run_cmd(f'rm -rf {self.target_dir}')
        else:
            self.fake.run_sudo(f'rm -rf {self.target_dir}')

    def _load_yaml(self, file: str) -> dict[str, Any]:
        with open(file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def parse(self):
        """ Load yaml configuration. """
        self._parse_yaml(self.config_file)

    def _parse_yaml(self, file: str):
        """ Load yaml configuration. """
        config_file = os.path.abspath(file)
        config_dir = os.path.dirname(config_file)

        config = self._load_yaml(config_file)

        base = config.get('base', None)
        if base:
            # Handle parent config files
            if isinstance(base, str):
                bases = [base]
            else:
                bases = base

            if not isinstance(bases, list):
                raise InvalidConfiguration(
                    f'Unknown base value {base} ({type(base)})!')

            for b in bases:
                b = resolve_file(
                    file=b,
                    relative_base_dir=config_dir
                )
                self._parse_yaml(b)

        if 'arch' in config:
            self.arch = CpuArch.from_str(config.get('arch', None))

        if 'use_fakeroot' in config:
            self.use_fakeroot = config.get('use_fakeroot', False)

        if 'ebcl_version' in config:
            self.ebcl_version = config.get('ebcl_version', '1.2')

        if 'apt_repos' in config:
            apt_repos = self.proxy.parse_apt_repos(
                apt_repos=config.get('apt_repos', None),
                arch=self.arch
            )

            for apt_repo in apt_repos:
                self.proxy.add_apt(apt_repo)

            self.apt_repos += apt_repos

        if 'use_ebcl_apt' in config:
            self.use_ebcl_apt = config.get('use_ebcl_apt', False)
            if self.use_ebcl_apt:
                ebcl_apt = Apt.ebcl_apt(self.arch)
                self.proxy.add_apt(ebcl_apt)
                self.apt_repos.append(ebcl_apt)
                ebcl_main = Apt.ebcl_primary_repo(self.arch)
                self.proxy.add_apt(ebcl_main)
                self.apt_repos.append(ebcl_main)

        host_files = parse_files(
            config.get('host_files', None),
            output_path=self.output_path,
            relative_base_dir=config_dir)

        for host_file in host_files:
            host_file_path = host_file['source']
            matches = glob.glob(host_file_path)
            if not matches:
                raise FileNotFound(f'The file {host_file} referenced form config file '
                                   f'{config_file} was not found!')

        self.host_files += host_files

        scripts = parse_scripts(
            config.get('scripts', None),
            output_path=self.output_path,
            relative_base_dir=config_dir)

        for script in scripts:
            script_path = script['name']
            matches = glob.glob(script_path)
            if not matches:
                raise FileNotFound(f'The script {script_path} referenced form config file '
                                   f'{config_file} was not found!')

        self.scripts += scripts

        files = config.get('files', [])
        self.files += files

        if 'template' in config:
            template = config.get('template', None)
            self.template = resolve_file(
                file=template,
                relative_base_dir=config_dir
            )
            self.template = sub_output_path(self.template, self.output_path)

        if 'name' in config:
            self.name = config.get('name', None)

        if 'download_deps' in config:
            self.download_deps = config.get('download_deps', None)

        if 'base_tarball' in config:
            base_tarball = config.get('base_tarball', None)
            self.base_tarball = resolve_file(
                file=base_tarball,
                relative_base_dir=config_dir
            )
            self.base_tarball = sub_output_path(
                self.base_tarball, self.output_path)

        inherit_packages: bool = config.get('inherit_packages', True)

        if 'packages' in config:
            if inherit_packages:
                packages = parse_package_config(
                    config.get('packages', []), self.arch)
                self.packages += packages
            else:
                self.packages = parse_package_config(
                    config.get('packages', []), self.arch)

        if 'kernel' in config:
            kernel = config.get('kernel', None)
            self.kernel = parse_package(kernel, self.arch)

        if 'tar' in config:
            self.tar = config.get('tar', True)

        if 'busybox' in config:
            busybox = config.get('busybox', None)
            self.busybox = parse_package(busybox, self.arch)

        if 'modules' in config:
            modules = config.get('modules', [])
            self.modules += modules

        if 'root_device' in config:
            self.root_device = config.get('root_device', None)

        if 'devices' in config:
            devices = config.get('devices', [])
            self.devices += devices

        if 'kernel_version' in config:
            self.kernel_version = config.get('kernel_version', None)

        if 'modules_folder' in config:
            modules_folder = config.get('modules_folder', None)
            self.modules_folder = resolve_file(
                file=modules_folder,
                relative_base_dir=config_dir
            )
            self.modules_folder = sub_output_path(
                self.modules_folder, self.output_path)

            if not os.path.isdir(self.modules_folder):
                raise InvalidConfiguration(f'The module folder {self.modules_folder} '
                                           f'of config file {config_file} does not exist!')

        if 'image' in config:
            image = config.get('image', None)
            self.image = resolve_file(
                file=image,
                relative_base_dir=config_dir
            )
            self.image = sub_output_path(self.image, self.output_path)

        if 'primary_distro' in config:
            self.primary_distro = config.get('primary_distro', None)

        if 'debootstrap_flags' in config:
            self.debootstrap_flags = config.get('debootstrap_flags', None)

        if 'root_password' in config:
            self.root_password = config.get('root_password', 'linux')

        if 'hostname' in config:
            self.hostname = config.get('hostname', 'ebcl')

        if 'domain' in config:
            self.domain = config.get('domain', 'elektrobit.com')

        if 'sysroot_packages' in config:
            if inherit_packages:
                sysroot_packages = parse_package_config(
                    config.get('sysroot_packages', []), self.arch)
                self.sysroot_packages += sysroot_packages
            else:
                self.sysroot_packages = parse_package_config(
                    config.get('sysroot_packages', []), self.arch)

        if 'sysroot_defaults' in config:
            self.sysroot_defaults = config.get('sysroot_defaults', True)

        for key in config.keys():
            if key not in self.keywords:
                logging.warning(
                    'Config file %s is using unknown keyword %s!',
                    config_file, key)

    def extract_package(self, vd: VersionDepends) -> bool:
        """Get package and add it to the target dir. """
        return self.proxy.extract_package(vd, self.arch, self.target_dir)
