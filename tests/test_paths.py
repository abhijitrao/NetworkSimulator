"""Platform-specific writable data directory tests."""
import tempfile
import unittest
from pathlib import Path

from simulator.paths import get_data_dir


class DataDirectoryTests(unittest.TestCase):
    def test_linux_uses_xdg_data_home_when_set(self):
        result = get_data_dir(
            platform="linux",
            environ={"XDG_DATA_HOME": "/var/tmp/test-data"},
            home=Path("/home/test-user"),
        )
        self.assertEqual(result, Path("/var/tmp/test-data/network-simulator"))

    def test_linux_defaults_to_user_local_share(self):
        result = get_data_dir(
            platform="linux",
            environ={},
            home=Path("/home/test-user"),
        )
        self.assertEqual(result, Path("/home/test-user/.local/share/network-simulator"))

    def test_windows_keeps_portable_data_directory(self):
        result = get_data_dir(
            platform="win32",
            environ={},
            app_dir=Path("D:/Tools/NetworkSimulator"),
        )
        self.assertEqual(result, Path("D:/Tools/NetworkSimulator/data"))

    def test_linux_directory_can_be_created_without_application_directory_access(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = get_data_dir(
                platform="linux",
                environ={"XDG_DATA_HOME": temp_dir},
            )
            data_dir.mkdir(parents=True)
            self.assertTrue(data_dir.is_dir())


if __name__ == "__main__":
    unittest.main()
