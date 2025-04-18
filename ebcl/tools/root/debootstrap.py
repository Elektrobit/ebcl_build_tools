""" Implementation for using debootstrap as root filesystem generator. """
import glob
import hashlib
import logging
import os

from pathlib import Path
from typing import Optional, List, Any

from ebcl.common import get_cache_folder
from ebcl.common.apt import Apt, AptDebRepo
from ebcl.common.config import Config
from ebcl.common.version import VersionDepends, VersionRelation


class DebootstrapRootGenerator:
    """ Implementation for using debootstrap as root generator. """

    def __init__(
        self,
        config: Config,
        result_dir: str,
        debootstrap_variant: str = 'minbase'
    ) -> None:
        """ Create new DebootstrapRootGenerator. """
        self.config = config
        self.result_dir = result_dir
        self.cache_folder = get_cache_folder('debootstrap')
        self.debootstrap_variant = debootstrap_variant
        self.apt_env = 'DEBIAN_FRONTEND=noninteractive TZ=Etc/UTC'
        self.apt_options = ' -o DPkg::Options::=--force-confold --allow-downgrades '

    def _get_apt_hash(self, debootstrap_hash: str) -> str:
        """ Generate a hash for the apt configuration """
        apt_config = f'{debootstrap_hash} '
        for apt in self.config.apt_repos:
            apt_config += f'{apt.id} '

        for entry in self._find_apt_host_files():
            apt_config += f'{str(entry)}'

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
            list(map(lambda vd: f'{vd.name} {vd.version_relation} {vd.version} ', self.config.packages)))
        packages += f' {apt_hash}'

        hf = hashlib.md5(packages.encode('utf-8'))

        # Extend hash for apt config
        apt_config = self._find_apt_host_files()
        for ac in apt_config:
            for fp in glob.glob(f'{ac}/*'):
                if os.path.isfile(fp):
                    with open(fp, 'rb') as f:
                        hf.update(f.read())

        return hf.hexdigest()

    def _generate_apt_config(self) -> None:
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

                # Copy key if available
                (key_pub_file, key_gpg_file) = apt.get_key_files()
                if key_pub_file:
                    os.remove(key_pub_file)

                trusted = False
                if key_gpg_file and os.path.isfile(key_gpg_file):
                    fake.run_sudo(
                        f'cp {key_gpg_file} {apt_key_dir}',
                        cwd=self.config.target_dir,
                        check=True
                    )
                else:
                    logging.warning('No GPG key for %s, will trust the repo!', apt)
                    trusted = True

                f.write(f'{apt.repo.sources_entry(trusted=trusted)}\n\n')

        fake.run_sudo(
            f'cp {apt_sources} {apt_sources_target}',
            cwd=self.config.target_dir,
            check=True
        )

        # Copy host files to allow adding additional package manager config
        # and overwriting of generated apt config.
        if self.config.host_files:
            # Copy host files to target_dir folder
            logging.info('Copy apt config to target dir...')
            for entry in self._find_apt_host_files():
                self.config.fh.copy_files([entry], self.config.target_dir)

    def _find_apt_host_files(self) -> List[Any]:
        """ Check for host files affecting the apt behavior. """
        apt_config = []

        for entry in self.config.host_files:
            dest: str = entry.get('destination', '')
            src: str = entry.get('source', '')

            apt_path = 'etc/apt'
            if dest == 'etc' or dest == 'etc/':
                apt_path = 'apt'
            elif dest == 'etc/apt' or dest == 'etc/apt/':
                apt_path = ''

            if src.endswith('*'):
                src = src[:-1]

            test_path = os.path.join(src, apt_path)

            if os.path.isdir(test_path):
                logging.debug("Found apt config %s.", entry)
                apt_config.append(entry)

        return apt_config

    def _copy_credentials(self):
        """ copy the user credential for apt repo """
        if not next(self.config.cred_dir.glob("*.conf"), None):
            return

        self.config.fake.run_sudo(
            f'install -m 600 {self.config.cred_dir}/*.conf {self.config.target_dir}/etc/apt/auth.conf.d/',
            check=True
        )

    def _remove_credentials(self):
        """ cleanup user credentials """
        if not next(self.config.cred_dir.glob("*.conf"), None):
            return

        self.config.fake.run_sudo(
            f'rm {self.config.target_dir}/etc/apt/auth.conf.d/*',
            check=True
        )

    def _find_deboostrap_repo(self) -> tuple[Apt, AptDebRepo] | tuple[None, None]:
        """ Find apt repository for debootstrap. """
        for apt in self.config.apt_repos:
            repo: AptDebRepo | None = apt.deb_repo
            if repo and repo.dist == self.config.primary_distro:
                if 'main' in repo.components:
                    return (apt, repo)
        return (None, None)

    def _update_ca_certificates(self) -> None:
        """
        Update ca-certificates
        There is a chance that this cannot be done using apt update && apt upgrade,
        because the sources may list a repository, that uses a root certificate for signing
        that is not yet installed on the target system (because the ca-certificates package in debootrap is too old).
        """

        logging.info("Trying to update ca-certificates")
        ca_pkg = self.config.proxy.find_package(VersionDepends("ca-certificates", None, None, None, self.config.arch))
        if not ca_pkg:
            logging.warning("No ca-certificates package in sources found, skipping update.")
            return

        ca_pkg = self.config.proxy.download_package(self.config.arch, ca_pkg, location=self.config.target_dir)
        local_file_str = ca_pkg and ca_pkg.local_file or None
        if not local_file_str:
            logging.error("Unable to download ca-certificates package")
            return
        local_file = Path(local_file_str)
        local_name = local_file.name

        self.config.fake.run_chroot(
            f'bash -c "{self.apt_env} dpkg --install --skip-same-version /{local_name}"',
            self.config.target_dir
        )
        local_file.unlink()

    def _run_debootstrap(self) -> bool:
        """ Run debootstrap and store result in cache. """
        fake = self.config.fake

        apt, repo = self._find_deboostrap_repo()
        if apt is None or repo is None:
            logging.critical('No apt repo for deboostrap found!')
            return False

        keyring = ''
        (pub, gpg) = apt.get_key_files()
        if pub:
            os.remove(pub)

        if gpg is not None:
            keyring = f' --keyring={gpg} '

        user_flags = ''
        if self.config.debootstrap_flags:
            user_flags = self.config.debootstrap_flags

        fake.run_sudo(
            f'debootstrap --arch={self.config.arch} {keyring} {user_flags} --variant={self.debootstrap_variant} '
            f'{repo.dist} {self.config.target_dir} '
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
            self._copy_credentials()
            self._update_ca_certificates()

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
            self._remove_credentials()

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
            self._copy_credentials()

            # Update root
            fake.run_chroot(
                f'bash -c "{self.apt_env} apt update"',
                chroot=self.config.target_dir,
                check=True
            )

            # Install additional packages
            packages = ''
            for p in self.config.packages:
                if p.version_relation and p.version_relation == VersionRelation.EXACT:
                    packages += f'{p.name}={p.version} '
                else:
                    packages += f'{p.name} '

            no_recommends = ""
            if not self.config.install_recommends:
                no_recommends = "--no-install-recommends "
            fake.run_chroot(
                f'bash -c "{self.apt_env} apt install -y {self.apt_options}  {no_recommends}{packages}"',
                chroot=self.config.target_dir,
                check=True
            )

        except Exception as e:
            logging.critical('Error while generating root! %s', str(e))
            return False
        finally:
            self._remove_credentials()

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
            logging.debug('Cache hit for %s: %s', archive_hash, archive)
            return True
        logging.debug('Cache miss for %s.', archive_hash)
        return False

    def _run_base_config_and_tar(self, name: str) -> Optional[str]:
        """ Apply very basic config like root password and create result tarball. """
        fake = self.config.fake
        config = self.config

        try:
            self._copy_credentials()

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
            return None
        finally:
            self._remove_credentials()

            # Cleanup
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

        logging.debug('debootstrap hash: %s', debootstrap_hash)
        logging.debug('apt hash: %s', apt_hash)
        logging.debug('package hash: %s', package_hash)

        run_debootstrap = not (
            self._has_cache_archive(debootstrap_hash)
            or self._has_cache_archive(apt_hash)
            or self._has_cache_archive(package_hash)
        )
        run_update = not (self._has_cache_archive(apt_hash) or self._has_cache_archive(package_hash))
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
            if self.config.packages:
                if not self._run_install_packages(apt_hash):
                    return None
        else:
            self._extract_form_cache(package_hash)

        return self._run_base_config_and_tar(name)
