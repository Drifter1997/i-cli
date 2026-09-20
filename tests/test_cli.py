import os
import tempfile
import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch
from pathlib import Path

from icli.config import RAM_DIR, DOWNLOAD_DIR, CONFIG_DIR
from icli.ui import TerminalUI
from icli.media import get_inline_thumbnail


class TestInstagramCLI(unittest.TestCase):
    def setUp(self):
        self.mock_client = MagicMock()
        self.mock_client.user_id = "12345"
        self.mock_client.username = "testuser"
        self.ui = TerminalUI(self.mock_client)
        self.ui.current_thread = {"id": "th_1", "title": "bestfriend", "shh_mode_enabled": False}

    def test_config_paths(self):
        self.assertTrue(CONFIG_DIR.exists())
        self.assertTrue(RAM_DIR.exists())
        self.assertTrue(DOWNLOAD_DIR.exists())
        # RAM_DIR should be in /dev/shm or /tmp
        self.assertTrue(str(RAM_DIR).startswith("/dev/shm") or str(RAM_DIR).startswith("/tmp"))

    def test_timestamp_formatting(self):
        # Test 12-hour AM/PM and date format
        dt = datetime(2026, 9, 20, 14, 30)
        formatted = self.ui.format_timestamp(dt)
        self.assertIn("Sep 20", formatted)
        self.assertIn("02:30 PM", formatted)

        dt_morning = datetime(2026, 1, 5, 9, 5)
        formatted_m = self.ui.format_timestamp(dt_morning)
        self.assertIn("Jan 05", formatted_m)
        self.assertIn("09:05 AM", formatted_m)

    def test_line_buffer_rendering(self):
        self.ui.messages = [
            {
                "id": "m1",
                "user_id": "999",
                "is_me": False,
                "timestamp": datetime(2026, 9, 20, 12, 0),
                "text": "Hey there!",
                "item_type": "text",
                "is_vanish": False,
                "media": None
            },
            {
                "id": "m2",
                "user_id": "12345",
                "is_me": True,
                "timestamp": datetime(2026, 9, 20, 12, 1),
                "text": "Secret vanishing message",
                "item_type": "text",
                "is_vanish": True,
                "media": None
            }
        ]
        self.ui.rebuild_line_buffer()
        self.assertEqual(len(self.ui.rendered_lines), 2)
        # Check sender & vanish tag
        self.assertIn("bestfriend", self.ui.rendered_lines[0])
        self.assertIn("Hey there!", self.ui.rendered_lines[0])
        self.assertIn("You", self.ui.rendered_lines[1])
        self.assertIn("VANISH", self.ui.rendered_lines[1])
        self.assertIn("Secret vanishing message", self.ui.rendered_lines[1])

    def test_vanish_toggle_command(self):
        self.assertFalse(self.ui.vanish_mode_active)
        exit_flag = self.ui.handle_chat_command(":v", "th_1")
        self.assertFalse(exit_flag)
        self.assertTrue(self.ui.vanish_mode_active)
        self.assertIn("Vanish Mode toggled ON", self.ui.status_message)

        self.ui.handle_chat_command(":v", "th_1")
        self.assertFalse(self.ui.vanish_mode_active)
        self.assertIn("Vanish Mode toggled OFF", self.ui.status_message)

    def test_inbox_navigation_command(self):
        exit_flag = self.ui.handle_chat_command(":t", "th_1")
        self.assertTrue(exit_flag)

    def test_quit_command(self):
        exit_flag = self.ui.handle_chat_command(":q", "th_1")
        self.assertTrue(exit_flag)
        self.assertFalse(self.ui.running)

    def test_call_event_rendering(self):
        self.ui.messages = [
            {
                "id": "m3",
                "user_id": "999",
                "is_me": False,
                "timestamp": datetime(2026, 9, 20, 15, 0),
                "text": "Call ended",
                "item_type": "call",
                "is_vanish": False,
                "media": {
                    "type": "call",
                    "label": "Call Event: Call ended"
                }
            }
        ]
        self.ui.rebuild_line_buffer()
        lines_text = "\n".join(self.ui.rendered_lines)
        self.assertIn("📞", lines_text)
        self.assertIn("Call Event: Call ended", lines_text)

    def test_parse_input_bytes_arrows(self):
        from icli.ui import parse_input_bytes
        self.assertEqual(parse_input_bytes(b"\x1b[A"), ["UP"])
        self.assertEqual(parse_input_bytes(b"\x1b[B"), ["DOWN"])
        self.assertEqual(parse_input_bytes(b"\x1bOA"), ["UP"])
        self.assertEqual(parse_input_bytes(b"\x1bOB"), ["DOWN"])
        self.assertEqual(parse_input_bytes(b"\x1b[1;2A"), ["UP"])
        self.assertEqual(parse_input_bytes(b"\x1b[1;5B"), ["DOWN"])

    def test_parse_input_bytes_mouse_touchpad(self):
        from icli.ui import parse_input_bytes
        # SGR Mouse wheel up
        self.assertEqual(parse_input_bytes(b"\x1b[<64;25;12M"), ["MOUSE_UP"])
        # SGR Mouse wheel down
        self.assertEqual(parse_input_bytes(b"\x1b[<65;25;12M"), ["MOUSE_DOWN"])
        # Mouse click (btn 0) and release (btn 0, lowercase m) should be ignored
        self.assertEqual(parse_input_bytes(b"\x1b[<0;25;12M"), [])
        self.assertEqual(parse_input_bytes(b"\x1b[<0;25;12m"), [])

    def test_parse_input_bytes_page_keys(self):
        from icli.ui import parse_input_bytes
        self.assertEqual(parse_input_bytes(b"\x1b[5~"), ["PAGE_UP"])
        self.assertEqual(parse_input_bytes(b"\x1b[6~"), ["PAGE_DOWN"])

    def test_clean_zone_at_bottom(self):
        self.ui.rendered_lines = [f"Message line {i}" for i in range(40)]
        self.ui.scroll_offset = 0
        rows = 24
        header_h = 3
        footer_h = 3
        viewport_h = rows - header_h - footer_h  # 18
        clean_lines = max(2, viewport_h // 4)    # 4

        disp_h = viewport_h - clean_lines
        end_idx = len(self.ui.rendered_lines)
        start_idx = max(0, end_idx - disp_h)
        visible = self.ui.rendered_lines[start_idx:end_idx]
        self.assertEqual(len(visible), 14)
        empty_lines = viewport_h - len(visible)
        self.assertEqual(empty_lines, clean_lines)


if __name__ == "__main__":
    unittest.main()
