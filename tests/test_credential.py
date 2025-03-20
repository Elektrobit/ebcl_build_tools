from .data.flat_repo.secure_repo import Server
import os
import pytest

from ebcl.common.fake import Fake
from ebcl.tools.root.root import RootGenerator
from ebcl.tools.initrd.initrd import InitrdGenerator


@pytest.mark.dev_container
class TestCredential:

    yaml: str
    yaml_debootstrap: str
    server: Server
    repo_dir: str
    fake: Fake
    data_dir: str
    auth_path: str

    @classmethod
    def setup_class(cls):
        cls.fake = Fake()
        tmp = os.path.join(os.path.dirname(__file__), 'data')
        cls.yaml = os.path.join(tmp, 'repo_local.yaml')
        cls.yaml_debootstrap = os.path.join(tmp, 'repo_local_debootrap.yaml')
        cls.repo_dir = '/workspace/results/packages/'
        cls.data_dir = os.path.join(tmp, 'flat_repo/')
        cls.auth_path = '/workspace/tools/user_config/auth.d/localrepo.conf'

        # setup basic repo
        cls.fake.run_cmd(f'{cls.data_dir}/credential_repo_setup {cls.data_dir}')

        cls.server = Server(port=8088, username='ebcl', password='ebcl', directory=cls.repo_dir)
        cls.server.start()

    @classmethod
    def teardown_class(cls):
        cls.server.stop()
        cls.fake.run_cmd(f'rm -fr {cls.repo_dir}/*')

    def test_auth_debootstrap(self, tmp_path):
        self.fake.run_cmd(f'install -m 600 {self.data_dir}/auth.d/good.conf {self.auth_path}')
        self.fake.run_cmd('rm -fr /workspace/state/*')
        print(f'tmp_path -- {tmp_path}')

        generator = RootGenerator(self.yaml_debootstrap, tmp_path, False)
        generator.config.use_ebcl_apt = False
        generator.config.primary_distro = 'jammy'

        generator.create_root()
        try:
            assert self.server.get_last_auth_status()
        finally:
            generator.finalize()

    def test_auth_rootfs(self, tmp_path):
        self.fake.run_cmd(f'install -m 600 {self.data_dir}/auth.d/good.conf {self.auth_path}')
        self.fake.run_cmd('rm -fr /workspace/state/*')

        generator = RootGenerator(self.yaml, tmp_path, False)
        archive = generator.create_root()
        try:
            assert archive
            assert os.path.isfile(archive)
        finally:
            generator.finalize()

    def test_auth_initrd(self, tmp_path):
        self.fake.run_cmd(f'install -m 600 {self.data_dir}/auth.d/good.conf {self.auth_path}')
        self.fake.run_cmd('rm -fr /workspace/state/*')

        initrd = InitrdGenerator(self.yaml, tmp_path)
        image = None
        image = initrd.create_initrd()

        try:
            assert image
            assert os.path.isfile(os.path.join(
                initrd.target_dir, 'bin', 'busybox'))
            # just for testing ebcl-doc is made it as amd64 instead of all
            assert os.path.isfile(os.path.join(
                initrd.target_dir, 'etc', 'ebcl_doc.txt'))
        finally:
            initrd.finalize()

    @pytest.mark.skip(reason="credential negative tests are skipped to avoid unwanted delays ")
    def test_auth_rootfs_neg(self, tmp_path):
        print("negative: basic rootfs creation with credential's protected apt repo")
        self.fake.run_cmd(f'install -m 600 {self.data_dir}/auth.d/wrong.conf {self.auth_path}')
        self.fake.run_cmd('rm -fr /workspace/state/*')

        generator = RootGenerator(self.yaml, tmp_path, False)
        archive = None
        archive = generator.create_root()
        try:
            assert archive is None
        finally:
            generator.finalize()

    @pytest.mark.skip(reason="credential negative tests are skipped to avoid unwanted delays ")
    def test_auth_initrd_neg(self, tmp_path):
        print("negative: basic initrd creation with credential's protected apt repo")
        self.fake.run_cmd(f'install -m 600 {self.data_dir}/auth.d/wrong.conf {self.auth_path}')
        self.fake.run_cmd('rm -fr /workspace/state/*')

        initrd = InitrdGenerator(self.yaml, tmp_path)
        image = initrd.create_initrd()
        try:
            assert image is None
        finally:
            initrd.finalize()

    @pytest.mark.skip(reason="credential negative tests are skipped to avoid unwanted delays ")
    def test_apt_http_connection_neg(self, tmp_path):
        print("negative: apt with credential: https/http missing in auth files")
        self.fake.run_cmd(f'install -m 600 {self.data_dir}/auth.d/without_http.conf {self.auth_path}')
        self.fake.run_cmd('rm -fr /workspace/state/*')

        generator = RootGenerator(self.yaml, tmp_path, False)
        archive = None
        archive = generator.create_root()
        try:
            assert archive is None
        finally:
            generator.finalize()
