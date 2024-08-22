#!/usr/bin/env python
""" EBcL root filesystem generator. """
import argparse
import glob
import logging
import os
import platform
import shutil
import tempfile

from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse

import yaml

from ebcl.common import init_logging, promo, log_exception, ImplementationError
from ebcl.common.apt import Apt
from ebcl.common.config import Config, InvalidConfiguration
from ebcl.common.templates import render_template
from ebcl.common.version import parse_package_config

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

        use_primary_repo = self.config.type == BuildType.ELBE
        if self.config.primary_repo:
            use_primary_repo = True
        else:
            # Default primary repo
            if self.config.arch == CpuArch.AMD64:
                primary_repo = 'http://archive.ubuntu.com/ubuntu'
            else:
                primary_repo = 'http://ports.ubuntu.com/ubuntu-ports/'

        if not self.config.primary_distro:
            # Default primary distro
            primary_distro = 'jammy'

        self.primary_repo: Optional[Apt] = None
        if use_primary_repo:
            self.config.primary_repo = primary_repo
            self.config.primary_distro = primary_distro

            primary_apt = Apt(
                url=primary_repo,
                distro=primary_distro,
                components=['main'],
                arch=self.config.arch
            )

            logging.info('Adding primary repo %s...', primary_apt)

            self.config.proxy.add_apt(primary_apt)
            self.primary_repo = primary_apt
            self.config.apt_repos = [primary_apt] + self.config.apt_repos

    def _generate_elbe_image(self) -> Optional[str]:
        """ Generate an elbe image description. """
        # TODO: test

        logging.info('Generating elbe image from template...')

        if not self.config.primary_repo:
            logging.critical('No primary repo!')
            return None

        if not self.config.packages:
            logging.critical('Packages defined!')
            return None

        params: dict[str, Any] = {}

        params['name'] = self.config.name
        params['arch'] = self.config.arch.get_elbe_arch()

        if not self.primary_repo:
            raise InvalidConfiguration('Primary apt repository is missing!')

        try:
            url = urlparse(self.primary_repo.url)
        except Exception as e:
            logging.critical(
                'Invalid primary repo url %s! %s', self.primary_repo.url, e)
            return None

        params['primary_repo_url'] = url.netloc
        params['primary_repo_path'] = url.path
        params['primary_repo_proto'] = url.scheme
        params['distro'] = self.primary_repo.distro

        params['hostname'] = self.config.hostname
        params['domain'] = self.config.domain
        params['console'] = self.config.console

        if self.config.root_password:
            params['root_password'] = self.config.root_password
        else:
            params['root_password'] = ''

        if self.config.packages:
            package_names = []
            for vd in self.config.packages:
                package_names.append(vd.name)
            params['packages'] = package_names

        params['packer'] = self.config.packer
        params['output_archive'] = 'root.tar'

        if self.config.apt_repos:
            params['apt_repos'] = []
            for repo in self.config.apt_repos:
                components = ' '.join(repo.components)
                apt_line = f'{repo.url} {repo.distro} {components}'

                key = repo.get_key()

                if key:
                    params['apt_repos'].append({
                        'apt_line': apt_line,
                        'arch': repo.arch,
                        'key': key
                    })
                else:
                    params['apt_repos'].append({
                        'apt_line': apt_line,
                        'arch': repo.arch,
                    })

        if self.config.template is None:
            template = os.path.join(os.path.dirname(__file__), 'root.xml')
        else:
            template = self.config.template

        (image_file, _content) = render_template(
            template_file=template,
            params=params,
            generated_file_name=f'{self.name}.image.xml',
            results_folder=self.result_dir,
            template_copy_folder=self.result_dir
        )

        if not image_file:
            logging.critical('Rendering image description failed!')
            return None

        logging.debug('Generated image stored as %s', image_file)

        return image_file

    def _build_elbe_image(self) -> Optional[str]:
        """ Run elbe image build. """

        if self.config.image:
            image: Optional[str] = self.config.image
        else:
            image = self._generate_elbe_image()

        if not image:
            logging.critical('No elbe image description found!')
            return None

        if not os.path.isfile(image):
            logging.critical('Image %s not found!', image)
            return None

        (out, err, _returncode) = self.config.fake.run_cmd(
            'elbe control create_project')
        if err.strip() or not out:
            raise ImplementationError(
                f'Elbe project creation failed! err: {err.strip()}')
        prj = out.strip()

        pre_xml = os.path.join(
            self.result_dir, os.path.basename(image)) + '.gz'

        self.config.fake.run_cmd(
            f'elbe preprocess --output={pre_xml} {image}')
        self.config.fake.run_cmd(
            f'elbe control set_xml {prj} {pre_xml}')
        self.config.fake.run_cmd(f'elbe control build {prj}')
        self.config.fake.run_fake(f'elbe control wait_busy {prj}')
        self.config.fake.run_fake(
            f'elbe control get_files --output {self.result_dir} {prj}')
        self.config.fake.run_fake(f'elbe control del_project {prj}')

        tar = os.path.join(self.result_dir, 'root.tar')

        if os.path.isfile(tar):
            return tar

        results = Path(self.result_dir)

        # search for tar
        pattern = '*.tar'
        if self.config.result_pattern:
            pattern = self.config.result_pattern

        images = list(results.glob(pattern))
        if images:
            return os.path.join(self.result_dir, images[0])

        return ''

    def _generate_kiwi_image(self, generate_repos: bool = False) -> Optional[str]:
        """ Generate a kiwi image description. """

        # TODO: test

        if not self.config.apt_repos:
            logging.critical('No apt repositories defined!')
            return None

        bootstrap_package = None
        if self.config.use_bootstrap_package:
            bootstrap_package = self.config.bootstrap_package
            if not bootstrap_package:
                bootstrap_package = 'bootstrap-root-ubuntu-jammy'
                logging.info('No bootstrap paackage provided. '
                             'Using default package %s.', bootstrap_package)

        params: dict[str, Any] = {}

        if generate_repos:
            kiwi_repos = self._generate_kiwi_repo_config()
            if kiwi_repos:
                params['repos'] = kiwi_repos

        params['arch'] = self.config.arch.get_kiwi_arch()

        if self.config.image_version:
            params['version'] = self.config.image_version
        else:
            params['version'] = '1.0.0'

        if self.config.root_password:
            params['root_password'] = self.config.root_password
        else:
            params['root_password'] = ''

        if self.config.packages:
            package_names = []
            for vd in self.config.packages:
                package_names.append(vd.name)
            params['packages'] = package_names

        if bootstrap_package:
            params['bootstrap_package'] = bootstrap_package

        if self.config.bootstrap:
            package_names = []
            for vd in self.config.bootstrap:
                package_names.append(vd.name)
            params['bootstrap'] = package_names

        if self.config.template:
            template = self.config.template
        else:
            template = os.path.join(os.path.dirname(__file__), 'root.kiwi')

        (image_file, _content) = render_template(
            template_file=template,
            params=params,
            generated_file_name=f'{self.name}.image.kiwi',
            results_folder=self.result_dir,
            template_copy_folder=self.result_dir
        )

        if not image_file:
            logging.critical('Rendering image description failed!')
            return None

        logging.debug('Generated image stored as %s', image_file)

        return image_file

    def _generate_kiwi_repo_config(self) -> Optional[str]:
        """ Generate repos as kiwi XML tags. """

        # TODO: test

        repos = ''

        cnt = 0
        for apt in self.config.apt_repos:

            if apt.key_url or apt.key_gpg:
                logging.warning(
                    'Apt repository key checks are not supported for kiwi-only build!')

            for component in apt.components:
                bootstrap = 'false'
                if cnt == 0:
                    bootstrap = 'true'

                cmp_id = f'{cnt}_{apt.distro}_{component}'
                repos += f'<repository alias="{cmp_id}" type="apt-deb" ' \
                    f'distribution="{apt.distro}" components="{component}" ' \
                    f'use_for_bootstrap="{bootstrap}" repository_gpgcheck="false" >\n'
                repos += f'    <source path = "{apt.url}" />\n'
                repos += '</repository>\n\n'

                cnt += 1

        return repos

    def _generate_berrymill_config(self) -> Optional[str]:
        """ Generate a berrymill.conf. """

        # TODO: test

        berrymill_conf: dict[str, Any] = {}

        berrymill_conf['use-global-repos'] = False
        berrymill_conf['boxed_plugin_conf'] = '/etc/berrymill/kiwi_boxed_plugin.yml'
        berrymill_conf['repos'] = {}
        berrymill_conf['repos']['release'] = {}

        cnt = 1
        for apt in self.config.apt_repos:
            apt_repo_key = None
            (_pub, apt_repo_key) = apt.get_key_files(self.result_dir)
            if not apt_repo_key:
                logging.error('No key found for %s, skipping repo!', apt)
                continue

            arch = str(apt.arch)

            if arch not in berrymill_conf['repos']['release']:
                berrymill_conf['repos']['release'][arch] = {}

            for component in apt.components:
                cmp_id = f'{cnt}_{apt.distro}_{component}'
                cnt += 1

                berrymill_conf['repos']['release'][arch][cmp_id] = {
                    'url': apt.url,
                    'type': 'apt-deb',
                    'key': f'file://{apt_repo_key}',
                    'name': apt.distro,
                    'components': component
                }

        config_file = os.path.join(self.result_dir, 'berrymill.conf')

        try:
            with open(config_file, 'w', encoding='utf-8') as f:
                data = yaml.dump(berrymill_conf)
                logging.debug('Berrymill configuration: %s', data)
                f.write(data)
        except Exception as e:
            logging.critical('Saving berrymill.conf failed! %s', e)
            return None

        logging.debug('Berrymill configuration written to %s.', config_file)

        return config_file

    def _build_kiwi_image(self) -> Optional[str]:
        """ Run kiwi image build. """

        berrymill_conf = None
        use_berrymill = self.config.use_berrymill

        if use_berrymill:
            berrymill_conf = self.config.berrymill_conf
            if berrymill_conf:
                berrymill_conf = self.config.berrymill_conf
            else:
                logging.info('Generating the berrymill.conf...')
                berrymill_conf = self._generate_berrymill_config()
                if not berrymill_conf:
                    logging.critical('Generating a berrymill.conf failed!')
                    return None

        if not berrymill_conf:
            if use_berrymill:
                logging.warning(
                    'No berrymill.conf, falling back to kiwi-only build.')
            use_berrymill = False

        if self.config.image:
            image: Optional[str] = self.config.image
        else:
            generate_repos = not use_berrymill
            image = self._generate_kiwi_image(generate_repos)

        if not image:
            logging.critical('No kiwi image description found!')
            return None

        if not os.path.isfile(image):
            logging.critical('Image %s not found!', image)
            return None

        logging.debug('Berrymill.conf: %s', berrymill_conf)

        appliance = os.path.join(self.result_dir, image)

        if os.path.abspath(appliance) != os.path.abspath(image):
            shutil.copy(image, appliance)

        kiwi_scripts = self.config.kiwi_scripts
        kiwi_root_overlays = self.config.kiwi_root_overlays

        if self.config.use_kiwi_defaults:
            image_dir = Path(image).parent

            root_overlay = image_dir / 'root'
            if root_overlay.is_dir():
                logging.info('Adding %s to kiwi root overlays.', root_overlay)
                kiwi_root_overlays.append(str(root_overlay.absolute()))

            for name in ['config.sh', 'pre_disk_sync.sh', 'uboot-install.sh',
                         'post_bootstrap.sh', 'uboot_install.sh']:
                kiwi_script = image_dir / name
                if kiwi_script.is_file():
                    logging.info('Adding %s to kiwi scripts.', kiwi_script)
                    kiwi_scripts.append(str(kiwi_script.absolute()))

        # Copy kiwi image dependencies
        kiwi_script_files = [{'source': file, 'mode': 700}
                             for file in kiwi_scripts]
        self.config.fh.copy_files(
            kiwi_script_files, os.path.dirname(appliance))

        root_folder = os.path.join(os.path.dirname(appliance), 'root')
        self.config.fake.run_cmd(f'mkdir -p {root_folder}')

        for overlay in kiwi_root_overlays:
            self.config.fh.copy_file(
                f'{overlay}/*',
                f'{root_folder}',
                environment=None)

        # Copy other .kiwi files
        self.config.fh.copy_file(
            f'{os.path.dirname(image)}/*.kiwi',
            os.path.dirname(appliance)
        )

        # Ensure kiwi boxes are accessible
        self.config.fake.run_sudo(
            'chmod -R 777 /home/ebcl/.kiwi_boxes', check=False)

        accel = ''
        if not self.config.kvm:
            accel = '--no-accel'

        host_is_amd64 = platform.machine().lower() in ("amd64", "x86_64")
        host_is_arm64 = platform.machine().lower() in ("arm64", "aarch64")

        cross = True
        if self.config.arch == CpuArch.AMD64 and host_is_amd64:
            cross = False
        elif self.config.arch == CpuArch.ARM64 and host_is_arm64:
            cross = False

        logging.info('Cross-build: %s', cross)

        arch = self.config.arch.get_berrymill_arch()

        cmd = None
        if use_berrymill:
            logging.info(
                'Berrymill & Kiwi KVM build of %s (KVM: %s).', appliance, self.config.kvm)

            if cross:
                cmd = f'berrymill -c {berrymill_conf} -d -a {arch} -i {appliance} ' \
                    f'--clean build --cross --box-memory 4G ' \
                    f'--target-dir {self.result_dir}'
            else:
                cmd = f'berrymill -c {berrymill_conf} -d -a {arch} -i {appliance} ' \
                    f'--clean build --box-memory 4G  --cpu qemu64-v1 {accel} ' \
                    f'--target-dir {self.result_dir}'
        else:
            logging.info('Kiwi KVM build of %s (KVM: %s).',
                         appliance, self.config.kvm)

            box_arch = self.config.arch.get_box_arch()

            cmd = f'kiwi-ng --debug --target-arch={arch} ' \
                f'--kiwi-file={os.path.basename(appliance)} ' \
                f'system boxbuild {box_arch} ' \
                f'--box ubuntu --box-memory=4G --cpu=qemu64-v1 {accel} -- ' \
                f'--description={os.path.dirname(appliance)} ' \
                f'--target-dir={self.result_dir}'

        fn_run = None
        if self.config.kvm:
            fn_run = self.config.fake.run_sudo
        else:
            fn_run = self.config.fake.run_cmd
            cmd = f'bash -c "{cmd}"'

        fn_run(f'. /build/venv/bin/activate && {cmd}')

        # Fix ownership - needed for KVM build which is executed as root
        self.config.fake.run_sudo(
            f'chown -R ebcl:ebcl {self.result_dir}', check=False)

        tar: Optional[str] = None
        pattern = '*.tar.xz'
        if self.config.result_pattern:
            pattern = self.config.result_pattern

        # search for result
        images = list(
            glob.glob(f'{self.result_dir}/**/{pattern}', recursive=True))
        if images:
            tar = os.path.join(self.result_dir, images[0])

        if not tar:
            logging.critical('Kiwi image build failed!')
            logging.debug('Apt repos: %s', self.config.apt_repos)
            return None

        # rename result archive
        ext = pattern.split('.', maxsplit=1)[-1]
        result_name = f'{self.name}.{ext}'

        logging.debug('Using result name %s...', result_name)

        result_file = os.path.join(self.config.target_dir, result_name)
        self.config.fake.run_fake(f'mv {tar} {result_file}')

        return result_file

    @log_exception()
    def create_root(
        self,
        run_scripts: bool = True
    ) -> Optional[str]:
        """ Create the root image.  """

        if self.sysroot:
            logging.info('Running build in sysroot mode.')

            # TODO: test

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
            image_file = self._build_elbe_image()
        elif self.config.type == BuildType.KIWI:
            image_file = self._build_kiwi_image()

        if not image_file:
            logging.critical('Image build failed!')
            return None

        if run_scripts:
            if self.config.name:
                name = self.config.name + '.tar'
            else:
                name = 'root.tar'
            archive_out = os.path.join(self.config.output_path, name)
            image = config_root(self.config, image_file, archive_out)

            if not image:
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

    logging.info('\n===================\n'
                 'EBcL Root Generator\n'
                 '===================\n')

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
