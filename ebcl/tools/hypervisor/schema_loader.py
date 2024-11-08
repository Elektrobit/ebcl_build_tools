from __future__ import annotations

import importlib.util
import importlib.resources
import logging
from pathlib import Path
import sys
import types
from typing import IO, Literal, Protocol
import yaml

from .model_gen import BaseModel, ConfigError, PropertyInfo
from . import model
from . import data


def merge_dict(old: dict, new: dict) -> None:
    """
    Recursively merge one dictionary into another.
    For existing values the behavior depends on the datatype:
        * strings, numbers and booleans are overwritten
        * lists are appended
        * dicts are updated by recursively executing this function
    """
    def _merge_list(old: list, new: list) -> None:
        old += new

    for key, value in new.items():
        if key not in old:
            old[key] = value
        else:
            if type(old[key]) is not type(value):
                raise ConfigError(f"Type for {key} do not match ({type(old[key])} != {type(value)})")

            if isinstance(value, list):
                _merge_list(old[key], value)
            elif isinstance(value, dict):
                merge_dict(old[key], value)
            elif isinstance(value, (str, int, bool)):
                old[key] = value
            else:
                raise ConfigError(f"Unknown type for {key} ({type(value)})")


class DisablePycache:
    """
    Temporarily disables creation of the byte cache.
    Use this as a context manager, e.g.::

        with DisablePycache():
            ...
    """
    _old_state: bool = False

    def __enter__(self):
        self._old_state = sys.dont_write_bytecode
        sys.dont_write_bytecode = True

    def __exit__(self, type, value, traceback):
        sys.dont_write_bytecode = self._old_state


class FileReadProtocol(Protocol):
    """
    Protocol for read-only text file interfaces (Path and importlib.Traversable)
    """
    def open(self, mode: Literal["r"] = "r", *, encoding: str | None = None, errors: str | None = None) -> IO[str]:
        ...

    @property
    def name(self) -> str:
        ...

    def read_text(self, encoding: str | None = None) -> str:
        ...


class Schema:
    """
    Load base and extension schema

    The class loads schema.yaml from this module and from the extension path.
    It then unifies the configuration and creates/updates all model classes
    with the properties defined in the schema.
    The model is loaded from model.py of this module and also model.py from
    the extension path.
    This allows fully extending the configuration system with hypervisor
    extensions required for specific hypervisor versions.
    """
    _root: type[BaseModel]
    _templates: list[FileReadProtocol]
    _schema_version: int

    def __init__(self, extension: Path | None) -> None:
        schema = self._load_base_schema()
        ext_model = None
        if extension:
            ext_schema = self._load_ext_schema(extension)
            if ext_schema:
                merge_dict(schema, ext_schema)
                logging.info("Extension schema loaded")
            ext_model = self._load_ext_model(extension)
            if ext_model:
                logging.info("Extension model loaded")

        for key, value in schema.get("classes", {}).items():
            cls: type[BaseModel] | None = None
            if ext_model:
                cls = getattr(ext_model, key, None)
            if not cls:
                cls = getattr(model, key, None)

            if cls and not issubclass(cls, BaseModel):
                raise ConfigError(f"Class {cls.__name__} is not derived from BaseModel")

            if not cls:
                cls = type(key, (BaseModel,), {})
            cls.PROPERTIES = [PropertyInfo(key, info) for key, info in value.items()]
            BaseModel.class_registry[key] = cls

        root = schema.get("root")
        if not root or not isinstance(root, str) or root not in BaseModel.class_registry:
            raise ConfigError("Missing or invalid root property in schema")
        self._root = BaseModel.class_registry[root]
        self._templates = self._load_templates(schema.get("templates", []), extension)

    def _load_base_schema(self) -> dict:
        """Load the schema.yaml from this module"""
        schema_file = importlib.resources.files(data) / "schema.yaml"
        with schema_file.open(encoding="utf8") as f:
            schema = yaml.load(f, yaml.Loader)
        schema_version = schema.get("version", None)

        if not schema_version or not isinstance(schema_version, int):
            raise ConfigError("Version missing in base schema")
        self._schema_version = schema_version
        return schema

    def _load_ext_schema(self, extension: Path) -> dict | None:
        """Load the schema.yaml from the extension path"""
        schema_file = extension / "schema.yaml"
        if not schema_file.is_file():
            return None

        with schema_file.open(encoding="utf-8") as f:
            schema = yaml.load(f, yaml.Loader)
        schema_ext_version = schema.get("version", None)
        if not schema_ext_version or not isinstance(schema_ext_version, int):
            raise ConfigError("Version missing in extension schema")
        if self._schema_version != schema_ext_version:
            raise ConfigError(
                f"Version of extension schema ({schema_ext_version}) "
                f"does not match base schema version ({self._schema_version})"
            )
        return schema

    def _load_ext_model(self, extension: Path) -> None | types.ModuleType:
        """Load the model.py from the extension path"""
        ext_model_file = extension / "model.py"
        if not ext_model_file.exists():
            return None

        spec = importlib.util.spec_from_file_location("ext_model", ext_model_file)
        if not spec or not spec.loader:
            raise ConfigError(f"Unable to load extension model {ext_model_file}")
        ext_model = importlib.util.module_from_spec(spec)
        with DisablePycache():  # Disable creation of __pycache__ in extension dir
            spec.loader.exec_module(ext_model)
        return ext_model

    def _load_templates(self, templates: list[str], extension: Path | None) -> list[FileReadProtocol]:
        """Find paths to all templates defined in the schema"""
        res: list[FileReadProtocol] = []
        for template in templates:
            if extension:
                ext_template = extension / template
            else:
                ext_template = None
            if ext_template and ext_template.is_file():
                res.append(ext_template)
            else:
                path = importlib.resources.files(data) / template
                if not path.is_file():
                    raise ConfigError(f"Unable to find template {template}")
                res.append(path)

        return res

    def parse_config(self, config: dict) -> BaseModel:
        """Parse a hypervisor config with the current schema"""
        return self._root(config)

    @property
    def templates(self) -> list[FileReadProtocol]:
        """The templates defined in the schema"""
        return self._templates
