import sys
import pytest

from pathlib import Path

from ebcl.tools.hypervisor.config_gen import BaseResolver, main as hv_main

test_data = Path(__file__).parent / "data"


class TestBaseResolver:
    def test_no_includes(self) -> None:
        assert BaseResolver().load("empty.yaml", test_data) == {}

    def test_recursive_include(self) -> None:
        data = BaseResolver().load("include_test.yaml", test_data)
        assert data['includes'] == [
            'include_a_a',
            'include_a_b',
            'include_b_a',
            'include_a',
            'include_b',
            'include_test'
        ], "Verify include order is depth-first in order of defined bases"
        assert data['foo']['bar'] == 4

    def test_missing_include(self) -> None:
        with pytest.raises(FileNotFoundError):
            BaseResolver().load("missing_include.yaml", test_data)


real_examples = list((test_data / "examples").iterdir())


@pytest.mark.parametrize(
    'path',
    [n for n in real_examples],
    ids=[n.name for n in real_examples]
)
def test_examples(path: Path, tmp_path: Path) -> None:
    """Full integration tests, that are automatically discovered from data/examples"""
    expected_dir = path / "expected"
    extension_dir = path / "extension"

    # call the generator through main
    sys.argv = [
        "hypervisor_config",
        str(path / "config.yaml"),
        str(tmp_path)
    ]
    if extension_dir.is_dir():
        sys.argv += ["-s", str(extension_dir)]
    hv_main()

    created_files = sorted(tmp_path.iterdir())
    expected_files = sorted(expected_dir.iterdir())
    assert list(map(lambda x: x.name, created_files)) == list(map(lambda x: x.name, expected_files))
    for act, exp in zip(created_files, expected_files):
        assert act.read_text() == exp.read_text(), f"{act.name} differs"
