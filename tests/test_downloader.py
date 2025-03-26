import tempfile
import os
import pytest

from ebcl.tools.downloader.downloader import PackageDownloader


class TestPackageDownloader:

    packageDownloader: PackageDownloader
    yaml: str
    temp_dir: str

    @classmethod
    def setup_class(cls):
        """ Prepare downloader object. """
        test_dir = os.path.dirname(os.path.abspath(__file__))
        cls.yaml = os.path.join(test_dir, 'data', 'root.yaml')
        # Prepare generator
        cls.temp_dir = tempfile.mkdtemp()
        cls.packageDownloader = PackageDownloader(cls.yaml, cls.temp_dir)

    @pytest.mark.requires_download
    def test_download_packages(self):
        """ Test download packages. """
        self.packageDownloader.download_packages('busybox-static', self.temp_dir, 'amd64', False)
        assert os.path.exists(os.path.join(self.temp_dir, 'contents/bin/busybox'))
