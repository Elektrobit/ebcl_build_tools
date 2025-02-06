import logging
import pytest

from typing import Any, Protocol

from ebcl.tools.hypervisor.model_gen import BaseModel, ConfigError, PropertyInfo


class TestPropertyInfo:
    def test_init(self) -> None:
        prop = PropertyInfo('a_name', {
            'type': 'string'
        })
        assert prop.name == 'a_name'
        assert prop.type == 'string'
        assert prop.aggregate == 'None'
        assert prop.optional is False
        assert prop.default is None
        assert prop.enum_values is None

        prop = PropertyInfo('a_name', {
            'type': 'string',
            'aggregate': 'list',
            'optional': True,
            'default': 'default',
            'enum_values': ['a', 'b']
        })
        assert prop.aggregate == 'list'
        assert prop.optional is True
        assert prop.default == 'default'
        assert prop.enum_values == ['a', 'b']

    def test_validate_enum(self) -> None:
        prop = PropertyInfo('a_name', {
            'type': 'string'
        })
        assert prop.validate_enum(1) is True, 'If type is not an enum this is always true'

        prop = PropertyInfo('a_name', {
            'type': 'enum',
            'enum_values': ['a', 'b']
        })
        assert prop.validate_enum('a') is True
        assert prop.validate_enum('b') is True
        assert prop.validate_enum('c') is False
        assert prop.validate_enum(1) is False

        prop = PropertyInfo('a_name', {
            'type': 'enum'
        })
        assert prop.validate_enum('a') is False

    def test_get_type(self) -> None:
        assert PropertyInfo('a_name', {'type': 'string'}).get_type({}) is str
        assert PropertyInfo('a_name', {'type': 'enum'}).get_type({}) is str
        assert PropertyInfo('a_name', {'type': 'integer'}).get_type({}) is int
        assert PropertyInfo('a_name', {'type': 'boolean'}).get_type({}) is bool
        assert PropertyInfo('a_name', {'type': 'something'}).get_type({}) is None
        assert PropertyInfo('a_name', {'type': 'test'}).get_type({'test': BaseModel}) is BaseModel


class SupportsGetAttr(Protocol):
    """A protocol, that supports generic attribute access"""
    def __getattr__(self, name: str) -> Any:
        ...


class BaseModelWithGetAttr(BaseModel, SupportsGetAttr):
    """Create a type, that makes static typing happy"""


def create_model_class(properties: dict[str, dict], name="ModelClass") -> type[BaseModelWithGetAttr]:
    return type(name, (BaseModel, ), {
        'PROPERTIES': [PropertyInfo(k, v) for k, v in properties.items()]
    })


class TestBaseModel:
    def teardown_method(self) -> None:
        # Clear the class_registry after every test
        BaseModel.class_registry = {}

    def test_init(self) -> None:
        assert create_model_class({})({}) is not None, "A very simple class can be created"

        obj = create_model_class({
            'str': {'type': 'string'},
            'int': {'type': 'integer'},
            'enum': {'type': 'enum', 'enum_values': ['foo', 'bar', 'foobar']},
            'bool': {'type': 'boolean'}
        })({
            'str': 'test',
            'int': 42,
            'enum': 'bar',
            'bool': True
        })
        assert obj.str == 'test'
        assert obj.int == 42
        assert obj.enum == 'bar'
        assert obj.bool is True

    @pytest.mark.parametrize('expected_type, value', [
        ('string', 42),
        ('string', True),
        ('integer', 'string'),
        ('integer', True),
        ('boolean', 0),
        ('boolean', 'string'),
        ('boolean', 'True'),
    ])
    def test_invalid(self, expected_type: str, value: Any) -> None:
        with pytest.raises(
            ConfigError,
            match=f"^Wrong type for ModelClass.value, expected {expected_type} but is {type(value)}$"
        ):
            create_model_class({
                'value': {'type': expected_type}
            })({'value': value})

    def test_invalid_enum(self) -> None:
        with pytest.raises(
            ConfigError,
            match="^Invalid value for enum type ModelClass.value, expected one of a, b but is c$"
        ):
            create_model_class({
                'value': {'type': 'enum', 'enum_values': ['a', 'b']}
            })({'value': 'c'})

    def test_invalid_type(self):
        with pytest.raises(
            ConfigError,
            match="^Invalid type for ModelClass.value: blub$"
        ):
            create_model_class({
                'value': {'type': 'blub'}
            })({'value': 'c'})

    def test_superfluous_parameter(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            create_model_class({
                'str': {'type': 'string'},
                'int': {'type': 'integer'}
            })({
                'str': 'string',
                'int': 42,
                'str2': 'str',
                'int2': 43
            })
        assert caplog.messages[0] == "Some properties for ModelClass are unused: int2, str2"

    def test_missing_parameters(self) -> None:
        with pytest.raises(
            ConfigError,
            match="^Properties are missing for ModelClass: int, str$"
        ):
            create_model_class({
                'str': {'type': 'string'},
                'int': {'type': 'integer'},
                'int2': {'type': 'integer', 'optional': True}
            })({})

    def test_model_class(self) -> None:
        AModel = create_model_class({'value': {'type': 'string'}}, name="AModel")
        BModel = create_model_class({'a': {'type': 'AModel'}}, name="BModel")
        BModel.class_registry['AModel'] = AModel

        obj = BModel({
            'a': {
                'value': 'foobar'
            }
        })
        assert isinstance(obj.a, AModel)
        assert obj.a.value == "foobar"

    def test_list(self) -> None:
        AModel = create_model_class({'value': {'type': 'string'}}, name="AModel")
        BaseModel.class_registry['AModel'] = AModel
        obj = create_model_class({
            'str': {'type': 'string', 'aggregate': 'list'},
            'int': {'type': 'integer', 'aggregate': 'list'},
            'bool': {'type': 'boolean', 'aggregate': 'list'},
            'obj': {'type': 'AModel', 'aggregate': 'list'}
        })({
            'str': ['foo', 'bar'],
            'int': [123],
            'bool': [True, True, False],
            'obj': [{'value': 'foo'}, {'value': 'bar'}]
        })
        assert obj.str == ['foo', 'bar']
        assert obj.int == [123]
        assert obj.bool == [True, True, False]
        assert len(obj.obj) == 2
        assert obj.obj[0].value == 'foo'
        assert obj.obj[1].value == 'bar'

    def test_list_convert_from_value(self, caplog: pytest.LogCaptureFixture) -> None:
        cls = create_model_class({'value': {'type': 'string', 'aggregate': 'list'}})
        with caplog.at_level(logging.WARNING):
            obj = cls({
                'value': 'str'
            })
        assert caplog.messages[0] == "Value for ModelClass.value is expected to be a list. It will be converted to a single item list"  # noqa: E501
        assert obj.value == ['str']

    def test_optional(self) -> None:
        AModel = create_model_class({'value': {'type': 'string'}}, name="AModel")
        BaseModel.class_registry['AModel'] = AModel
        cls = create_model_class({
            'str': {'type': 'string', 'optional': True},
            'int': {'type': 'integer', 'optional': True},
            'bool': {'type': 'boolean', 'optional': True},
            'obj': {'type': 'AModel', 'optional': True}
        })
        obj = cls({})
        assert obj.str is None
        assert obj.int is None
        assert obj.bool is None
        assert obj.obj is None

        obj = cls({
            'str': 'foo',
            'int': 123,
            'bool': True,
            'obj': {'value': 'foo'}
        })
        assert obj.str == 'foo'
        assert obj.int == 123
        assert obj.bool is True
        assert obj.obj.value == 'foo'

        cls = create_model_class({
            'str': {'type': 'string', 'optional': True, 'default': 'foobar'},
            'int': {'type': 'integer', 'optional': True, 'default': 42},
            'bool': {'type': 'boolean', 'optional': True, 'default': True},
            'obj': {'type': 'AModel', 'optional': True, 'default': {'value': 'fooo'}}
        })
        obj = cls({})
        assert obj.str == 'foobar'
        assert obj.int == 42
        assert obj.bool is True
        assert obj.obj.value == 'fooo'
