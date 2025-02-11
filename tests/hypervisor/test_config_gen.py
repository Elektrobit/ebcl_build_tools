import sys
import pytest

from pathlib import Path

import yaml

from ebcl.common.types.cpu_arch import CpuArch
from ebcl.tools.hypervisor.config_gen import BaseResolver, SpecializationUnpacker, main as hv_main
from ebcl.tools.hypervisor.model_gen import ConfigError

test_data = Path(__file__).parent / "data"


def compare_directories(actual: Path, expected: Path) -> None:
    created_files = sorted(actual.iterdir())
    expected_files = sorted(expected.iterdir())
    assert list(map(lambda x: x.name, created_files)) == list(map(lambda x: x.name, expected_files))
    for act, exp in zip(created_files, expected_files):
        assert act.read_text() == exp.read_text(), f"{act.name} differs"


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


class TestSpecializationUnpacker:
    config: Path

    @pytest.fixture(scope="function", autouse=True)
    def setup(self, tmp_path: Path) -> None:
        self.config = tmp_path / "config.yaml"
        with self.config.open("w") as f:
            yaml.dump(
                {
                    'arch': str(CpuArch.ARM64),
                    'apt_repos': [
                        {
                            'apt_repo': "file://" + str(test_data / "test_packages"),
                            'directory': '.'
                        }
                    ]
                },
                f
            )

    def test_missing(self) -> None:
        with pytest.raises(ConfigError, match="^Cannot find package nonexisting-package$"):
            SpecializationUnpacker("nonexisting-package", self.config)

    def test_empty(self) -> None:
        with pytest.raises(ConfigError, match="^Expected exactly one schema.yaml in specialization package, found 0.$"):
            SpecializationUnpacker("test-empty", self.config)

    def test_simple(self) -> None:
        unpacker = SpecializationUnpacker("test-simple", self.config)
        assert unpacker.directory.relative_to(unpacker._tmp_dir.name) == Path("a/b")

        path = Path(unpacker._tmp_dir.name)
        del unpacker
        assert path.exists() is False

    def test_multiple(self) -> None:
        with pytest.raises(ConfigError, match="^Expected exactly one schema.yaml in specialization package, found 2.$"):
            SpecializationUnpacker("test-multiple", self.config)

    def test_manual(self) -> None:
        unpacker = SpecializationUnpacker("test-multiple", self.config, "a/b")
        assert unpacker.directory.relative_to(unpacker._tmp_dir.name) == Path("a/b")

    def test_cli(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        sys.argv = [
            "hypervisor_config",
            "--specialization-package", "test-ebclfsa",
            str(test_data / "examples" / "qemu_ebclfsa" / "config.yaml"),
            str(tmp_path / "out")
        ]
        # Missing repo config leads to system exit
        with pytest.raises(SystemExit):
            hv_main()
        assert capsys.readouterr().err.endswith(
            "If a SPECIALIZATION_PACKAGE is specified a REPO_CONFIG must be specified as well\n"
        )

        sys.argv = [
            "hypervisor_config",
            "--specialization-package", "test-ebclfsa",
            "--repo-config", str(self.config),
            str(test_data / "examples" / "qemu_ebclfsa" / "config.yaml"),
            str(tmp_path / "out")
        ]
        hv_main()

        compare_directories(tmp_path / "out", test_data / "examples" / "qemu_ebclfsa" / "expected")


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
        sys.argv += ["--specialization", str(extension_dir)]
    hv_main()

    compare_directories(tmp_path, expected_dir)
