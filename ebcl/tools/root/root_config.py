#!/usr/bin/env python
""" EBcL root filesystem config helper. """
import argparse
import logging
import os
import tempfile

from pathlib import Path
from typing import Optional, Any

from ebcl.common import init_logging, promo, log_exception
from ebcl.common.config import load_yaml
from ebcl.common.fake import Fake
from ebcl.common.files import Files, EnvironmentType, parse_scripts, parse_files
from ebcl.tools.root.root import FileNotFound


class RootConfig:
    """ EBcL root filesystem config helper. """

    # TODO: test

    # config file
    config: str
    # config values
    scripts: list[dict[str, Any]]
    host_files: list[dict[str, str]]
    # Tar the root tarball in the chroot env
    pack_in_chroot: bool
    # fakeroot helper
    fake: Fake
    # files helper
    fh: Files

    @log_exception(call_exit=True)
    def __init__(self, config_file: str):
        """ Parse the yaml config file.

        Args:
            config_file (Path): Path to the yaml config file.
        """
        config = load_yaml(config_file)

        self.config = config_file

        config_dir = os.path.dirname(config_file)

        self.scripts = parse_scripts(
            config.get('scripts', None),
            relative_base_dir=config_dir)

        self.host_files = parse_files(
            config.get('host_files', None),
            relative_base_dir=config_dir)

        self.pack_in_chroot = config.get('pack_in_chroot', True)

        self.fake = Fake()
        self.fh = Files(self.fake)

    def _run_scripts(self, output_path: str):
        """ Run scripts. """
        for script in self.scripts:
            logging.info('Running script: %s', script)

            if 'name' not in script:
                logging.error(
                    'Invalid script entry %s, name is missing!', script)

            if '$$RESULTS$$' in script['name']:
                logging.debug(
                    'Replacing $$RESULTS$$ with %s for script %s.', output_path, script)
                parts = script['name'].split('$$RESULTS$$/')
                script['name'] = os.path.abspath(
                    os.path.join(output_path, parts[-1]))

            file = os.path.join(os.path.dirname(
                self.config), script['name'])

            env: Optional[EnvironmentType] = None
            if 'env' in script:
                env = script['env']

            self.fh.run_script(
                file=file,
                params=script.get('params', None),
                environment=env,
                check=True
            )

    def _copy_files(self,
                    relative_base_dir: str,
                    files: list[dict[str, str]],
                    target_dir: str,
                    output_path: str):
        """ Copy files to target_dir. """
        logging.debug('Files: %s', files)

        for entry in files:
            logging.info('Processing entry: %s', entry)

            src = entry.get('source', None)
            if not src:
                logging.error(
                    'Invalid file entry %s, source is missing!', entry)

            if '$$RESULTS$$' in src:
                logging.debug(
                    'Replacing $$RESULTS$$ with %s for file %s.', output_path, entry)
                parts = src.split('$$RESULTS$$/')
                src = os.path.abspath(os.path.join(output_path, parts[-1]))

            src = Path(relative_base_dir) / src

            dst = Path(target_dir)
            file_dest = entry.get('destination', None)
            if file_dest:
                dst = dst / file_dest

            mode: str = entry.get('mode', '600')
            uid: int = int(entry.get('uid', '0'))
            gid: int = int(entry.get('gid', '0'))

            logging.debug('Copying files %s', src)

            copied_files = self.fh.copy_file(
                src=str(src),
                dst=str(dst),
                uid=uid,
                gid=gid,
                mode=mode,
                delete_if_exists=True
            )

            if not copied_files:
                raise FileNotFound(f'File {src} not found!')

    @log_exception()
    def config_root(self, archive_in: str, archive_out: str) -> Optional[str]:
        """ Config the tarball.  """
        if not os.path.exists(archive_in):
            logging.critical('Archive %s does not exist!', archive_in)
            return None

        output_path = os.path.dirname(archive_out)

        tmp_root_dir = tempfile.mkdtemp()

        ao = None

        self.fh.target_dir = tmp_root_dir
        self.fh.extract_tarball(archive_in, tmp_root_dir)

        if self.host_files:
            # Copy host files to target_dir folder
            logging.info('Copy host files to target dir...')
            self._copy_files(os.path.dirname(self.config), self.host_files,
                             tmp_root_dir, output_path=output_path)

        self._run_scripts(output_path=output_path)

        ao = self.fh.pack_root_as_tarball(
            output_dir=os.path.dirname(archive_out),
            archive_name=os.path.basename(archive_out),
            root_dir=tmp_root_dir,
            use_fake_chroot=self.pack_in_chroot
        )

        if logging.root.level == logging.DEBUG:
            logging.info('Skipping cleanup of tmpdir.')
        else:
            logging.info('Cleaning up the tmpdir...')
            self.fake.run(f'rm -rf {tmp_root_dir}', check=False)

        if not ao:
            logging.critical('Repacking root failed!')
            return None

        return ao


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL root filesystem config helper. """
    init_logging()

    logging.info('\n=====================\n'
                 'EBcL Root Configurator\n'
                 '======================\n')

    parser = argparse.ArgumentParser(
        description='Configure the given root tarball.')
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('archive_in', type=str, help='Root tarball.')
    parser.add_argument('archive_out', type=str, help='New tarball.')

    args = parser.parse_args()

    logging.debug('Running root_configurator with args %s', args)

    # Read configuration
    generator = RootConfig(args.config_file)

    archive = generator.config_root(args.archive_in, args.archive_out)

    if archive:
        print(f'Archive was written to {archive}.')
        promo()
    else:
        exit(1)


if __name__ == '__main__':
    main()
