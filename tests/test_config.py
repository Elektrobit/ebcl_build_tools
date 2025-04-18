""" Tests for config helpers. """
import os
import shutil
import stat
import tempfile

from pathlib import Path

from ebcl.common.apt import AptDebRepo, AptFlatRepo
from ebcl.common.config import Config
from ebcl.common.files import EnvironmentType

from ebcl.common.types.build_type import BuildType
from ebcl.common.types.cpu_arch import CpuArch


class TestConfig:
    """ Tests for config helpers. """

    temp_dir: str

    @classmethod
    def setup_class(cls):
        """ Prepare cache object. """
        cls.temp_dir = tempfile.mkdtemp()

    @classmethod
    def teardown_class(cls):
        """ Delete cache folder. """
        shutil.rmtree(cls.temp_dir)

    def test_boot_yaml(self):
        """ Try to parse boot.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'boot.yaml')

        config = Config(yaml_file, self.temp_dir)

        assert len(config.apt_repos) == 4
        assert isinstance(config.apt_repos[0].repo, AptDebRepo)
        assert config.apt_repos[0].repo.dist == 'jammy'
        assert isinstance(config.apt_repos[1].repo, AptDebRepo)
        assert config.apt_repos[1].repo.dist == 'jammy-security'

        assert config.arch == CpuArch.AMD64

        assert len(config.packages) == 1
        assert config.packages[0].name == 'linux-image-generic'

        assert config.download_deps is True

        assert len(config.files) == 2
        assert config.files[0] == 'boot/vmlinuz*'
        assert config.files[1] == 'boot/config*'

        assert len(config.scripts) == 1
        assert config.scripts[0]['name'] == os.path.join(
            os.path.dirname(__file__), 'data', 'config_boot.sh')

    def test_initrd_yaml(self):
        """ Try to parse initrd.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'initrd.yaml')

        config = Config(yaml_file, self.temp_dir)

        assert len(config.apt_repos) == 4
        assert isinstance(config.apt_repos[0].repo, AptDebRepo)
        assert config.apt_repos[0].repo.dist == 'jammy'
        assert isinstance(config.apt_repos[1].repo, AptDebRepo)
        assert config.apt_repos[1].repo.dist == 'ebcl_nxp_public'

        assert config.modules == ['kernel/drivers/net/virtio_net.ko', 'bridge', 'stp', 'virtio']

        assert len(config.packages) == 0
        assert config.kernel is not None and config.kernel.name == 'linux-image-generic'

        assert config.arch == CpuArch.ARM64

        assert config.root_device == '/dev/mmcblk0p2'

        assert len(config.devices) == 2
        assert config.devices[0]['name'] == 'mmcblk1'
        assert config.devices[0]['type'] == 'block'
        assert config.devices[0]['major'] == 8
        assert config.devices[1]['name'] == 'console'
        assert config.devices[1]['type'] == 'char'
        assert config.devices[1]['major'] == 5

        assert len(config.host_files) == 2
        assert config.host_files[0]['source'] == os.path.join(
            os.path.dirname(__file__), 'data', 'dummy.txt')
        assert config.host_files[0]['destination'] == 'root'
        assert config.host_files[1]['source'] == os.path.join(
            os.path.dirname(__file__), 'data', 'other.txt')
        assert config.host_files[1]['destination'] == 'root'

    def test_initrd_with_flat_repo_yaml(self):
        """ Try to parse initrd_with_flat.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'initrd_with_flat.yaml')

        config = Config(yaml_file, self.temp_dir)

        assert len(config.apt_repos) == 4
        assert isinstance(config.apt_repos[0].repo, AptDebRepo)
        assert config.apt_repos[0].repo.dist == 'jammy'
        assert isinstance(config.apt_repos[1].repo, AptFlatRepo)
        assert config.apt_repos[1].repo.url == 'http://example.com/'
        assert config.apt_repos[1].repo._directory == 'flat_repo'

    def test_root_yaml(self):
        """ Try to parse boot.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'root.yaml')

        config = Config(yaml_file, self.temp_dir)

        assert config.name == 'ubuntu'

        assert config.arch == CpuArch.AMD64

        assert len(config.packages) == 3
        assert config.packages[0].name == 'systemd'
        assert config.packages[1].name == 'udev'
        assert config.packages[2].name == 'util-linux'

        assert len(config.scripts) == 3
        assert config.scripts[0]['env'] == EnvironmentType.SUDO
        assert config.scripts[1]['env'] == EnvironmentType.FAKEROOT
        assert config.scripts[2]['env'] == EnvironmentType.CHROOT

    def test_root_kiwi_berry_yaml(self):
        """ Try to parse boot.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'root_kiwi_berry.yaml')

        config = Config(yaml_file, self.temp_dir)

        assert config.name == 'ubuntu'

        assert config.arch == CpuArch.AMD64

        assert len(config.packages) == 3
        assert config.packages[0].name == 'systemd'
        assert config.packages[1].name == 'udev'
        assert config.packages[2].name == 'util-linux'

        assert len(config.scripts) == 3
        assert config.scripts[0]['env'] == EnvironmentType.SUDO
        assert config.scripts[1]['env'] == EnvironmentType.FAKEROOT
        assert config.scripts[2]['env'] == EnvironmentType.CHROOT

        assert config.type == BuildType.KIWI

        assert config.kvm is True

        assert config.result_pattern == '*.tar.xz'

        assert config.use_berrymill is False

    def test_credentials(self, tmp_path: Path) -> None:
        netrc_path = Path.home() / ".netrc"
        config_file = (tmp_path / "test.yaml")
        cred_dir = tmp_path / 'cred'
        cred_dir.mkdir()

        config_file.write_text("base: []")
        config = Config(str(config_file), str(tmp_path))
        config.cred_dir = cred_dir

        netrc_path.unlink(missing_ok=True)

        config._create_netrc_file()
        assert netrc_path.exists(), "File is created, if it does not exist"
        assert stat.S_IMODE(netrc_path.stat().st_mode) == 0o600, "File mode is 600"
        assert netrc_path.read_text() == ""

        (cred_dir / "05_test.conf").write_text("file 05_test.conf")
        (cred_dir / "01_test.conf").write_text("file 01_test.conf")
        (cred_dir / "03_test.conf").write_text("file 03_test.conf")
        (cred_dir / "00_test.cnf").write_text("file 01_test.cnf")
        config._create_netrc_file()
        assert netrc_path.read_text() == "file 01_test.conf\nfile 03_test.conf\nfile 05_test.conf\n"

        for f in cred_dir.glob("*.conf"):
            f.unlink()
        config._create_netrc_file()
        assert netrc_path.read_text() == ""

        del config
        assert not netrc_path.exists()

    def test_distro_ebcl_apt_yaml(self):
        """ Try to parse boot.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'root_distro.yaml')

        config = Config(yaml_file, self.temp_dir)

        print(config.apt_repos)
        print(config.primary_distro)
