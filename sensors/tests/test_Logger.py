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

    def test_add_log_exception(self):
        """Covers the 'except Exception as e' branch in add_log."""
        # Patching open to raise an exception
        with patch("builtins.open", side_effect=Exception("File System Lock")):
            # We wrap this in a print patch to verify the error is printed 
            # without actually cluttering your test console output
            with patch("builtins.print") as mock_print:
                add_log("Error trigger test")
                # Verify the error was handled and printed
                mock_print.assert_called_with("❌ Logger Error: File System Lock")
    
    def test_get_logs_success(self):
        """Covers the successful read branch."""
        # Prepare mock file content
        file_content = "Line 1\nLine 2\n"
        with patch("os.path.exists", return_value=True):
            with patch("builtins.open", mock_open(read_data=file_content)):
                logs = get_logs()
                self.assertEqual(logs, "Line 1\nLine 2\n")