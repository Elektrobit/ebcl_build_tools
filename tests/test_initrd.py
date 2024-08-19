""" Unit tests for the EBcL initrd generator. """
import os
import tempfile

from pathlib import Path

from ebcl.common.fake import Fake
from ebcl.tools.initrd.initrd import InitrdGenerator
from ebcl.common.version import VersionDepends

from ebcl.common.types.cpu_arch import CpuArch


class TestInitrd:
    """ Unit tests for the EBcL initrd generator. """

    yaml: str
    temp_dir: str
    generator: InitrdGenerator
    fake: Fake

    @classmethod
    def setup_class(cls):
        """ Prepare initrd generator. """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        cls.yaml = os.path.join(test_dir, 'data', 'initrd.yaml')
        # Prepare generator
        cls.temp_dir = tempfile.mkdtemp()
        cls.generator = InitrdGenerator(cls.yaml, cls.temp_dir)
        cls.fake = Fake()

    @classmethod
    def teardown_class(cls):
        """ Remove temp_dir. """
        cls.fake.run_sudo(f'rm -rf {cls.temp_dir}')

    def test_read_config(self):
        """ Test yaml config loading. """
        generator = InitrdGenerator(self.yaml, self.temp_dir)
        assert generator.config.arch == CpuArch.ARM64
        assert generator.config.root_device == '/dev/mmcblk0p2'

    def test_install_busybox(self):
        """ Test yaml config loading. """
        self.generator.install_busybox()

        assert os.path.isfile(os.path.join(
            self.generator.target_dir, 'bin', 'busybox'))
        assert os.path.islink(os.path.join(
            self.generator.target_dir, 'bin', 'sh'))

    def test_download_deb_package(self):
        """ Test modules package download. """
        vd = VersionDepends(
            name='linux-modules-5.15.0-1023-s32-eb',
            package_relation=None,
            version_relation=None,
            version=None,
            arch=self.generator.config.arch
        )
        package = self.generator.config.proxy.find_package(vd)
        assert package

        pkg = self.generator.config.proxy.download_package(
            self.generator.config.arch, package)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

    def test_extract_modules_from_deb(self):
        """ Test modules package download. """
        vd = VersionDepends(
            name='linux-modules-5.15.0-1023-s32-eb',
            package_relation=None,
            version_relation=None,
            version=None,
            arch=self.generator.config.arch
        )
        package = self.generator.config.proxy.find_package(vd)
        assert package

        pkg = self.generator.config.proxy.download_package(
            self.generator.config.arch, package)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

        mods_temp = tempfile.mkdtemp()

        pkg.extract(mods_temp)

        module = 'kernel/pfeng/pfeng.ko'
        self.generator.config.modules = [module]

        kversion = self.generator.find_kernel_version(mods_temp)
        assert kversion

        self.generator.copy_modules(mods_temp)

        self.fake.run_sudo(f'rm -rf {mods_temp}', check=False)

        assert os.path.isfile(os.path.join(
            self.generator.config.target_dir, 'lib', 'modules', kversion, module))

    def test_add_devices(self):
        """ Test device node creation. """
        self.generator.config.devices = [{
            'name': 'console',
            'type': 'char',
            'major': '5',
            'minor': '1',
        }]

        self.generator.install_busybox()
        self.generator.add_devices()

        device = Path(self.generator.config.target_dir) / 'dev' / 'console'
        assert device.is_char_device()

    def test_copy_files(self):
        """ Test copying of files. """
        self.generator.config.host_files = [
            {
                'source': f'{os.path.dirname(__file__)}/data/dummy.txt',
                'destination': 'root'
            },
            {
                'source': f'{os.path.dirname(__file__)}/data/other.txt',
                'destination': 'root',
                'mode': '700',
                'uid': '123',
                'gid': '456'
            }
        ]

        os.mkdir(os.path.join(self.generator.config.target_dir, 'root'))

        self.generator.install_busybox()
        self.generator.config.fh.copy_files(
            self.generator.config.host_files,
            self.generator.target_dir)

        (out, err, _returncode) = self.fake.run_sudo(
            f'stat -c \'%a\' {self.generator.target_dir}/root/dummy.txt')
        assert out is not None
        out = out.split('\n')[-2]
        assert out.strip() == '600'
        assert not err.strip()

        (out, err, _returncode) = self.fake.run_sudo(
            f'stat -c \'%u %g\' {self.generator.target_dir}/root/dummy.txt')
        assert out is not None
        out = out.split('\n')[-2]
        assert out.strip() == f'0 0'
        assert not err.strip()

        (out, err, _returncode) = self.fake.run_sudo(
            f'stat -c \'%a\' {self.generator.target_dir}/root/other.txt')
        assert out is not None
        out = out.split('\n')[-2]
        assert out.strip() == '700'

        (out, err, _returncode) = self.fake.run_sudo(
            f'stat -c \'%u %g\' {self.generator.target_dir}/root/other.txt')
        assert out is not None
        out = out.split('\n')[-2]
        assert out.strip() == '123 456'
        assert not err.strip()

    def test_initrd_is_created(self):
        """ Test that the initrd.img is created. """
        out = tempfile.mkdtemp()

        generator = InitrdGenerator(self.yaml, out)
        out = generator.create_initrd()
        assert out
        assert os.path.isfile(out)

        self.fake.run_sudo(f'rm -rf {out}', check=False)
