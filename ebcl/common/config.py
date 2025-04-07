""" Yaml loading helpers. """
import glob
import logging
import os
import shutil
import tempfile

from functools import partial
from pathlib import Path
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
        'modules_folder', 'result_pattern', 'image', 'berrymill_conf', 'use_berrymill',
        'use_bootstrap_package', 'bootstrap_package', 'bootstrap', 'kiwi_root_overlays',
        'use_kiwi_defaults', 'kiwi_scripts', 'kvm', 'image_version', 'type',
        'root_password', 'hostname', 'domain', 'console', 'sysroot_packages',
        'sysroot_defaults', 'primary_distro', 'base', 'debootstrap_flags', 'install_recommends'
    ]

    def __init__(self, config_file: str, output_path: str) -> None:
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
        self.ebcl_version: str = '1.2'
        # Files to include from host env
        self.host_files: list[dict[str, Any]] = []
        # Files to extract from target environment
        self.files: list[str] = []
        # Scripts for target configration
        self.scripts: list[dict[str, Any]] = []
        # Name of the template file
        self.template: Optional[str] = None
        # Name of the artifact
        self.name: Optional[str] = None
        # Download package dependencies
        self.download_deps: bool = True
        # Base enviromnet as a tarball
        self.base_tarball: Optional[str] = None
        # Packages to install or extract
        self.packages: list[VersionDepends] = []
        # Kernel package
        self.kernel: Optional[VersionDepends] = None
        # Pack result as tar
        self.tar: bool = True
        # Busybox package for minmal environment
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
        # Pattern to find the build result.
        self.result_pattern: Optional[str] = None
        # Image description file
        self.image: Optional[str] = None
        # Berrymill configuration file
        self.berrymill_conf: Optional[str] = None
        # Use Berrymill for Kiwi-ng builds.
        self.use_berrymill: bool = True
        # Use a bootstrap package for Kiwi-ng builds.
        self.use_bootstrap_package: bool = True
        # Name of the Kiwi-ng bootstrap package.
        self.bootstrap_package: Optional[str] = None
        # Additional bootstrap packages for debootstrap.
        self.bootstrap: list[VersionDepends] = []
        # List of overlay folders for Kiwi-ng builds.
        self.kiwi_root_overlays: list[str] = []
        # Add default names for Kiwi-ng artifacts.
        self.use_kiwi_defaults: bool = True
        # Additional scripts for the Kiwi-ng build.
        self.kiwi_scripts: list[str] = []
        # Use KVM acceleration for Kiwi-ng builds.
        self.kvm: bool = True
        # Kiwi-ng image version string
        self.image_version: Optional[str] = None
        # Root filesystem build type.
        self.type: BuildType | None = BuildType.DEBOOTSTRAP
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
        # Console
        self.console: Optional[str] = None
        # Additional sysroot packages.
        self.sysroot_packages: list[VersionDepends] = []
        # Add default extensions for sysroot builds
        self.sysroot_defaults: bool = True
        # Install recommends (defaults to true, to keep behavior)
        self.install_recommends: bool = True
        # where credentials are kept
        self.cred_dir = Path('/workspace/tools/user_config/auth.d/')

        self.parse()

        self._create_netrc_file()

    @log_exception()
    def __del__(self) -> None:
        """ Cleanup. """
        (Path.home() / ".netrc").unlink(missing_ok=True)
        self.fake.run_sudo('rm -f ~/.netrc')

        if self.use_fakeroot:
            self.fake.run_cmd(f'rm -rf {self.target_dir}')
        else:
            self.fake.run_sudo(f'rm -rf {self.target_dir}')

    def _load_yaml(self, file: str) -> dict[str, Any]:
        with open(file, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def _create_netrc_file(self) -> None:
        """ combine credential files and create .netrc """

        netrc_path = Path.home() / ".netrc"
        with open(netrc_path, "w", opener=partial(os.open, mode=0o600)) as outfile:
            for f in sorted(self.cred_dir.glob("*.conf")):
                with f.open("r") as infile:
                    shutil.copyfileobj(infile, outfile)
                    outfile.write('\n')
        # Install it also for the root user. Required for debootstrap
        self.fake.run_sudo(f"install -m 0600 {netrc_path} ~/.netrc")

    def parse(self) -> None:
        """ Load yaml configuration. """
        self._parse_yaml(self.config_file)
        if self.use_ebcl_apt:
            ebcl_apt = Apt.ebcl_apt(self.arch)
            self.proxy.add_apt(ebcl_apt)
            self.apt_repos.append(ebcl_apt)
            ebcl_main = Apt.ebcl_primary_repo(self.arch, self.primary_distro)
            self.proxy.add_apt(ebcl_main)
            self.apt_repos.append(ebcl_main)

    def _parse_yaml(self, file: str) -> None:
        """ Load yaml configuration. """
        conifg_file = os.path.abspath(file)
        config_dir = os.path.dirname(conifg_file)

        config = self._load_yaml(conifg_file)

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
            arch = CpuArch.from_str(config.get('arch', None))
            if not arch:
                raise InvalidConfiguration(f'Unknown arch: {config.get("arch")}')
            self.arch = arch

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

        if 'primary_distro' in config:
            self.primary_distro = config.get('primary_distro', None)

        if 'use_ebcl_apt' in config:
            self.use_ebcl_apt = config.get('use_ebcl_apt', False)

        host_files = parse_files(
            config.get('host_files', None),
            output_path=self.output_path,
            relative_base_dir=config_dir)

        for host_file in host_files:
            host_file_path = host_file['source']
            matches = glob.glob(host_file_path)
            if not matches:
                raise FileNotFound(f'The file {host_file} referenced form config file '
                                   f'{conifg_file} was not found!')

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
                                   f'{conifg_file} was not found!')

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
                                           f'of config file {conifg_file} does not exist!')

        if 'result_pattern' in config:
            self.result_pattern = config.get('result_pattern', None)

        if 'image' in config:
            image = config.get('image', None)
            self.image = resolve_file(
                file=image,
                relative_base_dir=config_dir
            )
            self.image = sub_output_path(self.image, self.output_path)

        if 'berrymill_conf' in config:
            berrymill_conf = config.get('berrymill_conf', None)
            self.berrymill_conf = resolve_file(
                file=berrymill_conf,
                relative_base_dir=config_dir
            )
            self.berrymill_conf = sub_output_path(
                self.berrymill_conf, self.output_path)

        if 'use_berrymill' in config:
            self.use_berrymill = config.get('use_berrymill', True)

        if 'use_bootstrap_package' in config:
            self.use_bootstrap_package = config.get(
                'use_bootstrap_package', True)

        if 'bootstrap_package' in config:
            self.bootstrap_package = config.get('bootstrap_package', None)

        if 'bootstrap' in config:
            if inherit_packages:
                bootstrap = parse_package_config(
                    config.get('bootstrap', []), self.arch)
                self.bootstrap += bootstrap
            else:
                self.bootstrap = parse_package_config(
                    config.get('bootstrap', []), self.arch)

        if 'kiwi_root_overlays' in config:
            kiwi_root_overlays = parse_files(
                config.get('kiwi_root_overlays', None),
                output_path=self.output_path,
                relative_base_dir=config_dir)

            kiwi_overlay_list = [r['source'] for r in kiwi_root_overlays]

            for r in kiwi_overlay_list:
                if not os.path.isdir(r):
                    raise InvalidConfiguration(f'Kiwi-ng root overlay {r} from config file '
                                               f'{conifg_file} does not exist!')

            self.kiwi_root_overlays += kiwi_overlay_list

        if 'use_kiwi_defaults' in config:
            self.use_kiwi_defaults = config.get('use_kiwi_defaults', True)

        if 'kiwi_scripts' in config:
            kiwi_scripts = parse_files(
                config.get('kiwi_scripts', None),
                output_path=self.output_path,
                relative_base_dir=config_dir)

            kiwi_script_list = [s['source'] for s in kiwi_scripts]

            for s in kiwi_script_list:
                if not os.path.isfile(s):
                    raise InvalidConfiguration(f'Kiwi-ng script {s} from config file '
                                               f'{conifg_file} does not exist!')

            self.kiwi_scripts += kiwi_script_list

        if 'kvm' in config:
            self.kvm = config.get('kvm', True)

        if 'image_version' in config:
            self.image_version = config.get('image_version', None)

        if 'type' in config:
            self.type = BuildType.from_str(config.get('type', None))

        if 'debootstrap_flags' in config:
            self.debootstrap_flags = config.get('debootstrap_flags', None)

        if 'root_password' in config:
            self.root_password = config.get('root_password', 'linux')

        if 'hostname' in config:
            self.hostname = config.get('hostname', 'ebcl')

        if 'domain' in config:
            self.domain = config.get('domain', 'elektrobit.com')

        if 'console' in config:
            self.console = config.get('console', None)

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

        if 'install_recommends' in config:
            self.install_recommends = config.get('install_recommends', True)

        for key in config.keys():
            if key not in self.keywords:
                logging.warning(
                    'Config file %s is using unknown keyword %s!',
                    conifg_file, key)

    def extract_package(self, vd: VersionDepends) -> bool:
        """Get package and add it to the target dir. """
        return self.proxy.extract_package(vd, self.arch, self.target_dir)
