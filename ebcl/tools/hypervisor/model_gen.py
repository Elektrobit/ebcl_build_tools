from __future__ import annotations

import builtins
import logging
from typing import Any, Type


class ConfigError(Exception):
    """Configuration error"""


class PropertyInfo:
    """Information about a property of the configuration"""

    name: str
    type: str
    aggregate: str
    default: Any
    optional: bool
    enum_values: list[str] | None

    def __init__(self, name: str, info: dict) -> None:
        self.name = name
        self.type = info["type"]
        self.aggregate = info.get("aggregate", "None")
        self.optional = info.get("optional", False)
        self.default = info.get("default", None)
        self.enum_values = info.get("enum_values", None)

    def validate_enum(self, value: Any) -> bool:
        """
        Validate value of enum.
        Note: This is always true, it the type is not an enum
        """
        if self.type != "enum":
            return True
        if not isinstance(value, str) or not self.enum_values:
            return False
        return value in self.enum_values

    def get_type(self, registry: dict[str, builtins.type[BaseModel]]) -> Type | None:
        """Returns the expected class type of a value"""
        if self.type == "string" or self.type == "enum":
            return str
        elif self.type == "integer":
            return int
        elif self.type == "boolean":
            return bool
        return registry.get(self.type, None)


class BaseModel:
    """
    Base class for all model classes
    """
    class_registry: dict[str, type[BaseModel]] = {}
    PROPERTIES: list[PropertyInfo]

    def __init__(self, config: dict) -> None:
        self.__load(config)

    def __parse_type(self, info: PropertyInfo, value: Any) -> Any:
        """Verify that value matches the PropertyInfo"""
        expected = info.get_type(self.class_registry)

        if not expected:
            raise ConfigError(f"Unexpected type for {type(self).__name__}.{info.name}: {info.type}")

        if not info.validate_enum(value):
            raise ConfigError(
                f"Invalid value for enum type {type(self).__name__}.{info.name}, "
                f"expected one of {', '.join(info.enum_values or [])} but is '{value}"
            )

        if issubclass(expected, BaseModel):
            value = expected(value)

        if not isinstance(value, expected):
            raise ConfigError(
                f"Wrong type for {type(self).__name__}.{info.name}, expected {info.type} but is {type(value)}"
            )
        return value

    def __load_list(self, info: PropertyInfo, value: Any) -> None:
        """Load a list of values"""
        if not isinstance(value, list):
            logging.warning(
                "Value for %s.%s is expected to be a list. It will be converted to a single item list",
                type(self).__name__,
                info.name
            )
            value = [value]
        setattr(self, info.name, list(map(lambda x: self.__parse_type(info, x), value)))

    def __load(self, config: dict) -> None:
        """Load this instance from the config"""
        used_keys = []
        for info in self.PROPERTIES:
            value = config.get(info.name, info.default)
            if value is None:
                if not info.optional:
                    raise ConfigError(f"Property {info.name} for {type(self).__name__} is not optional")
                setattr(self, info.name, None)
                continue
            used_keys.append(info.name)

            if info.aggregate == "list":
                self.__load_list(info, value)
            else:
                setattr(self, info.name, self.__parse_type(info, value))

        unused_keys = set(config.keys()) - set(used_keys)
        if unused_keys:
            logging.warning("Some properties for %s are unused: %s", type(self).__name__, ", ".join(unused_keys))
