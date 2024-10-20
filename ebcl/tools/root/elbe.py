""" Implemenation for using elbe as root filesystem generator. """
import logging
import os

from pathlib import Path
from typing import Optional, Any
from urllib.parse import urlparse

from ebcl.common import ImplementationError
from ebcl.common.apt import Apt
from ebcl.common.config import Config, InvalidConfiguration
from ebcl.common.templates import render_template


def _generate_elbe_image(
    config: Config,
    primary_repo: Apt,
    name: str,
    result_dir: str
) -> Optional[str]:
    """ Generate an elbe image description. """

    logging.info('Generating elbe image from template...')

    if not config.primary_repo:
        logging.critical('No primary repo!')
        return None

    if not config.packages:
        logging.critical('Packages defined!')
        return None

    params: dict[str, Any] = {}

    params['name'] = config.name
    params['arch'] = config.arch.get_elbe_arch()

    if not primary_repo:
        raise InvalidConfiguration('Primary apt repository is missing!')

    try:
        url = urlparse(primary_repo.url)
    except Exception as e:
        logging.critical(
            'Invalid primary repo url %s! %s', primary_repo.url, e)
        return None

    params['primary_repo_url'] = url.netloc
    params['primary_repo_path'] = url.path
    params['primary_repo_proto'] = url.scheme
    params['distro'] = primary_repo.distro

    params['hostname'] = config.hostname
    params['domain'] = config.domain
    params['console'] = config.console

    if config.root_password:
        params['root_password'] = config.root_password
    else:
        params['root_password'] = ''

    if config.packages:
        package_names = []
        for vd in config.packages:
            package_names.append(vd.name)
        params['packages'] = package_names

    params['packer'] = config.packer
    params['output_archive'] = 'root.tar'

    if config.apt_repos:
        params['apt_repos'] = []
        for repo in config.apt_repos:
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

    if config.template is None:
        template = os.path.join(os.path.dirname(__file__), 'root.xml')
    else:
        template = config.template

    (image_file, _content) = render_template(
        template_file=template,
        params=params,
        generated_file_name=f'{name}.image.xml',
        results_folder=result_dir,
        template_copy_folder=result_dir
    )

    if not image_file:
        logging.critical('Rendering image description failed!')
        return None

    logging.debug('Generated image stored as %s', image_file)

    return image_file


def build_elbe_image(
    config: Config,
    primary_repo: Apt,
    name: str,
    result_dir: str
) -> Optional[str]:
    """ Run elbe image build. """

    if config.image:
        image: Optional[str] = config.image
    else:
        image = _generate_elbe_image(config, primary_repo, name, result_dir)

    if not image:
        logging.critical('No elbe image description found!')
        return None

    if not os.path.isfile(image):
        logging.critical('Image %s not found!', image)
        return None

    (out, err, _returncode) = config.fake.run_cmd(
        'elbe control create_project')
    if err.strip() or not out:
        raise ImplementationError(
            f'Elbe project creation failed! err: {err.strip()}')
    prj = out.strip()

    pre_xml = os.path.join(result_dir, os.path.basename(image)) + '.gz'

    config.fake.run_cmd(
        f'elbe preprocess --output={pre_xml} {image}')
    config.fake.run_cmd(
        f'elbe control set_xml {prj} {pre_xml}')
    config.fake.run_cmd(f'elbe control build {prj}')
    config.fake.run_fake(f'elbe control wait_busy {prj}')
    config.fake.run_fake(
        f'elbe control get_files --output {result_dir} {prj}')
    config.fake.run_fake(f'elbe control del_project {prj}')

    tar = os.path.join(result_dir, 'root.tar')

    if os.path.isfile(tar):
        return tar

    results = Path(result_dir)

    # search for tar
    pattern = '*.tar'
    if config.result_pattern:
        pattern = config.result_pattern

    images = list(results.glob(pattern))
    if images:
        return os.path.join(result_dir, images[0])

    return ''
