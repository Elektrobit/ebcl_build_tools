""" Tests for the files functions. """
import os
import tempfile
import shutil

from typing import Any

from ebcl.common.apt import Apt, AptDebRepo
from ebcl.common.fake import Fake
from ebcl.common.files import (
    Files, EnvironmentType,
    parse_scripts, parse_files
)
from ebcl.common.proxy import Proxy
from ebcl.common.types.cpu_arch import CpuArch


class TestEnvironmentType:
    """ Tests for EnvironmentType. """

    def test_from_str(self):
        """ Test creation form string. """
        env = EnvironmentType.from_str('fake')
        assert env == EnvironmentType.FAKEROOT
        assert str(env) == 'fake'

        env = EnvironmentType.from_str('chroot')
        assert env == EnvironmentType.CHROOT
        assert str(env) == 'chroot'

        env = EnvironmentType.from_str('sudo')
        assert env == EnvironmentType.SUDO
        assert str(env) == 'sudo'

        env = EnvironmentType.from_str('shell')
        assert env == EnvironmentType.SHELL
        assert str(env) == 'shell'


class TestFiles:
    """ Tests for the files functions. """

    fake: Fake
    files: Files
    target_dir: str
    other_dir: str
    apt: Apt
    proxy: Proxy

    @classmethod
    def setup_class(cls):
        """ Prepare apt repo object. """
        cls.target_dir = tempfile.mkdtemp()
        cls.other_dir = tempfile.mkdtemp()
        cls.fake = Fake()
        cls.files = Files(fake=cls.fake, target_dir=cls.target_dir)

        cls.fake.run_sudo(f'echo "owned by root" > {cls.other_dir}/root')
        cls.fake.run_cmd(f'echo "owned by user" > {cls.other_dir}/user')
        cls.fake.run_cmd(f'mkdir -p {cls.other_dir}/adir/subdir')
        cls.fake.run_sudo('echo "owned by root" > '
                          f'{cls.other_dir}/adir/subdir/a')
        cls.fake.run_cmd('echo "owned by user" > '
                         f'{cls.other_dir}/adir/subdir/b')

        cls.apt = Apt(
            AptDebRepo(
                url='http://archive.ubuntu.com/ubuntu',
                dist='jammy',
                components=['main'],
                arch=CpuArch.AMD64
            )
        )
        cls.proxy = Proxy()
        cls.proxy.add_apt(cls.apt)

    @classmethod
    def teardown_class(cls):
        """ Remove temp_dir. """
        cls.fake.run_sudo(f'rm -rf {cls.target_dir}', check=False)
        cls.fake.run_sudo(f'rm -rf {cls.other_dir}', check=False)

    def test_copy_file_shell(self):
        """ Copy files using shell env. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/cp_root_shell',
            environment=EnvironmentType.SHELL
        )
        assert files

        (out, err, ret) = self.fake.run_sudo(
            f'file {self.target_dir}/cp_root_shell')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_sudo(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_root_shell')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        (mode, _err, _ret) = self.fake.run_sudo(
            f'stat -c \'%a\'  {self.other_dir}/root')
        assert mode
        mode = mode.strip()
        assert f'{os.getuid()} {os.getgid()} {mode}' in out.strip()

        files = self.files.copy_file(
            src=f'{self.other_dir}/user',
            dst=f'{self.target_dir}/cp_user_shell',
            environment=EnvironmentType.SHELL
        )
        assert files

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/cp_user_shell')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_user_shell')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        (mode, _err, _ret) = self.fake.run_cmd(
            f'stat -c \'%a\'  {self.other_dir}/user')
        assert mode
        mode = mode.strip()
        assert f'{os.getuid()} {os.getgid()} {mode}' in out.strip()

    def test_copy_file_sudo(self):
        """ Copy files using sudo env. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/cp_root_sudo',
            environment=EnvironmentType.SUDO
        )
        assert files

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/cp_root_sudo')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_root_sudo')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        (mode, _err, _ret) = self.fake.run_cmd(
            f'stat -c \'%a\'  {self.other_dir}/root')
        assert mode
        mode = mode.strip()
        assert f'0 0 {mode}' in out.strip()

        files = self.files.copy_file(
            src=f'{self.other_dir}/user',
            dst=f'{self.target_dir}/cp_user_sudo',
            environment=EnvironmentType.SUDO
        )
        assert files

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/cp_user_sudo')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_user_sudo')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 644' in out.strip()

    def test_copy_file_fakeroot(self):
        """ Copy files using fakeroot env. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/cp_root_fake',
            environment=EnvironmentType.FAKEROOT
        )
        assert files

        (out, err, ret) = self.fake.run_fake(
            f'file {self.target_dir}/cp_root_fake')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_root_fake')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        (mode, _err, _ret) = self.fake.run_fake(
            f'stat -c \'%a\'  {self.other_dir}/root')
        assert mode
        mode = mode.strip()
        assert f'0 0 {mode}' in out.strip()

        files = self.files.copy_file(
            src=f'{self.other_dir}/user',
            dst=f'{self.target_dir}/cp_user_fake',
            environment=EnvironmentType.FAKEROOT
        )
        assert files

        (out, err, ret) = self.fake.run_fake(
            f'file {self.target_dir}/cp_user_fake')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_user_fake')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        (mode, _err, _ret) = self.fake.run_fake(
            f'stat -c \'%a\'  {self.other_dir}/user')
        assert mode
        mode = mode.strip()
        assert f'0 0 {mode}' in out.strip()

    def _prepare_chroot(self):
        """ Prepare a busybox chroot env. """
        # Prepare fakeroot
        # Get busybox
        ps = self.apt.find_package('busybox-static')
        assert ps
        p = ps[0]

        pkg = self.proxy.download_package(self.apt.arch, p)
        assert pkg
        assert pkg.local_file
        assert os.path.isfile(pkg.local_file)

        pkg.extract(self.target_dir)

        # Install busybox
        (_stdout, stderr, _returncode) = self.fake.run_chroot(
            '/bin/busybox --install -s /bin', self.target_dir)
        assert stderr is not None
        assert not stderr.strip()

    def test_copy_file_chroot(self):
        """ Copy files using chroot env. """
        self._prepare_chroot()

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 755' in out.strip()

        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/afile',
            environment=EnvironmentType.SUDO
        )
        assert files

        self.files.target_dir = self.target_dir

        files = self.files.copy_file(
            src='/afile',
            dst='/root_chroot',
            environment=EnvironmentType.CHROOT
        )
        assert files

        (out, err, ret) = self.fake.run_sudo(
            f'file {self.target_dir}/root_chroot')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_chroot(
            'stat -c \'%u %g %a\'  /root_chroot',
            chroot=self.target_dir)
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 644' in out.strip()

    def test_copy_file_sudo_dir(self):
        """ Merge dirs. """
        self.fake.run_cmd(f'mkdir -p {self.target_dir}/adir')
        self.fake.run_cmd(f'touch {self.target_dir}/adir/c')

        files = self.files.copy_file(
            src=f'{self.other_dir}/adir',
            dst=f'{self.target_dir}',
            environment=EnvironmentType.SUDO
        )
        assert files

        assert os.path.isdir(f'{self.target_dir}/adir/subdir')

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/adir/subdir/a')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/adir/subdir/a')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 644' in out.strip()

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/adir/subdir/b')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/adir/subdir/b')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'{os.getuid()} {os.getgid()}' in out.strip()
        # Group permissions depend on shell config
        assert '664' in out.strip() or '644' in out.strip()

        assert os.path.isfile(f'{self.target_dir}/adir/c')

    def test_copy_file_attr(self):
        """ Copy file and set user and mode. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/cp_root_mode',
            environment=EnvironmentType.FAKEROOT,
            uid=123,
            gid=456,
            mode='774'
        )
        assert files

        (out, err, ret) = self.fake.run_fake(
            f'file {self.target_dir}/cp_root_mode')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {self.target_dir}/cp_root_mode')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '123 456 774' in out.strip()

    def test_copy_file_move(self):
        """ Move a file. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/cp_root_move',
            environment=EnvironmentType.FAKEROOT
        )
        assert files

        files = self.files.copy_file(
            src=f'{self.target_dir}/cp_root_move',
            dst=f'{self.target_dir}/mv_root_move',
            environment=EnvironmentType.FAKEROOT,
            move=True
        )
        assert files

        (out, err, ret) = self.fake.run_fake(
            f'file {self.target_dir}/mv_root_move')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {self.target_dir}/mv_root_move')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 644' in out.strip()

    def test_copy_file_delete(self):
        """ Copy a file and delete old first. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/target',
            environment=EnvironmentType.FAKEROOT
        )
        assert files

        files = self.files.copy_file(
            src=f'{self.other_dir}/user',
            dst=f'{self.target_dir}/target',
            environment=EnvironmentType.FAKEROOT,
            delete_if_exists=True
        )
        assert files

        (out, err, ret) = self.fake.run_fake(
            f'file {self.target_dir}/target')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {self.target_dir}/target')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0' in out.strip()
        # Group permissions depend on shell config
        assert '664' in out.strip() or '644' in out.strip()

        (out, err, ret) = self.fake.run_fake(
            f'cat  {self.target_dir}/target')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'owned by user' in out.strip()

    def test_copy_file_ownership(self):
        """ Copy a file and change onwer to local user. """
        files = self.files.copy_file(
            src=f'{self.other_dir}/root',
            dst=f'{self.target_dir}/root_owner',
            environment=EnvironmentType.SUDO
        )
        assert files

        files = self.files.copy_file(
            src=f'{self.target_dir}/root_owner',
            dst=f'{self.target_dir}/owned',
            environment=EnvironmentType.SHELL,
            fix_ownership=True
        )
        assert files

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/owned')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/owned')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        # Do not check file permissions, since these depend on shell config.
        assert f'{os.getuid()} {os.getgid()}' in out.strip()

        (out, err, ret) = self.fake.run_cmd(
            f'file {self.target_dir}/root_owner')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'ASCII text' in out

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {self.target_dir}/root_owner')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        # Do not check file permissions, since these depend on shell config.
        assert f'{os.getuid()} {os.getgid()}' in out.strip()

    def test_run_script_shell(self):
        """ Test for script execution. """
        self._prepare_chroot()

        script = os.path.join(os.path.dirname(__file__),
                              'data', 'config_boot.sh')

        res = self.files.run_script(
            script,
            params=f'{self.target_dir} 1234',
            environment=EnvironmentType.SHELL,
            cwd=self.target_dir
        )
        assert res
        (out, err, ret) = res
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'Temporary boot folder is {self.target_dir}' in out

    def test_run_script_sudo(self):
        """ Test for script execution in the sudo env. """
        self._prepare_chroot()

        script = os.path.join(os.path.dirname(__file__),
                              'data', 'config_boot.sh')

        res = self.files.run_script(
            script,
            params=f'{self.target_dir} 1234',
            environment=EnvironmentType.SUDO,
            cwd=self.target_dir
        )
        assert res
        (out, err, ret) = res
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'Temporary boot folder is {self.target_dir}' in out

    def test_run_script_fakeroot(self):
        """ Test for script execution in the fakeroot env. """
        self._prepare_chroot()

        script = os.path.join(os.path.dirname(__file__),
                              'data', 'config_boot.sh')

        res = self.files.run_script(
            script,
            params=f'{self.target_dir} 1234',
            environment=EnvironmentType.FAKEROOT,
            cwd=self.target_dir
        )
        assert res
        (out, err, ret) = res
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'Temporary boot folder is {self.target_dir}' in out

    def test_run_script_chroot(self):
        """ Test for script execution in the chroot env. """
        self._prepare_chroot()

        script = os.path.join(os.path.dirname(__file__),
                              'data', 'config_boot.sh')

        res = self.files.run_script(
            script,
            params='/ 1234',
            environment=EnvironmentType.CHROOT,
            cwd=self.target_dir
        )
        assert res
        (out, err, ret) = res
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert 'Temporary boot folder is /' in out

    def test_extract_tarball(self):
        """ Test for tarball extraction. """
        tar = os.path.join(os.path.dirname(__file__),
                           'data', 'data.tar.zst')

        tempdir = tempfile.mkdtemp()
        self.files.extract_tarball(tar, tempdir, True)

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {tempdir}/bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 755' in out.strip()

        # Overwrite exising files
        self.files.extract_tarball(tar, tempdir, True)

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {tempdir}/bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 755' in out.strip()

        self.fake.run_sudo(f'rm -rf {tempdir}', check=False)

    def test_extract_tarball_fake(self):
        """ Test for tarball extraction using fakeroot. """
        tar = os.path.join(os.path.dirname(__file__),
                           'data', 'data.tar.zst')

        temp = tempfile.mkdtemp()

        self.files.extract_tarball(
            archive=tar,
            directory=temp,
            use_sudo=False)

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {temp}/bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 755' in out.strip()

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {temp}/bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'{os.getuid()} {os.getgid()} 755' in out.strip()

        # Overwrite exising files
        self.files.extract_tarball(
            archive=tar,
            directory=temp,
            use_sudo=False)

        (out, err, ret) = self.fake.run_fake(
            f'stat -c \'%u %g %a\'  {temp}/bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '0 0 755' in out.strip()

        self.fake.run_sudo(f'rm -rf {temp}', check=False)

    def test_pack_root_as_tarball(self):
        """ Test for tarball packing. """
        tar = os.path.join(os.path.dirname(__file__),
                           'data', 'data.tar.zst')

        tempdir = tempfile.mkdtemp()

        self.files.extract_tarball(tar, tempdir, True)

        outdir = tempfile.mkdtemp()
        self.files.pack_root_as_tarball(
            output_dir=outdir,
            archive_name='myroot.tar',
            root_dir=tempdir,
            use_sudo=True
        )

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {outdir}/myroot.tar')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'{os.getuid()} {os.getgid()} 644' in out.strip()

        (out, err, ret) = self.fake.run_cmd(
            f'tar --list --verbose --file={outdir}/myroot.tar | grep ./bin/busybox')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert '-rwxr-xr-x root/root' in out.strip()

        # repack
        self.files.pack_root_as_tarball(
            output_dir=outdir,
            archive_name='myroot.tar',
            root_dir=tempdir,
            use_sudo=True
        )

        (out, err, ret) = self.fake.run_cmd(
            f'stat -c \'%u %g %a\'  {outdir}/myroot.tar')
        assert ret == 0
        assert err is not None
        assert not err.strip()
        assert out
        assert f'{os.getuid()} {os.getgid()} 644' in out.strip()

        self.fake.run_sudo(f'rm -rf {tempdir}', check=False)
        self.fake.run_sudo(f'rm -rf {outdir}', check=False)


class TestParsers:
    """ Tests for the config parser functions. """

    fake: Fake
    temp_dir: str

    @classmethod
    def setup_class(cls):
        """ Prepare apt repo object. """
        cls.fake = Fake()
        cls.temp_dir = tempfile.mkdtemp()

    @classmethod
    def teardown_class(cls):
        """ Remove temp_dir. """
        shutil.rmtree(cls.temp_dir)

    def test_parse_scripts(self):
        """ Test the scripts parsing. """

        data_dir = os.path.join(os.path.dirname(__file__), 'data')

        script_files = [
            {
                'env': 'chroot',
                'base_dir': data_dir
            },
            {
                'name': 'root_config_chroot.sh',
                'env': 'chroot',
                'base_dir': data_dir
            },
            {
                'name': 'data/root_config_chroot.sh',
                'env': 'sudo',
                'base_dir': os.path.dirname(__file__)
            },
            'test_files.py'
        ]

        scripts = parse_scripts(
            scripts=script_files,
            output_path=self.temp_dir,
            relative_base_dir=os.path.dirname(__file__)
        )
        assert len(scripts) == 3
        assert scripts[0]['name'] == os.path.abspath(
            os.path.join(data_dir, 'root_config_chroot.sh'))
        assert scripts[0]['env'] == EnvironmentType.CHROOT
        assert scripts[1]['name'] == os.path.abspath(
            os.path.join(data_dir, 'root_config_chroot.sh'))
        assert scripts[1]['env'] == EnvironmentType.SUDO
        assert scripts[2]['name'] == os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'test_files.py'))
        assert scripts[2]['env'] == EnvironmentType.FAKEROOT

    def test_parse_files(self) -> None:
        """ Test the scripts parsing. """

        data_dir = os.path.join(os.path.dirname(__file__), 'data')

        file_files: Any = [
            {
                'base_dir': data_dir
            },
            {
                'source': 'root_config_chroot.sh',
                'base_dir': data_dir
            },
            {
                'source': 'data/root_config_chroot.sh',
                'base_dir': os.path.dirname(__file__)
            },
            'test_files.py'
        ]

        files = parse_files(
            files=file_files,
            output_path=self.temp_dir,
            relative_base_dir=os.path.dirname(__file__)
        )

        assert len(files) == 3
        assert files[0]['source'] == os.path.abspath(
            os.path.join(data_dir, 'root_config_chroot.sh'))
        assert files[1]['source'] == os.path.abspath(
            os.path.join(data_dir, 'root_config_chroot.sh'))
        assert files[2]['source'] == os.path.abspath(
            os.path.join(os.path.dirname(__file__), 'test_files.py'))
