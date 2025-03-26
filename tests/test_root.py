""" Unit tests for the EBcL root generator. """
import os
import shutil
import tempfile

import pytest

from ebcl.common.apt import Apt
from ebcl.common.config import Config
from ebcl.common.fake import Fake
from ebcl.tools.root.root import RootGenerator
from ebcl.tools.root.debootstrap import DebootstrapRootGenerator

from ebcl.common.types.build_type import BuildType
from ebcl.common.types.cpu_arch import CpuArch


class TestRoot:
    """ Unit tests for the EBcL root generator. """

    yaml: str
    temp_dir: str
    result_dir: str
    generator: RootGenerator

    @classmethod
    def setup_class(cls):
        """ Prepare root generator. """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        cls.yaml = os.path.join(test_dir, 'data', 'root.yaml')
        # Prepare generator
        cls.temp_dir = tempfile.mkdtemp()
        cls.generator = RootGenerator(cls.yaml, cls.temp_dir, False)

        cls.result_dir = tempfile.mkdtemp()
        cls.generator.result_dir = cls.result_dir

    @classmethod
    def teardown_class(cls):
        """ Remove temp_dir. """
        shutil.rmtree(cls.temp_dir)
        shutil.rmtree(cls.result_dir)
        shutil.rmtree(cls.output_path)

    def test_read_config(self):
        """ Test yaml config loading. """
        assert self.generator.config.image is None
        assert self.generator.config.type == BuildType.DEBOOTSTRAP

    @pytest.mark.skip(reason="Kiwi doesn't work with AWS hosted linux.elektrobit.com")
    @pytest.mark.dev_container
    def test_build_kiwi_image(self):
        """ Test kiwi image build. """
        # EBcL dev container required - root generator calls berrymill as subprocess
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_kiwi.yaml')
        generator = RootGenerator(yaml, self.temp_dir, False)

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

    @pytest.mark.skip(reason="Kiwi doesn't work with AWS hosted linux.elektrobit.com")
    @pytest.mark.dev_container
    def test_build_kiwi_no_berry(self):
        """ Test kiwi image build without berrymill. """
        # EBcL dev container required - root generator calls kiwi-ng as subprocess
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_kiwi_berry.yaml')
        generator = RootGenerator(yaml, self.temp_dir, False)

        generator.apt_repos = [Apt.ebcl_apt(CpuArch.AMD64)]

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

    @pytest.mark.skip(reason="Kiwi doesn't work with AWS hosted linux.elektrobit.com")
    @pytest.mark.dev_container
    def test_build_kiwi_no_bootstrap(self):
        """ Test kiwi image build without bootstrap package. """
        # EBcL dev container required - root generator calls kiwi-ng as subprocess
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_kiwi_debo.yaml')
        generator = RootGenerator(yaml, self.temp_dir, False)

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

    @pytest.mark.skip(reason="Kiwi doesn't work with AWS hosted linux.elektrobit.com")
    @pytest.mark.dev_container
    def test_build_sysroot_kiwi(self):
        """ Test kiwi image build. """
        # EBcL dev container required - root generator calls kiwi-ng as subprocess
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'sysroot_kiwi.yaml')
        generator = RootGenerator(yaml, self.temp_dir, False)

        generator.apt_repos = [Apt.ebcl_apt(CpuArch.AMD64)]

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

    @pytest.mark.requires_download
    def test_build_debootstrap(self):
        """ Test build root.tar. """
        # Requires debootstrap and some other tools.
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_debootstrap.yaml')
        generator = RootGenerator(yaml, self.temp_dir, False)

        generator.apt_repos = [Apt.ebcl_apt(CpuArch.AMD64)]

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

        # Check that apt config was added
        fake = Fake()
        fake.run_cmd(f'tar -tvf {archive} | grep "preferences.d/linux.elektrobit.com"', check=True)
        fake.run_cmd(f'tar -tvf {archive} | grep "preferences.d/aptconfig2"', check=True)
        fake.run_cmd(f'tar -tvf {archive} | grep "preferences.d/aptconfig3"', check=True)
        fake.run_cmd(f'tar -tvf {archive} | grep "preferences.d/aptconfig4"', check=True)
        fake.run_cmd(f'tar -tvf {archive} | grep "preferences.d/aptconfig5"', check=True)

    @pytest.mark.requires_download
    def test_build_sysroot(self):
        """ Test build sysroot root.tar. """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_sysroot.yaml')
        generator = RootGenerator(yaml, self.temp_dir, True)

        generator.apt_repos = [Apt.ebcl_apt(CpuArch.AMD64)]

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

        # Check that iproute was added
        fake = Fake()
        fake.run_cmd(f'tar -tvf {archive} | grep "/bin/ip"', check=True)


    def test_get_package_hash(self):
        """ Test for apt config hash algorithm. """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_debootstrap.yaml')

        config = Config(yaml, self.temp_dir)

        generator = DebootstrapRootGenerator(config, self.temp_dir)

        apt_hash = '01ab76374f82438e4c32ec1df0e480d8'

        hash = generator._get_package_hash(apt_hash)

        assert hash == '54b54b43bf89e6967d4d87d0416e1574'
