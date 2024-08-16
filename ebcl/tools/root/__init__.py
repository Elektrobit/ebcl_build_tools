""" Root generator and configurator. """
import logging
import os

from typing import Optional

from ebcl.common.config import Config


def config_root(config: Config, archive_in: str, archive_out: str):
    """ Configure the given root tarball. """
    if not os.path.exists(archive_in):
        logging.critical('Archive %s does not exist!', archive_in)
        return None

    config.fh.extract_tarball(archive_in, config.target_dir)

    if logging.root.level == logging.DEBUG:
        config.fake.run_fake(f'ls -lah {config.target_dir}')

    if config.host_files:
        # Copy host files to target_dir folder
        logging.info('Copy host files to target dir...')
        config.fh.copy_files(
            config.host_files, config.target_dir)

    config.fh.run_scripts(config.scripts, config.target_dir)

    ao: Optional[str] = config.fh.pack_root_as_tarball(
        output_dir=os.path.dirname(archive_out),
        archive_name=os.path.basename(archive_out),
        root_dir=config.target_dir,
        use_sudo=not config.use_fakeroot
    )

    if not ao:
        logging.critical('Repacking root failed!')
        return None

    return ao
