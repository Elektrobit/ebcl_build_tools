""" Unit tests for the EBcL boot generator. """
import os
import shutil
import tempfile

import pytest

from ebcl.common.apt import Apt
from ebcl.tools.root.root import RootGenerator

from ebcl.common.types.build_type import BuildType
from ebcl.common.types.cpu_arch import CpuArch


class TestRoot:
    """ Unit tests for the EBcL boot generator. """

    yaml: str
    temp_dir: str
    result_dir: str
    generator: RootGenerator

    @classmethod
    def setup_class(cls):
        """ Prepare initrd generator. """
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

    def test_read_config(self):
        """ Test yaml config loading. """
        assert self.generator.config.image is None
        assert self.generator.config.type == BuildType.DEBOOTSTRAP

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

    @pytest.mark.dev_container
    def test_build_root_archive(self):
        """ Test build root.tar. """
        # EBcL dev container required - root generator calls elbe as subprocess
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'root_elbe.yaml')
        generator = RootGenerator(yaml, self.temp_dir, False)

        archive = generator.create_root()
        assert archive
        assert os.path.isfile(archive)

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

    @pytest.mark.dev_container
    def test_build_sysroot_elbe(self):
        """ Test build root.tar. """
        # EBcL dev container required - root generator calls elbe as subprocess
        test_dir = os.path.dirname(os.path.abspath(__file__))
        yaml = os.path.join(test_dir, 'data', 'sysroot_elbe.yaml')
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

        archive = generator.create_root(run_scripts=False)
        assert archive
        assert os.path.isfile(archive)
