""" Implementation for using debootstrap as root filesystem generator. """
import logging
import os
import hashlib

from typing import Optional

from ebcl.common import get_cache_folder
from ebcl.common.apt import Apt
from ebcl.common.config import Config


class DebootstrapRootGenerator:
    """ Implementation for using debootstrap as root generator. """

    def __init__(
        self,
        config: Config,
        result_dir: str,
        debootstrap_variant: str = 'minbase'
    ):
        """ Create new DebootstrapRootGenerator. """
        self.config = config
        self.result_dir = result_dir
        self.cache_folder = get_cache_folder('debootstrap')
        self.debootstrap_variant = debootstrap_variant
        self.apt_env = 'DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC'

    def _get_apt_hash(self, debootstrap_hash: str) -> str:
        """ Generate a hash for the apt configuration """
        apt_config = f'{debootstrap_hash} '
        for apt in self.config.apt_repos:
            components = ' '.join(apt.components)
            apt_config += f'{apt.url} {apt.distro} {components} '

        return hashlib.md5(apt_config.encode('utf-8')).digest().hex()

    def _get_debootstrap_hash(self) -> str:
        """ Generate hash for the debootstrap configuration. """
        params = f'{self.config.arch} {self.debootstrap_variant} ' \
            f'{self.config.primary_distro} {self._find_deboostrap_repo()} ' \
            f'{self.config.debootstrap_flags}'

        return hashlib.md5(params.encode('utf-8')).digest().hex()

    def _get_package_hash(self, apt_hash: str) -> str:
        """ Generate hash for the selected additional packages. """
        packages = ' '.join(
            list(map(lambda vd: vd.name, self.config.packages)))
        packages += f' {apt_hash}'

        return hashlib.md5(packages.encode('utf-8')).digest().hex()

    def _generate_apt_config(self):
        """ Generate a apt sources.list. """
        apt_conf = os.path.join(self.config.target_dir, 'etc', 'apt')
        apt_key_dir = os.path.join(apt_conf, 'trusted.gpg.d', )
        apt_sources = os.path.join(self.result_dir, 'sources.list')
        apt_sources_target = os.path.join(apt_conf, 'sources.list')

        fake = self.config.fake

        fake.run_sudo(
            f'mkdir -p {apt_conf}',
            cwd=self.config.target_dir,
            check=True
        )

        fake.run_sudo(
            f'mkdir -p {apt_key_dir}',
            cwd=self.config.target_dir,
            check=True
        )

        with open(apt_sources, mode='w', encoding='utf-8') as f:
            for apt in self.config.apt_repos:
                logging.info('Adding apt repo %s...', str(apt))
                components = ' '.join(apt.components)

                (key_pub_file, key_gpg_file) = apt.get_key_files()

                if key_pub_file:
                    # the armored key is not needed
                    os.remove(key_pub_file)

                distro = apt.distro
                if distro is not None:
                    # Flat repo
                    distro = './'

                if key_gpg_file:
                    fake.run_sudo(
                        f'cp {key_gpg_file} {apt_key_dir}',
                        cwd=self.config.target_dir,
                        check=True
                    )
                    f.write(
                        f'deb [arch={apt.arch}] {apt.url} {distro} {components}\n\n')
                else:
                    logging.warning(
                        'No key for repository %s, will blindly trust the repo!', str(apt))
                    f.write(
                        f'deb [trusted=yes arch={apt.arch}] {apt.url} {distro} {components}\n\n')

        fake.run_sudo(
            f'cp {apt_sources} {apt_sources_target}',
            cwd=self.config.target_dir,
            check=True
        )

    def _mount_special_folders(self):
        """ Mount special file systems to chroot folder. """
        fake = self.config.fake

        # Prepare for chroot.
        fake.run_sudo(
            f'mount -o bind /dev {self.config.target_dir}/dev',
            cwd=self.config.target_dir,
            check=True
        )
        fake.run_sudo(
            f'mount -o bind /dev/pts {self.config.target_dir}/dev/pts',
            cwd=self.config.target_dir,
            check=True
        )
        fake.run_sudo(
            f'mount -t sysfs /sys {self.config.target_dir}/sys',
            cwd=self.config.target_dir,
            check=True
        )
        fake.run_sudo(
            f'mount -t proc /proc {self.config.target_dir}/proc',
            cwd=self.config.target_dir,
            check=True
        )

    def _unmount_special_folders(self):
        """ Unmount special file systems from chroot folder. """
        fake = self.config.fake

        # Unmount special folders.
        fake.run_sudo(
            f'umount {self.config.target_dir}/dev/pts',
            cwd=self.config.target_dir,
            check=False
        )
        fake.run_sudo(
            f'umount {self.config.target_dir}/dev',
            cwd=self.config.target_dir,
            check=False
        )
        fake.run_sudo(
            f'umount {self.config.target_dir}/sys',
            cwd=self.config.target_dir,
            check=False
        )
        fake.run_sudo(
            f'umount {self.config.target_dir}/proc',
            cwd=self.config.target_dir,
            check=False
        )

    def _find_deboostrap_repo(self) -> Optional[Apt]:
        """ Find apt repository for debootstrap. """
        for apt in self.config.apt_repos:
            if apt.distro == self.config.primary_distro:
                if 'main' in apt.components:
                    return apt
        return None

    def _run_debootstrap(self) -> bool:
        """ Run debootstrap and store result in cache. """
        fake = self.config.fake

        repo = self._find_deboostrap_repo()
        if repo is None:
            logging.critical('No apt repo for deboostrap found!')
            return False

        keyring = ''
        (pub, gpg) = repo.get_key_files()
        if pub:
            os.remove(pub)

        if gpg is not None:
            keyring = f' --keyring={gpg} '

        user_flags = ''
        if self.config.debootstrap_flags:
            user_flags = self.config.debootstrap_flags

        fake.run_sudo(
            f'debootstrap --arch={self.config.arch} {keyring} {user_flags} --variant={self.debootstrap_variant} '
            f'{repo.distro} {self.config.target_dir} '
            f'{repo.url}',
            cwd=self.config.target_dir,
            check=True
        )

        cache_archive = f'{self._get_debootstrap_hash()}.tar'

        # Create cache archive.
        ao: Optional[str] = self.config.fh.pack_root_as_tarball(
            output_dir=self.cache_folder,
            archive_name=cache_archive,
            root_dir=self.config.target_dir,
            use_sudo=not self.config.use_fakeroot
        )

        if not ao:
            logging.error(
                'Creating cache archive failed! Cache folder: %s, archive: %s', self.cache_folder, cache_archive)
        else:
            logging.info('Debootstrap cache archive created: %s', ao)

        return True

    def _run_update(self, debootstrap_hash: Optional[str]) -> bool:
        """ Update the packages in the root using apt. """
        fake = self.config.fake

        self._generate_apt_config()

        try:
            self._mount_special_folders()

            fake.run_sudo(
                f'cp /proc/mounts {self.config.target_dir}/etc/mtab',
                cwd=self.config.target_dir,
                check=True
            )

            # Copy resolv.conf to enable name resolution.
            fake.run_sudo(
                f'cp /etc/resolv.conf {self.config.target_dir}/etc/resolv.conf',
                cwd=self.config.target_dir,
                check=True
            )

            # Update root
            fake.run_chroot(
                f'bash -c "{self.apt_env} apt update"',
                chroot=self.config.target_dir,
                check=True
            )

            fake.run_chroot(
                f'bash -c "{self.apt_env} apt upgrade -y"',
                chroot=self.config.target_dir,
                check=True
            )

        except Exception as e:
            logging.critical('Error while generating root! %s', str(e))
            return False
        finally:
            self._unmount_special_folders()

        if debootstrap_hash is not None:
            cache_archive = f'{self._get_apt_hash(debootstrap_hash)}.tar'

            # Create cache archive.
            ao: Optional[str] = self.config.fh.pack_root_as_tarball(
                output_dir=self.cache_folder,
                archive_name=cache_archive,
                root_dir=self.config.target_dir,
                use_sudo=not self.config.use_fakeroot
            )

            if not ao:
                logging.error(
                    'Creating cache archive failed! Cache folder: %s, archive: %s', self.cache_folder, cache_archive)
            else:
                logging.info('Update cache archive created: %s', ao)
        else:
            logging.info('Not creating and cache archive.')

        return True

    def _run_install_packages(self, apt_hash: Optional[str]) -> bool:
        """ Update the packages in the root using apt. """
        fake = self.config.fake

        try:
            self._mount_special_folders()

            # Update root
            fake.run_chroot(
                f'bash -c "{self.apt_env} apt update"',
                chroot=self.config.target_dir,
                check=True
            )

            fake.run_chroot(
                f'bash -c "{self.apt_env} apt upgrade -y"',
                chroot=self.config.target_dir,
                check=True
            )

            # Install additional packages
            packages = ' '.join(
                list(map(lambda vd: vd.name, self.config.packages)))
            fake.run_chroot(
                f'bash -c "{self.apt_env} apt install -y {packages}"',
                chroot=self.config.target_dir,
                check=True
            )

        except Exception as e:
            logging.critical('Error while generating root! %s', str(e))
            return False
        finally:
            self._unmount_special_folders()

        if apt_hash is not None:
            cache_archive = f'{self._get_package_hash(apt_hash)}.tar'

            # Create cache archive.
            ao: Optional[str] = self.config.fh.pack_root_as_tarball(
                output_dir=self.cache_folder,
                archive_name=cache_archive,
                root_dir=self.config.target_dir,
                use_sudo=not self.config.use_fakeroot
            )

            if not ao:
                logging.error(
                    'Creating package archive failed! Cache folder: %s, archive: %s', self.cache_folder, cache_archive)
            else:
                logging.info('Package cache archive created: %s', ao)
        else:
            logging.info('Not creating and cache archive.')

        return True

    def _extract_form_cache(self, archive_hash: str) -> bool:
        """ Get cached root content. """
        archive = os.path.join(self.cache_folder, f'{archive_hash}.tar')
        result = self.config.fh.extract_tarball(
            archive, self.config.target_dir, use_sudo=not self.config.use_fakeroot)
        return result is not None

    def _has_cache_archive(self, archive_hash: str) -> bool:
        """ Check if cache archive exists. """
        archive = os.path.join(self.cache_folder, f'{archive_hash}.tar')
        if os.path.exists(archive):
            return True
        return False

    def _run_base_config_and_tar(self, name: str) -> Optional[str]:
        """ Apply very basic config like root password and create result tarball. """
        fake = self.config.fake
        config = self.config

        try:
            self._mount_special_folders()

            # Copy resolv.conf to enable name resolution.
            fake.run_sudo(
                f'cp /etc/resolv.conf {config.target_dir}/etc/resolv.conf',
                cwd=config.target_dir,
                check=True
            )

            # Set root password
            if config.root_password:
                fake.run_chroot(
                    f'bash -c "echo \"root:{config.root_password}\" | chpasswd"',
                    chroot=config.target_dir,
                    check=True
                )

            # Set the hostname
            if config.hostname:
                hostname = config.hostname
                if config.domain:
                    hostname = f'{hostname}.{config.domain}'
                fake.run_chroot(
                    f'bash -c "echo \"{hostname}\" > /etc/hostname"',
                    chroot=config.target_dir,
                    check=True
                )

            # Update root
            fake.run_chroot(
                f'bash -c "{self.apt_env} apt update"',
                chroot=config.target_dir,
                check=True
            )

            fake.run_chroot(
                f'bash -c "{self.apt_env} apt upgrade -y"',
                chroot=config.target_dir,
                check=True
            )

        except Exception as e:
            logging.critical('Error while generating root! %s', str(e))
            self._unmount_special_folders()
            return None
        finally:
            self._unmount_special_folders()

            # Cleanup
            fake.run_sudo(
                f'rm {config.target_dir}/etc/resolv.conf',
                cwd=config.target_dir,
                check=False
            )

            fake.run_sudo(
                f'rm {config.target_dir}/etc/mtab',
                cwd=config.target_dir,
                check=False
            )

            fake.run_sudo(
                f'rm -rf {config.target_dir}/var/lib/apt/lists/*',
                cwd=config.target_dir,
                check=True
            )
            fake.run_sudo(
                f'rm -rf {config.target_dir}/var/cache/apt/*',
                cwd=config.target_dir,
                check=True
            )
            fake.run_sudo(
                f'rm -rf {config.target_dir}/usr/share/man/*',
                cwd=config.target_dir,
                check=True
            )

        # Create archive.
        ao: Optional[str] = config.fh.pack_root_as_tarball(
            output_dir=self.result_dir,
            archive_name=f'{name}.tar',
            root_dir=config.target_dir,
            use_sudo=not config.use_fakeroot
        )

        if not ao:
            logging.critical('Repacking root failed!')
            return None

        return ao

    def build_debootstrap_image(self, name: str) -> Optional[str]:
        """ Build the root tarball. """

        debootstrap_hash = self._get_debootstrap_hash()
        apt_hash = self._get_apt_hash(debootstrap_hash)
        package_hash = self._get_package_hash(apt_hash)

        run_debootstrap = not (self._has_cache_archive(debootstrap_hash) or self._has_cache_archive(
            apt_hash) or self._has_cache_archive(package_hash))
        run_update = not (self._has_cache_archive(apt_hash)
                          or self._has_cache_archive(package_hash))
        run_packages = not self._has_cache_archive(package_hash)

        if run_debootstrap:
            if not self._run_debootstrap():
                return None

        if run_update:
            self._extract_form_cache(debootstrap_hash)
            if not self._run_update(debootstrap_hash):
                return None

        if run_packages:
            self._extract_form_cache(apt_hash)
            if not self._run_install_packages(apt_hash):
                return None
        else:
            self._extract_form_cache(package_hash)

        return self._run_base_config_and_tar(name)
