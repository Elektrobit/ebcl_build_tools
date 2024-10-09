""" Tests for config helpers. """
import os
import shutil
import tempfile

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

        assert len(config.apt_repos) == 2
        assert config.apt_repos[0].distro == 'jammy'
        assert config.apt_repos[1].distro == 'jammy-security'

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
        """ Try to parse boot.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'initrd.yaml')

        config = Config(yaml_file, self.temp_dir)

        assert len(config.apt_repos) == 2
        assert config.apt_repos[0].distro == 'jammy'
        assert config.apt_repos[1].distro == 'ebcl_nxp_public'

        assert len(config.modules) == 1
        assert config.modules[0] == 'kernel/pfeng/pfeng.ko'

        assert len(config.packages) == 0
        assert config.kernel is not None and config.kernel.name == 'linux-modules-5.15.0-1023-s32-eb'

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

        assert config.kernel_version == '5.15.0-1023-s32-eb'

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

    def test_root_elbe_yaml(self):
        """ Try to parse boot.yaml. """
        yaml_file = os.path.join(
            os.path.dirname(__file__), 'data', 'root_elbe.yaml')

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

        assert config.type == BuildType.ELBE

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
