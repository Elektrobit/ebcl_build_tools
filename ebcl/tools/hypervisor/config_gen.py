import argparse
import logging
import os
from pathlib import Path

import jinja2
import yaml

from ebcl.common import init_logging, log_exception
from ebcl.common.files import resolve_file

from .schema_loader import BaseModel, FileReadProtocol, Schema, merge_dict


class BaseResolver:
    """
    Resolve bases defined in the yaml config.
    """

    def load(self, config_file: str, conf_dir: str) -> dict:
        """
        Load config_file and all of its bases.
        """
        config = {
            "base": [config_file]
        }
        while config["base"]:
            base_name = config["base"].pop(0)
            base_path = resolve_file(
                file=base_name, relative_base_dir=conf_dir)
            old = config
            config = self._load_file(base_path)
            merge_dict(config, old)
        return config

    def _load_file(self, filename: str) -> dict:
        with open(filename, "r", encoding="utf-8") as f:
            return yaml.load(f, yaml.Loader)


class HvFileGenerator:
    """
    Hypervisor configuration file generator
    """
    config: BaseModel
    schema: Schema
    output_path: Path

    def __init__(self, file: str, output_path: str, specialization: str | None = None) -> None:
        """ Parse the yaml config file.
        Args:
            config_file (Path): Path to the yaml config file.
        """
        self.output_path = Path(output_path)

        """ Load yaml configuration. """
        config_file = Path(file)

        config = BaseResolver().load(config_file.name, str(config_file.parent))
        del config["base"]

        self.schema = Schema(specialization and Path(specialization) or None)
        self.config = self.schema.parse_config(config)

    def _render_template(self, outpath: Path, template: FileReadProtocol) -> None:
        """Render a template to target"""
        template_obj = jinja2.Template(template.read_text("utf-8"), trim_blocks=True)

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


@log_exception(call_exit=True)
def main() -> None:
    """ Main entrypoint of EBcL hypervisor generator. """
    init_logging()

    logging.info('\n===================\n'
                 'EBcL Hypervisor Config File Generator\n'
                 '===================\n')

    parser = argparse.ArgumentParser(
        description='Create the config files for the hypervisor')
    parser.add_argument('-s', '--specialization', type=str,
                        help='Path to hypervisor specialization directory')
    parser.add_argument('config_file', type=str,
                        help='Path to the YAML configuration file')
    parser.add_argument('output', type=str,
                        help='Path to the output directory')
    args = parser.parse_args()

    generator = HvFileGenerator(args.config_file, args.output, args.specialization)
    generator.create_files()


if __name__ == "__main__":
    main()
