from unittest.mock import mock_open, patch

from django.test import TestCase

from ..logger import add_log
from ..utils import get_logs


class LoggerTest(TestCase):
    def test_get_logs_file_not_found(self):
        """Covers the 'if not os.path.exists' branch"""
        with patch("os.path.exists", return_value=False):
            self.assertIn("System Initialized", get_logs())

    def test_get_logs_exception(self):
        """Covers the 'except Exception' branch"""
        with patch("builtins.open", side_effect=Exception("Read Error")):
            self.assertEqual(get_logs(), "Error reading log file.")

    def test_add_log_success(self):
        """Covers the 'try' branch of adding logs"""
        with patch("builtins.open", mock_open()) as mocked_file:
            add_log("Test Message")
            mocked_file().write.assert_called()
