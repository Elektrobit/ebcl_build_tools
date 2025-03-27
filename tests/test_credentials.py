import shutil
import subprocess
import os
import pytest

from pathlib import Path

from .data.credentials_repo.repo_server import Server
from ebcl.tools.root.root import RootGenerator
from ebcl.tools.initrd.initrd import InitrdGenerator

test_data = Path(__file__).parent / "data"
PASSWORD = "supersecret_credential"


@pytest.mark.dev_container
class TestCredentials:
    AUTH_PATH = Path('/workspace/tools/user_config/auth.d/cred_test.conf')

    server: Server

    def setup_method(self) -> None:
        """Setup method run before each test"""
        # Generate test repository
        subprocess.run(
            ["make"],
            check=True,
            shell=True,
            cwd=test_data / "credentials_repo"
        )
        self.server = Server(
            port=8088,
            username='ebcl',
            password=PASSWORD,
            directory=str(test_data / "credentials_repo" / "repo")
        )
        self.server.start()

        self.AUTH_PATH.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(test_data / "credentials_repo" / "auth.d" / "credentials.conf", self.AUTH_PATH)

    def teardown_method(self) -> None:
        """Teardown method run before each test"""
        self.server.stop()
        self.AUTH_PATH.unlink()

    def test_auth_debootstrap(self, tmp_path: Path) -> None:
        generator = RootGenerator(str(test_data / "repo_local_debootrap.yaml"), str(tmp_path), False)

        assert not self.server.get_last_auth_status()
        generator.create_root()
        generator.finalize()
        assert self.server.get_last_auth_status()

    @pytest.mark.requires_download
    def test_auth_rootfs(self, tmp_path: Path) -> None:
        generator = RootGenerator(str(test_data / "repo_local.yaml"), str(tmp_path), False)
        archive = generator.create_root()
        generator.finalize()

        assert archive
        assert os.path.isfile(archive)

        result_dir = tmp_path / "result"
        result_dir.mkdir()
        subprocess.run(
            ["fakeroot", "tar", "-xf", archive],
            check=True,
            cwd=result_dir
        )
        res = subprocess.run(
            ["grep", "-rl", "Hi from EBcL development team!", "."],
            cwd=result_dir,
            stdout=subprocess.PIPE,
            encoding="ASCII"
        )
        assert "./cred_test.txt" in res.stdout.splitlines(), "Ensure that at least something exists and grep works"
        res = subprocess.run(
            ["grep", "-rl", PASSWORD, "."],
            cwd=result_dir,
            stdout=subprocess.PIPE,
            encoding="ASCII"
        )
        assert res.returncode == 1, "Ensure the credentials are not in the final filesystem"

    @pytest.mark.requires_download
    def test_auth_initrd(self, tmp_path: Path) -> None:
        initrd = InitrdGenerator(str(test_data / "repo_local.yaml"), str(tmp_path))
        image = initrd.create_initrd()
        initrd.finalize()

        assert image
        res = subprocess.run(
            ["cpio", "-tI", image],
            check=True,
            stdout=subprocess.PIPE,
            encoding="ASCII"
        )
        files_in_archive = res.stdout.splitlines()
        os.system(f"cpio -I {image} -t")
        assert "cred_test.txt" in files_in_archive, \
            "cred_test.txt is installed from a package in the test repository"

        result_dir = tmp_path / "result"
        result_dir.mkdir()
        subprocess.run(
            ["fakeroot", "cpio", "-diI", image],
            check=True,
            cwd=result_dir
        )
        res = subprocess.run(
            ["grep", "-rl", "Hi from EBcL development team!", "."],
            cwd=result_dir,
            stdout=subprocess.PIPE,
            encoding="ASCII"
        )
        assert "./cred_test.txt" in res.stdout.splitlines(), "Ensure that at least something exists and grep works"
        res = subprocess.run(
            ["grep", "-rl", PASSWORD, "."],
            cwd=result_dir,
            stdout=subprocess.PIPE,
            encoding="ASCII"
        )
        assert res.returncode == 1, "Ensure the credentials are not in the final filesystem"
