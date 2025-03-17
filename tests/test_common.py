"""Tests for the common module functions."""

import logging
import os
import shutil

from pathlib import Path

from pytest_mock import MockerFixture
from pytest import CaptureFixture, LogCaptureFixture

from ebcl.common import init_logging, bug, promo, log_exception, get_cache_folder


test_data = Path(__file__).parent / "data"


class TestCommon:
    """Tests for the common module functions."""

    def test_init_logging(self, caplog: LogCaptureFixture) -> None:
        """
        Test the logging setup.

        Args:
            caplog:
                Capture logs.
        """
        caplog.set_level(logging.INFO)

        init_logging()

        assert "Setting log level to INFO. (default: INFO, env: None)" in caplog.text

    def test_init_logging_debug(self, caplog: LogCaptureFixture) -> None:
        """
        Test the logging setup with explicit log level.

        Args:
            caplog:
                Capture logs.
        """
        caplog.set_level(logging.INFO)

        init_logging(level="DEBUG")

        assert "Setting log level to DEBUG. (default: DEBUG, env: None)" in caplog.text

    def test_init_logging_env(self, caplog: LogCaptureFixture) -> None:
        """
        Test the logging setup with log level from env.

        Args:
            caplog:
                Capture logs.
        """
        caplog.set_level(logging.INFO)

        os.environ["LOG_LEVEL"] = "DEBUG"

        init_logging(level="INFO")

        assert "Setting log level to DEBUG. (default: INFO, env: DEBUG)" in caplog.text

        os.environ["LOG_LEVEL"] = ""

    def test_bug(self, capsys: CaptureFixture) -> None:
        """
        Test the bug message.

        Args:
            capsys:
                Capture sysout.
        """
        bug()

        captured = capsys.readouterr()

        assert "Seems you hit a bug!" in captured.out
        assert "https://github.com/Elektrobit/ebcl_build_tools/issues" in captured.out

    def test_bug_url(self, capsys: CaptureFixture) -> None:
        """
        Test the bug message.

        Args:
            capsys:
                Capture sysout.
        """
        bug(bug_url="https://github.com/Elektrobit/ebcl_template/issues")

        captured = capsys.readouterr()

        assert "Seems you hit a bug!" in captured.out
        assert "https://github.com/Elektrobit/ebcl_template/issues" in captured.out

    def test_promo(self, capsys: CaptureFixture) -> None:
        """
        Test the promo message.

        Args:
            capsys:
                Capture sysout.
        """
        promo()

        captured = capsys.readouterr()

        assert "Do you need embedded (Linux) engineering services?" in captured.out

    def test_promo_release(self, capsys: CaptureFixture) -> None:
        """
        Test the promo message for EBcL releases.

        Args:
            capsys:
                Capture sysout.
        """
        os.environ["RELEASE_VERSION"] = "1.2.3"

        promo()

        captured = capsys.readouterr()

        assert "Thanks for using EB corbos Linux workspace 1.2.3!" in captured.out

        os.environ["RELEASE_VERSION"] = ""

    def test_log_exception(self, mocker: MockerFixture, caplog: LogCaptureFixture) -> None:
        """
        Test for log_exception annotation.

        Args:
            mocker:
                Pytest mocker.
            caplog:
                Capture logs.
        """
        caplog.set_level(logging.CRITICAL)
        mock_exit = mocker.patch("sys.exit")

        @log_exception()
        def raises_exception():
            raise Exception("My exception.")

        raises_exception()

        mock_exit.assert_not_called()
        assert "My exception." in caplog.text

    def test_log_exception_and_exit(self, mocker: MockerFixture, caplog: LogCaptureFixture) -> None:
        """
        Test for log_exception annotation for calling exit.

        Args:
            mocker:
                Pytest mocker.
            caplog:
                Capture logs.
        """
        mock_exit = mocker.patch("sys.exit")
        caplog.set_level(logging.CRITICAL)

        @log_exception(call_exit=True, code=123)
        def raises_exception():
            raise Exception("My exception.")

        raises_exception()

        mock_exit.assert_called_once_with(123)
        assert "My exception." in caplog.text

    def test_log_exception_no_exception(self, mocker: MockerFixture, caplog: LogCaptureFixture) -> None:
        """
        Test for log_exception annotation for calling exit.

        Args:
            mocker:
                Pytest mocker.
            caplog:
                Capture logs.
        """
        mock_exit = mocker.patch("sys.exit")
        caplog.set_level(logging.CRITICAL)

        @log_exception()
        def no_exception() -> int:
            return 456

        result = no_exception()

        assert result == 456
        mock_exit.assert_not_called()
        assert caplog.text == ""

    def test_get_cache_folder_no_state(self) -> None:
        """
        Test get_cache_folder without state folder.
        """
        state_folder = Path("/workspace/state")
        base_folder = Path.home() / ".ebcl_build_cache"

        # Delete state folder, if exists.
        if state_folder.is_dir():
            shutil.rmtree(state_folder)

        cache_folder = get_cache_folder("cache")

        assert cache_folder.is_dir()
        assert cache_folder.name == "cache"
        assert cache_folder.parent == base_folder

    def test_get_cache_folder_with_state(self) -> None:
        """
        Test get_cache_folder without state folder.
        """
        state_folder = Path("/workspace/state")

        # Create state folder
        os.makedirs(state_folder, exist_ok=True)

        cache_folder = get_cache_folder("cache")

        assert cache_folder.is_dir()
        assert cache_folder.name == "cache"
        assert cache_folder.parent == state_folder
