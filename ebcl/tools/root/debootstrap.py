""" Implemenation for using debootstrap as root filesystem generator. """
import logging
import os

from typing import Optional, Any

from ebcl.common.config import Config
from ebcl.common.templates import render_template


def _generate_multistrap_config(
    config: Config,
    name: str,
    result_dir: str
) -> Optional[str]:
    """ Generate a multistrap repo config. """
    params: dict[str, Any] = {}

    params['repo_url'] = config.primary_repo
    params['distro'] = config.primary_distro
    params['repo_keyring_package'] = config.primary_key_deb

    if config.template is None:
        template = os.path.join(os.path.dirname(__file__), 'multistrap.cfg')
    else:
        template = config.template

    (config_file, _content) = render_template(
        template_file=template,
        params=params,
        generated_file_name=f'{name}.multistrap.cfg',
        results_folder=result_dir,
        template_copy_folder=result_dir
    )

    return config_file


def _generate_apt_config(
    config: Config,
    result_dir: str,
) -> Optional[str]:
    """ Generate a apt sources.list. """
    apt_conf = os.path.join(config.target_dir, 'etc', 'apt')
    apt_key_dir = os.path.join(apt_conf, 'trusted.gpg.d', )
    apt_sources = os.path.join(result_dir, 'sources.list')
    apt_sources_target = os.path.join(apt_conf, 'sources.list')

    fake = config.fake

    fake.run_sudo(
        f'mkdir -p {apt_conf}',
        cwd=config.target_dir,
        check=True
    )

    fake.run_sudo(
        f'mkdir -p {apt_key_dir}',
        cwd=config.target_dir,
        check=True
    )

    with open(apt_sources, mode='w', encoding='utf-8') as f:
        for apt in config.apt_repos:
            components = ' '.join(apt.components)
            f.write(f'deb {apt.url} {apt.distro} {components}\n\n')

            (_key_pub_file, key_gpg_file) = apt.get_key_files()
            fake.run_sudo(
                f'cp {key_gpg_file} {apt_key_dir}',
                cwd=config.target_dir,
                check=True
            )

    fake.run_sudo(
        f'cp {apt_sources} {apt_sources_target}',
        cwd=config.target_dir,
        check=True
    )

    return apt_sources


def build_debootstrap_image(
    config: Config,
    name: str,
    result_dir: str
) -> Optional[str]:
    config_file = _generate_multistrap_config(config, name, result_dir)

    if not config_file:
        logging.critical('Generating the mutlistrap configuration failed.')
        return None

    fake = config.fake

    fake.run_sudo(
        f'multistrap -a {config.arch} -d {config.target_dir} -f {config_file}',
        cwd=config.target_dir,
        check=True
    )

    sources = _generate_apt_config(config, result_dir)

    if not sources:
        logging.critical('Generating the apt sources failed.')
        return None

    # Prepare for chroot.
    fake.run_sudo(
        f'mount -o bind /dev {config.target_dir}/dev',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'mount -o bind /dev/pts {config.target_dir}/dev/pts',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'mount -t sysfs /sys {config.target_dir}/sys',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'mount -t proc /proc {config.target_dir}/proc',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'cp /proc/mounts {config.target_dir}/etc/mtab',
        cwd=config.target_dir,
        check=True
    )

    # Copy resolv.conf to enable name resolution.
    fake.run_sudo(
        f'cp /etc/resolv.conf {config.target_dir}/etc/resolv.conf',
        cwd=config.target_dir,
        check=True
    )

    # Update root
    apt_env = 'DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC'
    fake.run_chroot(
        f'bash -c "{apt_env} apt update"',
        chroot=config.target_dir,
        check=True
    )
    fake.run_chroot(
        f'bash -c "{apt_env} apt upgrade -y"',
        chroot=config.target_dir,
        check=True
    )

    # Install additional packages
    packages = ' '.join(list(map(lambda vd: vd.name, config.packages)))
    fake.run_chroot(
        f'bash -c "{apt_env} apt install -y {packages}"',
        chroot=config.target_dir,
        check=True
    )

    # Cleanup
    fake.run_sudo(
        'rm -rf {config.target_dir}/var/lib/apt/lists/*',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        'rm -rf {config.target_dir}/var/cache/apt/*',
        cwd=config.target_dir,
        check=True
    )

    # Unmount special folders.
    fake.run_sudo(
        f'umount {config.target_dir}/dev/pts',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'umount {config.target_dir}/dev',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'umount {config.target_dir}/sys',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'umount {config.target_dir}/proc',
        cwd=config.target_dir,
        check=True
    )
    fake.run_sudo(
        f'rm {config.target_dir}/etc/mtab',
        cwd=config.target_dir,
        check=True
    )

    # Create archive.
    ao: Optional[str] = config.fh.pack_root_as_tarball(
        output_dir=result_dir,
        archive_name=f'{name}.tar',
        root_dir=config.target_dir,
        use_sudo=not config.use_fakeroot
    )

    if not ao:
        logging.critical('Repacking root failed!')
        return None

    return ao
