""" Implemenation for using kiwi as root filesystem generator. """
import glob
import logging
import os
import platform
import shutil

from pathlib import Path
from typing import Optional, Any

import yaml

from ebcl.common.config import Config
from ebcl.common.templates import render_template

from ebcl.common.types.cpu_arch import CpuArch


def _generate_kiwi_repo_config(config: Config) -> Optional[str]:
    """ Generate repos as kiwi XML tags. """
    repos = ''

    cnt = 0
    for apt in config.apt_repos:
        repo = apt.deb_repo
        if not repo:
            logging.error('Kiwi can only handle noraml debian repositories, not flat repos. Skipping repo!')
            continue

        if apt.key_url or apt.key_gpg:
            logging.warning(
                'Apt repository key checks are not supported for kiwi-only build!')

        for component in repo.components:
            bootstrap = 'false'
            if cnt == 0:
                bootstrap = 'true'

            cmp_id = f'{cnt}_{repo.dist}_{component}'
            repos += f'<repository alias="{cmp_id}" type="apt-deb" ' \
                f'distribution="{repo.dist}" components="{component}" ' \
                f'use_for_bootstrap="{bootstrap}" ' \
                'repository_gpgcheck="false" >\n'
            repos += f'    <source path = "{repo.url}" />\n'
            repos += '</repository>\n\n'

            cnt += 1

    return repos


def _generate_kiwi_image(
    config: Config,
    name: str,
    result_dir: str,
    generate_repos: bool = False
) -> Optional[str]:
    """ Generate a kiwi image description. """

    if not config.apt_repos:
        logging.critical('No apt repositories defined!')
        return None

    bootstrap_package = None
    if config.use_bootstrap_package:
        bootstrap_package = config.bootstrap_package
        if not bootstrap_package:
            bootstrap_package = 'bootstrap-root-ubuntu-jammy'
            logging.info('No bootstrap paackage provided. '
                         'Using default package %s.', bootstrap_package)

    params: dict[str, Any] = {}

    if generate_repos:
        kiwi_repos = _generate_kiwi_repo_config(config)
        if kiwi_repos:
            params['repos'] = kiwi_repos

    params['arch'] = config.arch.get_kiwi_arch()

    if config.image_version:
        params['version'] = config.image_version
    else:
        params['version'] = '1.0.0'

    if config.root_password:
        params['root_password'] = config.root_password
    else:
        params['root_password'] = ''

    if config.packages:
        package_names = []
        for vd in config.packages:
            package_names.append(vd.name)
        params['packages'] = package_names

    if bootstrap_package:
        params['bootstrap_package'] = bootstrap_package

    if config.bootstrap:
        package_names = []
        for vd in config.bootstrap:
            package_names.append(vd.name)
        params['bootstrap'] = package_names

    if config.template:
        template = config.template
    else:
        template = os.path.join(os.path.dirname(__file__), 'root.kiwi')

    (image_file, _content) = render_template(
        template_file=template,
        params=params,
        generated_file_name=f'{name}.image.kiwi',
        results_folder=result_dir,
        template_copy_folder=result_dir
    )

    if not image_file:
        logging.critical('Rendering image description failed!')
        return None

    logging.debug('Generated image stored as %s', image_file)

    return image_file


def _generate_berrymill_config(
    config: Config,
    result_dir: str
) -> Optional[str]:
    """ Generate a berrymill.conf. """

    berrymill_conf: dict[str, Any] = {}

    berrymill_conf['use-global-repos'] = False
    berrymill_conf['boxed_plugin_conf'] = '/etc/berrymill/kiwi_boxed_plugin.yml'
    berrymill_conf['repos'] = {}
    berrymill_conf['repos']['release'] = {}

    cnt = 1
    for apt in config.apt_repos:
        repo = apt.deb_repo
        if not repo:
            logging.error('Kiwi can only handle noraml debian repositories, not flat repos. Skipping repo!')
            continue

        apt_repo_key = None
        (pub, apt_repo_key) = apt.get_key_files(result_dir)
        if pub:
            os.remove(pub)

        if not apt_repo_key:
            logging.error('No key found for %s, skipping repo!', apt)
            continue

        arch = str(repo.arch)

        if arch not in berrymill_conf['repos']['release']:
            berrymill_conf['repos']['release'][arch] = {}

        for component in repo.components:
            cmp_id = f'{cnt}_{repo.dist}_{component}'
            cnt += 1

            berrymill_conf['repos']['release'][arch][cmp_id] = {
                'url': repo.url,
                'type': 'apt-deb',
                'key': f'file://{apt_repo_key}',
                'name': repo.dist,
                'components': component
            }

    config_file = os.path.join(result_dir, 'berrymill.conf')

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


def build_kiwi_image(
    config: Config,
    image_name: str,
    result_dir: str
) -> Optional[str]:
    """ Run kiwi image build. """

    berrymill_conf = None
    use_berrymill = config.use_berrymill

    if use_berrymill:
        berrymill_conf = config.berrymill_conf
        if berrymill_conf:
            berrymill_conf = config.berrymill_conf
        else:
            logging.info('Generating the berrymill.conf...')
            berrymill_conf = _generate_berrymill_config(config, result_dir)
            if not berrymill_conf:
                logging.critical('Generating a berrymill.conf failed!')
                return None

    if not berrymill_conf:
        if use_berrymill:
            logging.warning(
                'No berrymill.conf, falling back to kiwi-only build.')
        use_berrymill = False

    if config.image:
        image: Optional[str] = config.image
    else:
        generate_repos = not use_berrymill
        image = _generate_kiwi_image(
            config, image_name, result_dir, generate_repos)

    if not image:
        logging.critical('No kiwi image description found!')
        return None

    if not os.path.isfile(image):
        logging.critical('Image %s not found!', image)
        return None

    logging.debug('Berrymill.conf: %s', berrymill_conf)

    appliance = os.path.join(result_dir, image)

    if os.path.abspath(appliance) != os.path.abspath(image):
        shutil.copy(image, appliance)

    kiwi_scripts = config.kiwi_scripts
    kiwi_root_overlays = config.kiwi_root_overlays

    if config.use_kiwi_defaults:
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
    config.fh.copy_files(
        kiwi_script_files, os.path.dirname(appliance))

    root_folder = os.path.join(os.path.dirname(appliance), 'root')
    config.fake.run_cmd(f'mkdir -p {root_folder}')

    for overlay in kiwi_root_overlays:
        config.fh.copy_file(
            f'{overlay}/*',
            f'{root_folder}',
            environment=None)

    # Copy other .kiwi files
    config.fh.copy_file(
        f'{os.path.dirname(image)}/*.kiwi',
        os.path.dirname(appliance)
    )

    # Ensure kiwi boxes are accessible
    config.fake.run_sudo(
        'mkdir -p /home/ebcl/.kiwi_boxes', check=False)
    config.fake.run_sudo(
        'chmod -R 777 /home/ebcl/.kiwi_boxes', check=False)

    accel = ''
    if not config.kvm:
        accel = '--no-accel'

    host_is_amd64 = platform.machine().lower() in ("amd64", "x86_64")
    host_is_arm64 = platform.machine().lower() in ("arm64", "aarch64")

    cross = True
    if config.arch == CpuArch.AMD64 and host_is_amd64:
        cross = False
    elif config.arch == CpuArch.ARM64 and host_is_arm64:
        cross = False

    logging.info('Cross-build: %s', cross)

    arch = config.arch.get_berrymill_arch()

    cmd = None
    if use_berrymill:
        logging.info(
            'Berrymill & Kiwi KVM build of %s (KVM: %s).', appliance, config.kvm)

        if cross:
            cmd = f'berrymill -c {berrymill_conf} -d -a {arch} -i {appliance} ' \
                f'--clean build --cross --box-memory 4G ' \
                f'--target-dir {result_dir}'
        else:
            cmd = f'berrymill -c {berrymill_conf} -d -a {arch} -i {appliance} ' \
                f'--clean build --box-memory 4G  {accel} ' \
                f'--target-dir {result_dir}'
    else:
        logging.info('Kiwi KVM build of %s (KVM: %s).',
                     appliance, config.kvm)

        box_arch = config.arch.get_box_arch()

        cmd = f'kiwi-ng --debug --target-arch={arch} ' \
            f'--kiwi-file={os.path.basename(appliance)} ' \
            f'system boxbuild {box_arch} ' \
            f'--box ubuntu --box-memory=4G {accel} -- ' \
            f'--description={os.path.dirname(appliance)} ' \
            f'--target-dir={result_dir}'

    fn_run = None
    if config.kvm:
        fn_run = config.fake.run_sudo
    else:
        fn_run = config.fake.run_cmd
        cmd = f'bash -c "{cmd}"'

    fn_run(f'. /build/venv/bin/activate && {cmd}')

    # Fix ownership - needed for KVM build which is executed as root
    config.fake.run_sudo(
        f'chown -R ebcl:ebcl {result_dir}', check=False)

    tar: Optional[str] = None
    pattern = '*.tar.xz'
    if config.result_pattern:
        pattern = config.result_pattern

    # search for result
    images = list(
        glob.glob(f'{result_dir}/**/{pattern}', recursive=True))
    if images:
        tar = os.path.join(result_dir, images[0])

    if not tar:
        logging.critical('Kiwi image build failed!')
        logging.debug('Apt repos: %s', config.apt_repos)
        return None

    # rename result archive
    ext = pattern.split('.', maxsplit=1)[-1]
    result_name = f'{image_name}.{ext}'

    logging.debug('Using result name %s...', result_name)

    result_file = os.path.join(config.target_dir, result_name)
    config.fake.run_fake(f'mv {tar} {result_file}')

    return result_file
