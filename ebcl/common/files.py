""" Files and scripts helpers. """
import glob
import logging
import os
import tempfile

from pathlib import Path
from typing import Optional, Tuple, Any

from . import ImplementationError

from .fake import Fake

from .types.environment_type import EnvironmentType


class TarNotFound(Exception):
    """ Raised if the tar file to extract was not found. """


class TargetDirNotInitialized(Exception):
    """ Raised if the target dir is needed but not set. """


class FileNotFound(Exception):
    """ Raised if a command returns and returncode which is not 0. """


def sub_output_path(path: str, output_path: Optional[str] = None) -> str:
    """ Replace $$RESULTS$$ with output path.  """
    if '$$RESULTS$$' in path:
        if not output_path:
            raise ImplementationError('output_path missing!')

        if path.endswith('$$RESULTS$$'):
            path = output_path
        else:
            parts = path.split('$$RESULTS$$/')
            path = os.path.abspath(os.path.join(output_path, parts[-1]))

    return path


class Files:
    """ Files and scripts helpers. """

    def __init__(self, fake: Fake, target_dir: Optional[str] = None) -> None:
        self.target_dir: Optional[str] = target_dir
        self.fake: Fake = fake

    def _run_cmd(
        self, cmd: str,
        env: Optional[EnvironmentType],
        cwd: Optional[str] = None,
        check: bool = True,
        capture_output=True
    ) -> Optional[Tuple[Optional[str], Optional[str], int]]:
        """ Run the cmd using fake. """
        if env == EnvironmentType.FAKEROOT:
            return self.fake.run_fake(cmd, cwd=cwd, check=check, capture_output=capture_output)
        elif env == EnvironmentType.SUDO:
            return self.fake.run_sudo(cmd, cwd=cwd, check=check, capture_output=capture_output)
        elif env == EnvironmentType.CHROOT:
            chroot_dir: Optional[str] = None
            if cwd:
                logging.info('Using cwd %s as chroot dir.', cwd)
                chroot_dir = cwd
            else:
                chroot_dir = self.target_dir

            if not chroot_dir:
                raise TargetDirNotInitialized()

            cmd = cmd.replace(chroot_dir, '')

            return self.fake.run_chroot(cmd, chroot=chroot_dir, check=check, capture_output=capture_output)
        elif env == EnvironmentType.SHELL or env is None:
            return self.fake.run_cmd(cmd, cwd=cwd, check=check, capture_output=capture_output)

    def copy_files(
        self,
        files: list[dict[str, Any]],
        target_dir: Optional[str] = None,
        fix_ownership: bool = False
    ):
        """ Copy files. """
        # TODO: test
        logging.debug('Files: %s', files)

        for entry in files:
            logging.info('Processing entry: %s', entry)

            source = entry.get('source', None)
            if not source:
                logging.error(
                    'Invalid file entry %s, source is missing!', entry)
                continue

            src: str = source

            if not target_dir:
                target_dir = self.target_dir

            if not target_dir:
                raise TargetDirNotInitialized()

            dst = target_dir
            file_dest = entry.get('destination', None)
            if file_dest:
                dst = os.path.join(dst, file_dest)

            mode: str = entry.get('mode', None)
            uid: int = int(entry.get('uid', 0))
            gid: int = int(entry.get('gid', 0))

            logging.debug('Copying files %s', src)

            copied_files = self.copy_file(
                src=src,
                dst=dst,
                uid=uid,
                gid=gid,
                mode=mode,
                delete_if_exists=True,
                fix_ownership=fix_ownership
            )

            if not copied_files:
                raise FileNotFound(f'File {src} not found!')

    def copy_file(
        self,
        src: str,
        dst: str,
        environment: Optional[EnvironmentType] = EnvironmentType.SUDO,
        uid: Optional[int] = None,
        gid: Optional[int] = None,
        mode: Optional[str] = None,
        move: bool = False,
        delete_if_exists: bool = False,
        fix_ownership: bool = False
    ) -> list[str]:
        """ Copy file or dir to target environment"""
        files: list[str] = []

        if environment == EnvironmentType.CHROOT:
            if not self.target_dir:
                raise TargetDirNotInitialized()

            if dst.startswith('/'):
                dst = dst[1:]
            dst = os.path.abspath(os.path.join(self.target_dir, dst))

            if src.startswith('/'):
                src = src[1:]
            matches = glob.glob(f'{self.target_dir}/{src}')
        else:
            dst = os.path.abspath(dst)
            matches = glob.glob(src)

        for file in matches:
            file = os.path.abspath(file)

            if os.path.isfile(file):
                if os.path.exists(dst):
                    if os.path.isdir(dst):
                        # copy file to dir
                        target = os.path.join(dst, os.path.basename(file))
                    else:
                        # overwrite file
                        target = dst
                else:
                    # assume name if new filename
                    target = dst
            else:
                target = dst

            logging.info('Copying file %s to %s...', file, target)

            if file != target:
                if fix_ownership:
                    # Change owner to host user and group.
                    self.fake.run_sudo(
                        f'chown -R {os.getuid()}:{os.getgid()} {file}')

                # Create target directory if it does not exist.
                self._run_cmd(
                    f'mkdir -p {os.path.dirname(target)}',
                    environment, check=False)

                is_dir = os.path.isdir(file)
                if is_dir:
                    logging.debug('File %s is a dir...', file)
                else:
                    logging.debug('File %s is a file...', file)

                if delete_if_exists and not is_dir:
                    # Delete the target file or folder if it exists.
                    self._run_cmd(f'rm -rf {target}', environment)

                if move:
                    self._run_cmd(f'mv {file} {target}', environment)
                else:
                    if is_dir:
                        self._run_cmd(
                            f'rsync -a {file} {target}', environment)
                        target = os.path.join(target, os.path.basename(file))
                    else:
                        self._run_cmd(f'cp {file} {target}', environment)

                if uid:
                    self._run_cmd(f'chown {uid} {target}', environment)
                if gid:
                    self._run_cmd(f'chown :{gid} {target}', environment)

                if not mode and not move:
                    # Take over mode from source file.
                    mode = oct(os.stat(file).st_mode)
                    mode = mode[-4:]

                if mode:
                    self._run_cmd(f'chmod {mode} {target}', environment)

            else:
                logging.debug(
                    'Not copying %s, source and destination are identical.')

            files.append(target)

        return files

    def run_scripts(
        self,
        scripts: list[dict[str, str]],
        cwd: str,
    ):
        """ Run scripts. """
        # TODO: test
        logging.debug('Target dir: %s', self.target_dir)
        logging.debug('CWD: %s', cwd)

        for script in scripts:
            logging.info('Running script %s.', script)

            if 'name' not in script:
                logging.error(
                    'Invalid script entry %s, name is missing!', script)
                continue

            file = script['name']

            self.run_script(
                file=file,
                params=script.get('params', None),
                environment=EnvironmentType.from_str(script.get('env', None)),
                cwd=cwd
            )

    def run_script(
        self,
        file: str,
        params: Optional[str] = None,
        environment: Optional[EnvironmentType] = None,
        cwd: Optional[str] = None,
        check: bool = True,
        capture_output=True
    ) -> Optional[Tuple[Optional[str], Optional[str], int]]:
        """ Run scripts. """
        if not params:
            params = ''

        if not environment:
            environment = EnvironmentType.FAKEROOT
            logging.debug(
                'No environment provided. Using default %s.', environment)

        target_dir = self.target_dir
        if cwd:
            target_dir = cwd

        if not target_dir:
            logging.error('Target dir not set!')
            return None

        logging.info('Using %s as workdir for script %s.', target_dir, file)

        logging.debug('Copying scripts %s', file)
        script_files = self.copy_file(file, target_dir)

        logging.debug('Running scripts %s in environment %s',
                      script_files, environment)

        res = None

        for script_file in script_files:
            logging.info('Running script %s in environment %s',
                         script_file, environment)

            if not os.path.isfile(script_file):
                logging.error('Script %s not found!', script_file)
                return None

            if environment == EnvironmentType.CHROOT:
                script_file = f'./{os.path.basename(script_file)}'

            res = self._run_cmd(
                cmd=f'{script_file} {params}',
                env=environment,
                cwd=target_dir,
                check=check,
                capture_output=capture_output
            )

            if os.path.abspath(script_file) != os.path.abspath(file):
                # delete copied file
                self._run_cmd(
                    cmd=f'rm -f {script_file}',
                    env=environment,
                    cwd=target_dir,
                    check=False
                )

        return res

    def extract_tarball(self, archive: str, directory: Optional[str] = None,
                        use_sudo: bool = True) -> Optional[str]:
        """ Extract tar archive to directory. """
        target_dir = self.target_dir

        if directory:
            target_dir = directory

        if not target_dir:
            logging.error('No target dir found!')
            raise TargetDirNotInitialized('The target dir is not initialized!')

        tar_file = Path(archive)
        if not (tar_file.is_file() or tar_file.is_symlink()):
            logging.error('Archive is no file!')
            raise TarNotFound(f'The archive {archive} was not found!')

        temp_dir = tempfile.mkdtemp()

        if use_sudo:
            run_fn = self.fake.run_sudo
        else:
            run_fn = self.fake.run_fake

        # extract and rsync to avoid impact on ownership of base dir
        run_fn(f'tar xf {tar_file.absolute()} -C {temp_dir}')
        run_fn(f'rsync -a {temp_dir}/* {target_dir}')

        run_fn(f'rm -rf {temp_dir}', check=False)

        return target_dir

    def pack_root_as_tarball(
        self,
        output_dir: str,
        archive_name: str = 'root.tar',
        root_dir: Optional[str] = None,
        use_sudo: bool = True
    ) -> Optional[str]:
        """ Create tar archive of target_dir. """
        target_dir = self.target_dir

        if root_dir:
            target_dir = root_dir

        if not target_dir:
            raise TargetDirNotInitialized()

        tmp_archive = os.path.join(target_dir, archive_name)

        fn_run = self.fake.run_fake
        if use_sudo:
            fn_run = self.fake.run_sudo

        if os.path.isfile(tmp_archive):
            logging.info(
                'Archive %s exists. Deleting old archive.', tmp_archive)
            fn_run(f'rm -f {tmp_archive}', check=False)

        fn_run(
            'tar --exclude=\'./proc/*\' --exclude=\'./sys/*\' --exclude=\'./dev/*\' '
            f'--exclude=\'./{archive_name}\' -cf {archive_name} .',
            target_dir
        )

        if use_sudo:
            fn_run(
                f'chown {os.getuid()}:{os.getgid()} {tmp_archive}',
                check=False)

        archive = os.path.join(output_dir, archive_name)

        if os.path.isfile(archive):
            logging.info('Archive %s exists. Deleting old archive.', archive)
            fn_run(f'rm -f {archive}', check=False)

        # mv the file in two steps:
        # The first mv may move the file to another filesystem which is a copy followed by a remove
        # Due to The copy a half-copied file may be picked up by another process or even worse
        # two processes are writing to the file at the same time
        # Moving it to the same directory with the pid as filename extension ensures a unique name
        # The moving it to the correct name ensures that the move is atomic and so no half-copied file
        # can ever be seen by other processes
        pid_name = f"{archive}.{os.getpid()}"
        self.fake.run_cmd(f'mv -f {tmp_archive} {pid_name}')
        self.fake.run_cmd(f'mv -f {pid_name} {archive}')

        return archive


def parse_scripts(
    scripts: Optional[list[Any]],
    output_path: str,
    env: EnvironmentType = EnvironmentType.FAKEROOT,
    relative_base_dir: Optional[str] = None
) -> list[dict[str, Any]]:
    """ Parse scripts config entry. """
    if not scripts:
        return []

    result: list[dict[str, Any]] = []

    for script in scripts:
        if isinstance(script, dict):
            if 'name' not in script:
                logging.error('Script %s has no name!', script)
                continue

            script['name'] = resolve_file(
                file=script['name'],
                file_base_dir=script.get('base_dir', None),
                relative_base_dir=relative_base_dir
            )

            script['name'] = sub_output_path(script['name'], output_path)

            if 'env' in script:
                se = EnvironmentType.from_str(script['env'])
                logging.debug('Using env %s for script %s.', se, script)

                if not se:
                    logging.error('Unknown environment type %s! '
                                  'Falling back to %s.', script, env)
                    se = env

                script['env'] = se
            else:
                script['env'] = env

            result.append(script)

        elif isinstance(script, str):
            logging.debug('Using default env %s for script %s.', env, script)
            name = resolve_file(
                file=script,
                relative_base_dir=relative_base_dir
            )

            name = sub_output_path(name, output_path)

            result.append({
                'name': name,
                'env': env
            })
        else:
            logging.error('Unkown script entry type: %s', script)

    return result


def parse_files(
    files: Optional[list[dict[str, str]]],
    output_path: str,
    relative_base_dir: Optional[str] = None,
    resolve: bool = True
) -> list[dict[str, Any]]:
    """ Resolve file names to absolute paths. """
    if not files:
        return []

    processed: list[Any] = []

    for file in files:
        if isinstance(file, dict):
            if 'source' not in file:
                logging.error('File %s has no source!', file)
                continue

            if resolve:
                file['source'] = resolve_file(
                    file=file['source'],
                    file_base_dir=file.get('base_dir', None),
                    relative_base_dir=relative_base_dir
                )

            file['source'] = sub_output_path(file['source'], output_path)

            processed.append(file)

        elif isinstance(file, str):
            if resolve:
                file = resolve_file(
                    file=file,
                    relative_base_dir=relative_base_dir
                )

            file = sub_output_path(file, output_path)

            processed.append({
                'source': file
            })

        else:
            logging.error('Unknown file type %s! File is ignored.', file)

    return processed


def resolve_file(
    file: str,
    file_base_dir: Optional[str] = None,
    relative_base_dir: Optional[str] = None,
) -> str:
    """ Resolve path of file. """
    if file_base_dir:
        return os.path.abspath(os.path.join(file_base_dir, file))
    elif relative_base_dir:
        return os.path.abspath(os.path.join(relative_base_dir, file))
    return os.path.abspath(file)
