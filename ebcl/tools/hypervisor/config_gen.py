import argparse
import logging
import os

from pathlib import Path
from tempfile import TemporaryDirectory

import jinja2
import yaml

from ebcl.common import init_logging, log_exception
from ebcl.common.config import Config
from ebcl.common.files import resolve_file
from ebcl.common.version import VersionDepends
from ebcl.tools.hypervisor.model_gen import ConfigError
from ebcl.tools.hypervisor.vbus_gen import DTSConverter

from .schema_loader import BaseModel, FileReadProtocol, Schema, merge_dict


class BaseResolver:
    """
    Resolve bases defined in the yaml config.
    """

    def load(self, config_file: str, conf_dir: Path) -> dict:
        """
        Load config_file and all of its bases.
        """
        config = {
            "base": [config_file]
        }
        while config["base"]:
            base_name = config["base"].pop()
            base_path = resolve_file(file=base_name, relative_base_dir=str(conf_dir))
            old = config
            config = self._load_file(base_path)
            merge_dict(config, old)
        del config["base"]
        return config

    def _load_file(self, filename: str) -> dict:
        with open(filename, "r", encoding="utf-8") as f:
            data = yaml.load(f, yaml.Loader)
            if not data:
                data = {}
            return data


class HvFileGenerator:
    """
    Hypervisor configuration file generator
    """
    config: BaseModel
    schema: Schema
    output_path: Path

    def __init__(self, file: Path, output_path: Path, specialization: Path | None = None) -> None:
        """
        Parse the yaml config file.

        :param file: Path to the yaml config file
        :param output_path: Path where the output file are written to
        :param specilization: Path ot specialization directory
        """
        self.output_path = output_path

        config = BaseResolver().load(file.name, file.parent)

        self.schema = Schema(specialization)
        self.config = self.schema.parse_config(config)

    def _render_template(self, outpath: Path, template: FileReadProtocol) -> None:
        """Render a template to target"""
        template_obj = jinja2.Template(template.read_text("utf-8"), trim_blocks=True, keep_trailing_newline=True)

        with outpath.open("w", encoding="utf-8") as f:
            f.write(template_obj.render(config=self.config))

    def create_files(self) -> None:
        """
        Create three Files of HV
        init.ned, io.cfg and modules.list
        """
        self.output_path.mkdir(exist_ok=True)

        for template in self.schema.templates:
            base, ext = os.path.splitext(template.name)
            if ext == ".j2":
                logging.info("Rendering %s", base)
                outpath = self.output_path / base
                self._render_template(outpath, template)
            else:
                logging.info("Creating %s", template)
                outpath = self.output_path / template.name
                outpath.write_text(template.read_text("utf-8"))


class SpecializationUnpacker:
    """
    Unpacks a debian package with hypervisor specialization

    The property directory returns the path to the files on the local filesystem.
    They are removed when this object is deleted.

    The path is looked up automatically searching for schema.yaml. It can also be
    specified in the constructor (path).
    """
    _tmp_dir: TemporaryDirectory
    _config_dir: Path

    def __init__(self, package_name: str, config_file: Path, path: str | None = None) -> None:
        self._tmp_dir = TemporaryDirectory()
        self._config_dir = Path(self._tmp_dir.name)

        config = Config(str(config_file), self._tmp_dir.name)

        package = config.proxy.find_package(
            VersionDepends(package_name, None, None, None, config.arch)
        )
        if not package:
            raise ConfigError(f"Cannot find package {package_name}")
        package = config.proxy.download_package(config.arch, package)
        if not package:  # pragma: no cover (should never happen)
            raise ConfigError(f"Cannot download package {package_name}")

        print(package.local_file)
        print(package.extract(self._tmp_dir.name, None, use_sudo=False))

        os.system(f"find {self._tmp_dir.name}")

        if path:
            self._config_dir = self._config_dir / path
        else:
            self._config_dir = self.find_schema()

    def find_schema(self) -> Path:
        """Find a single instance of schema.yaml in the archive"""
        directories: list[Path] = []
        for root, _, files in os.walk(self._tmp_dir.name):
            if "schema.yaml" in files:
                directories.append(Path(root))

        if len(directories) != 1:
            raise ConfigError(f"Expected exactly one schema.yaml in specialization package, found {len(directories)}.")
        return directories[0]

    def __del__(self) -> None:
        self._tmp_dir.cleanup()

    @property
    def directory(self) -> Path:
        """Path to the extension directory on the local filesystem"""
        return self._config_dir


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL hypervisor generator. """
    init_logging()

    logging.info('\n===================\n'
                 'EBcL Hypervisor Config File Generator\n'
                 '===================\n')

    parser = argparse.ArgumentParser(
        description='Create the config files for the hypervisor')
    parser.add_argument('--dts', type=Path,
                        help=(
                            "Path to the SoC Device Tree to be converted to YAML format. "
                            "If provided, all other parameters will be ignored.")
                        )
    parser.add_argument('-s', '--specialization', type=Path,
                        help='Path to hypervisor specialization directory')
    parser.add_argument('-p', '--specialization-package', type=str,
                        help='Name of a debian package that contains the hypervisor specialization')
    parser.add_argument('--specialization-path', type=str,
                        help='Path to specialization in package')
    parser.add_argument('-r', '--repo-config', type=Path,
                        help='Path to a config file with a repository containing the hypervisor specialization')
    parser.add_argument('--config_file', type=Path,
                        help='Path to the YAML configuration file')
    parser.add_argument('--output', type=Path,
                        help='Path to the output directory')
    args = parser.parse_args()

    if args.dts:
        dtsconverter = DTSConverter(args.dts)
        dtsconverter.dump()

    if args.specialization_package and not args.dts:
        if not args.repo_config or not args.repo_config.exists():
            parser.error("If a SPECIALIZATION_PACKAGE is specified a REPO_CONFIG must be specified as well")
        unpacker = SpecializationUnpacker(args.specialization_package, args.repo_config, args.specialization_path)
        args.specialization = unpacker.directory

    if not args.dts:
        generator = HvFileGenerator(args.config_file, args.output, args.specialization)
        generator.create_files()


if __name__ == "__main__":  # pragma: nocover
    main()
