import os
import sys
import time
import uuid
import select
import termios
import tty
import atexit
import threading
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple

from icli.config import CONFIG_DIR, DOWNLOAD_DIR
from icli.client import InstagramClient
from icli.media import get_inline_thumbnail, play_media, download_media

# ANSI Formatting
RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
ITALIC = "\033[3m"
UNDERLINE = "\033[4m"

RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
BLUE = "\033[34m"
MAGENTA = "\033[35m"
CYAN = "\033[36m"
WHITE = "\033[37m"

BG_MAGENTA = "\033[45m"
BG_BLUE = "\033[44m"
BG_DARK = "\033[48;5;236m"
BG_STATUS = "\033[48;5;238m"


class RawTerminal:
    """Context manager for terminal raw/cbreak mode."""
    def __init__(self):
        self.fd = sys.stdin.fileno()
        self.old_settings = None

    def __enter__(self):
        if sys.stdin.isatty():
            self.old_settings = termios.tcgetattr(self.fd)
            tty.setcbreak(self.fd)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.old_settings is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.old_settings)


def read_key(timeout: float = 0.1) -> Optional[str]:
    """Read single keypress or escape sequence with timeout."""
    if not sys.stdin.isatty():
        return None
    r, _, _ = select.select([sys.stdin], [], [], timeout)
    if not r:
        return None

    ch = sys.stdin.read(1)
    if ch == "\033":
        # Check if more characters follow
        r2, _, _ = select.select([sys.stdin], [], [], 0.05)
        if not r2:
            return "ESC"
        ch2 = sys.stdin.read(1)
        if ch2 == "[":
            ch3 = sys.stdin.read(1)
            if ch3 == "A":
                return "UP"
            elif ch3 == "B":
                return "DOWN"
            elif ch3 == "C":
                return "RIGHT"
            elif ch3 == "D":
                return "LEFT"
            elif ch3 == "5":
                sys.stdin.read(1)  # consume ~
                return "PAGE_UP"
            elif ch3 == "6":
                sys.stdin.read(1)  # consume ~
                return "PAGE_DOWN"
            elif ch3 in ("H", "1", "7"):
                if ch3 != "H":
                    sys.stdin.read(1)
                return "HOME"
            elif ch3 in ("F", "4", "8"):
                if ch3 != "F":
                    sys.stdin.read(1)
                return "END"
            else:
                return "ESC"
        elif ch2 == "O":
            ch3 = sys.stdin.read(1)
            if ch3 == "A": return "UP"
            elif ch3 == "B": return "DOWN"
            elif ch3 == "C": return "RIGHT"
            elif ch3 == "D": return "LEFT"
            return "ESC"
        return "ESC"
    elif ch in ("\r", "\n"):
        return "ENTER"
    elif ch in ("\x7f", "\x08"):
        return "BACKSPACE"
    elif ch == "\x04":
        return "CTRL_D"
    elif ch == "\x15":
        return "CTRL_U"
    elif ch == "\x03":
        return "CTRL_C"
    elif ch == "\t":
        return "TAB"
    return ch


class TerminalUI:
    def __init__(self, client: InstagramClient):
        self.client = client
        self.current_thread: Optional[Dict[str, Any]] = None
        self.threads: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, Any]] = []
        self.media_registry: List[Dict[str, Any]] = []
        self.rendered_lines: List[str] = []

        self.scroll_offset = 0  # 0 = at bottom (latest)
        self.vanish_mode_active = False
        self.mode = "INSERT"  # "INSERT" or "NORMAL"
        self.input_buffer = ""
        self.status_message = ""
        self.status_time = 0.0

        self.running = True
        self.redraw_needed = True
        self.poll_active = False

        # Register terminal cleanup
        atexit.register(self._restore_cursor)

    def _restore_cursor(self):
        sys.stdout.write("\033[?25h\033[0m")
        sys.stdout.flush()

    def run(self):
        """Main application lifecycle."""
        sys.stdout.write("\033[2J\033[H")
        sys.stdout.flush()
        self.show_banner()

        session_stat = self.client.check_session()
        if session_stat["status"] == "checkpoint":
            if not self.handle_checkpoint_dialog():
                print(f"\n{RED}Checkpoint pending. Please approve in your Instagram app or log in with Session ID.{RESET}")
                return
        elif session_stat["status"] != "active":
            if not self.interactive_auth_flow():
                print(f"\n{RED}Authentication required to proceed. Exiting.{RESET}")
                return

        self.inbox_loop()

    def handle_checkpoint_dialog(self) -> bool:
        """Guide the user through approving a native Instagram checkpoint challenge."""
        sys.stdout.write("\033[2J\033[H")
        print(f"{BOLD}{YELLOW}╔═══════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{YELLOW}║               ⚠️  INSTAGRAM CHECKPOINT DETECTED               ║{RESET}")
        print(f"{BOLD}{YELLOW}╚═══════════════════════════════════════════════════════════════╝{RESET}\n")
        print(f"{WHITE}Instagram detected an unrecognized client device and placed a security hold.{RESET}\n")
        print(f"{BOLD}How to approve this login:{RESET}")
        print(f"  1. Open the {BOLD}Instagram app{RESET} on your phone (or visit {CYAN}instagram.com{RESET}).")
        print(f"  2. You will see an alert: {YELLOW}'Was this you? (Google Pixel 8 Pro / Linux)'{RESET}.")
        print(f"  3. Tap {GREEN}{BOLD}'This Was Me'{RESET} to whitelist this device.")
        print(f"  4. Once confirmed, press {BOLD}[Enter]{RESET} here to resume chatting!\n")
        print(f"{DIM}── Or Bypass With Session ID ───────────────────────────────────────{RESET}")
        print(f"  Type {BOLD}:s{RESET} to log in using your {GREEN}Session ID Cookie{RESET} (bypasses checkpoint challenges).")
        print(f"  Type {BOLD}:q{RESET} to exit.\n")

        ans = input(f"{BOLD}Press Enter to retry or enter :s / :q: {RESET}").strip()
        if ans == ":q":
            return False
        elif ans == ":s":
            session_id = input(f"{BOLD}Enter sessionid cookie: {RESET}").strip()
            if session_id:
                print(f"\n{CYAN}Authenticating with session ID...{RESET}")
                res = self.client.login_by_sessionid(session_id)
                if res["success"]:
                    print(f"{GREEN}✓ {res['message']}{RESET}")
                    time.sleep(1)
                    return True
                else:
                    print(f"{RED}✗ {res['message']}{RESET}")
                    time.sleep(2)
            return False
        else:
            print(f"\n{CYAN}Re-verifying session...{RESET}")
            res = self.client.check_session()
            if res["status"] == "active":
                print(f"{GREEN}✓ Session confirmed as @{res.get('username')}!{RESET}")
                time.sleep(1)
                return True
            elif res["status"] == "checkpoint":
                print(f"{YELLOW}Checkpoint still pending. Please confirm 'This was me' on your phone or use Session ID.{RESET}")
                time.sleep(2)
                return self.interactive_auth_flow()
            else:
                return self.interactive_auth_flow()

    def show_banner(self):
        print(f"{BOLD}{CYAN}╔═══════════════════════════════════════════════════════════════╗{RESET}")
        print(f"{BOLD}{CYAN}║                     i-cli : Instagram CLI                     ║{RESET}")
        print(f"{BOLD}{CYAN}║       Vanish Mode • RAM-Only Media (imv/mpv) • Chafa TUI      ║{RESET}")
        print(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════════════════╝{RESET}\n")

    def interactive_auth_flow(self) -> bool:
        """Prompt user for isolated login (independent of Firefox)."""
        print(f"{YELLOW}No saved session found in {CONFIG_DIR}{RESET}")
        print("Choose login method:")
        print(f"  {BOLD}1{RESET}) Session ID Cookie ({GREEN}Recommended{RESET} - bypasses checkpoints)")
        print(f"  {BOLD}2{RESET}) Instagram Username & Password")
        print(f"  {BOLD}3{RESET}) Exit")

        choice = input(f"\n{BOLD}Select option [1/2/3]: {RESET}").strip()

        if choice == "1":
            print(f"\n{DIM}To get your sessionid: Log in on web browser, inspect cookies for instagram.com, copy 'sessionid'.{RESET}")
            session_id = input(f"{BOLD}Enter sessionid: {RESET}").strip()
            if not session_id:
                return False
            print(f"\n{CYAN}Authenticating...{RESET}")
            res = self.client.login_by_sessionid(session_id)
            if res["success"]:
                print(f"{GREEN}✓ {res['message']}{RESET}")
                time.sleep(1)
                return True
            else:
                print(f"{RED}✗ {res['message']}{RESET}")
                return False

        elif choice == "2":
            username = input(f"{BOLD}Instagram Username: {RESET}").strip()
            import getpass
            password = getpass.getpass(f"{BOLD}Instagram Password: {RESET}")
            print(f"\n{CYAN}Logging in...{RESET}")
            res = self.client.login_by_password(username, password)
            if res["success"]:
                print(f"{GREEN}✓ {res['message']}{RESET}")
                time.sleep(1)
                return True
            elif res.get("requires_2fa"):
                code = input(f"{BOLD}Enter 2FA Code: {RESET}").strip()
                res2 = self.client.login_by_password(username, password, verification_code=code)
                if res2["success"]:
                    print(f"{GREEN}✓ {res2['message']}{RESET}")
                    time.sleep(1)
                    return True
                else:
                    print(f"{RED}✗ {res2['message']}{RESET}")
                    return False
            else:
                print(f"{RED}✗ {res['message']}{RESET}")
                return False
        else:
            return False

    def inbox_loop(self):
        """Thread selection and inbox management."""
        selected_idx = 0

        while self.running:
            sys.stdout.write("\033[2J\033[H")
            self.show_banner()
            print(f"{DIM}Logged in as: {BOLD}{self.client.username or 'Unknown'}{RESET}\n")
            print(f"{CYAN}Fetching direct conversations...{RESET}")

            self.threads = self.client.get_threads(amount=20)
            if not self.threads:
                print(f"{YELLOW}No active conversations found.{RESET}")
                print(f"\n{DIM}Commands: {BOLD}:r{RESET} Refresh  |  {BOLD}:logout{RESET}  |  {BOLD}:q{RESET} Quit{RESET}")
                cmd = input(f"{BOLD}> {RESET}").strip()
                if cmd == ":q":
                    break
                elif cmd == ":logout":
                    self.client.logout()
                    return
                continue

            # Thread selection loop with vim/arrow keys
            in_selection = True
            with RawTerminal():
                while in_selection and self.running:
                    cols, rows = self.get_term_size()
                    frame = ["\033[H"]
                    frame.append(f"{BOLD}{CYAN}╔═══════════════════════════════════════════════════════════════╗{RESET}\033[K\n")
                    frame.append(f"{BOLD}{CYAN}║                     i-cli : INBOX                             ║{RESET}\033[K\n")
                    frame.append(f"{BOLD}{CYAN}╚═══════════════════════════════════════════════════════════════╝{RESET}\033[K\n")
                    frame.append(f" {DIM}User: {BOLD}{self.client.username or 'Me'}{RESET} | {DIM}j/k or Up/Down to navigate, Enter to open, :r to refresh, :q to quit{RESET}\033[K\n\n")

                    for idx, th in enumerate(self.threads):
                        is_sel = (idx == selected_idx)
                        cursor = f"{BOLD}{GREEN} ▸ {RESET}" if is_sel else "   "
                        vanish_badge = f"{MAGENTA}👻 [VANISH]{RESET} " if th.get("shh_mode_enabled") else ""
                        group_badge = f"{BLUE}[GROUP]{RESET} " if th.get("is_group") else ""
                        title = th.get("title", "Direct Message")
                        preview = th.get("last_message", "")
                        if len(preview) > 50:
                            preview = preview[:47] + "..."

                        th_color = f"{BOLD}{CYAN}" if is_sel else f"{WHITE}"
                        frame.append(f"{cursor}{BOLD}[{idx+1:2d}]{RESET} {group_badge}{vanish_badge}{th_color}{title}{RESET}\033[K\n")
                        frame.append(f"       {DIM}└─ {preview}{RESET}\033[K\n")

                    frame.append("\033[J")
                    sys.stdout.write("".join(frame))
                    sys.stdout.flush()

                    key = read_key(timeout=0.2)
                    if not key:
                        continue

                    if key in ("j", "DOWN"):
                        selected_idx = min(len(self.threads) - 1, selected_idx + 1)
                    elif key in ("k", "UP"):
                        selected_idx = max(0, selected_idx - 1)
                    elif key == "ENTER":
                        self.current_thread = self.threads[selected_idx]
                        in_selection = False
                        self.chat_loop()
                    elif key == "q":
                        self.running = False
                        return
                    elif key == "r":
                        in_selection = False
                    elif key.isdigit():
                        num = int(key)
                        if 1 <= num <= len(self.threads):
                            selected_idx = num - 1
                            self.current_thread = self.threads[selected_idx]
                            in_selection = False
                            self.chat_loop()

    def get_term_size(self) -> Tuple[int, int]:
        try:
            sz = os.get_terminal_size()
            return sz.columns, sz.lines
        except Exception:
            return 80, 24

    def format_timestamp(self, dt: Optional[datetime]) -> str:
        """Format timestamp with date and 12-hour AM/PM time."""
        if not dt:
            return ""
        return dt.strftime("%b %d, %I:%M %p")

    def rebuild_line_buffer(self):
        """Transform messages and thumbnails into rendered terminal lines."""
        lines = []
        media_items = []

        if not self.messages:
            lines.append(f"{DIM}No messages in this conversation yet. Send a message to begin!{RESET}")
        else:
            for msg in self.messages:
                is_me = msg.get("is_me", False)
                sender = "You" if is_me else (self.current_thread.get("title", "User"))
                sender_color = GREEN if is_me else CYAN
                time_str = self.format_timestamp(msg.get("timestamp"))

                is_vanish = msg.get("is_vanish", False)
                vanish_tag = f"{MAGENTA}👻 [VANISH]{RESET} " if is_vanish else ""
                pending_tag = f" {YELLOW}(sending...){RESET}" if msg.get("pending") else ""

                media_info = msg.get("media")
                if media_info:
                    m_type = media_info.get("type", "media")
                    m_label = media_info.get("label", m_type.capitalize())

                    if m_type == "call":
                        lines.append(f"{DIM}[{time_str}]{RESET} {YELLOW}{BOLD}📞 [{m_label}]{RESET}")
                        lines.append("")
                        continue

                    media_items.append(media_info)
                    media_idx = len(media_items)
                    lines.append(f"{DIM}[{time_str}]{RESET} {sender_color}{BOLD}{sender}{RESET}{pending_tag}: {vanish_tag}")
                    lines.append(f"   {YELLOW}{BOLD}[Media #{media_idx}: {m_label}]{RESET} {DIM}(Type :p {media_idx} to play in RAM, :d {media_idx} to save){RESET}")

                    thumb_url = media_info.get("thumbnail_url") or (media_info.get("url") if m_type == "image" else None)
                    if thumb_url:
                        rendered_thumb = get_inline_thumbnail(thumb_url, max_width=24, max_height=9)
                        if rendered_thumb:
                            for t_line in rendered_thumb.split("\n"):
                                lines.append(f"   {t_line}")

                    if msg.get("text"):
                        lines.append(f"   {msg['text']}")
                    lines.append("")  # Blank line spacer
                else:
                    text = msg.get("text", "")
                    lines.append(f"{DIM}[{time_str}]{RESET} {sender_color}{BOLD}{sender}{RESET}{pending_tag}: {vanish_tag}{text}")

        self.rendered_lines = lines
        self.media_registry = media_items

    def render_chat_screen(self):
        """Zero-flicker frame renderer using single syscall write."""
        cols, rows = self.get_term_size()
        frame = ["\033[H"]  # Home cursor to 1,1

        # Header (3 lines)
        title = self.current_thread.get("title", "Direct Message")
        vanish_badge = f" {BOLD}{MAGENTA}[👻 VANISH MODE ACTIVE]{RESET}" if self.vanish_mode_active else ""
        mode_badge = f"{BOLD}{GREEN}[INSERT]{RESET}" if self.mode == "INSERT" else f"{BOLD}{YELLOW}[NORMAL - VIM SCROLL]{RESET}"

        frame.append(f"{BOLD}{BLUE}═" * (cols - 1) + f"{RESET}\033[K\n")
        frame.append(f" {BOLD}Chat: {CYAN}@{title}{RESET}{vanish_badge}  {mode_badge}\033[K\n")
        frame.append(f"{BOLD}{BLUE}═" * (cols - 1) + f"{RESET}\033[K\n")

        # Chat viewport calculation
        header_height = 3
        footer_height = 3  # status line, separator, input prompt
        viewport_height = max(1, rows - header_height - footer_height)

        total_lines = len(self.rendered_lines)
        max_scroll = max(0, total_lines - viewport_height)
        self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

        start_idx = max(0, total_lines - viewport_height - self.scroll_offset)
        end_idx = min(total_lines, start_idx + viewport_height)
        visible = self.rendered_lines[start_idx:end_idx]

        for line in visible:
            frame.append(line + "\033[K\n")

        # Fill empty lines if lines < viewport_height
        for _ in range(viewport_height - len(visible)):
            frame.append("\033[K\n")

        # Status Bar
        v_state = f"{MAGENTA}ON{RESET}" if self.vanish_mode_active else f"{DIM}OFF{RESET}"
        media_count = len(self.media_registry)
        media_str = f"Latest Media: #{media_count}" if media_count > 0 else "No Media"

        scroll_indicator = ""
        if self.scroll_offset > 0:
            scroll_indicator = f" {YELLOW}{BOLD}[SCROLLED UP: -{self.scroll_offset} lines (Down/G: bottom)]{RESET}"

        status_notice = ""
        if self.status_message and (time.time() - self.status_time < 4.0):
            status_notice = f" {GREEN}{BOLD}• {self.status_message}{RESET}"

        frame.append(f"{DIM}─" * (cols - 1) + f"{RESET}\033[K\n")
        frame.append(f" [Vanish: {v_state}]  [{media_str}]{scroll_indicator}{status_notice}\033[K\n")

        # Input Prompt
        if self.mode == "INSERT":
            prompt = f"{MAGENTA}👻 [VANISH] > {RESET}" if self.vanish_mode_active else f"{CYAN}> {RESET}"
            frame.append(f"{prompt}{self.input_buffer}\033[K")
        else:
            frame.append(f"{YELLOW}NORMAL{RESET} (j/k: scroll, i: insert, :p: play, :d: save, :v: vanish, :t: inbox, :q: quit)\033[K")

        frame.append("\033[J")
        sys.stdout.write("".join(frame))
        sys.stdout.flush()

    def set_status(self, msg: str):
        self.status_message = msg
        self.status_time = time.time()
        self.render_chat_screen()

    def start_background_poller(self, thread_id: str):
        """Background thread polling for new incoming messages without UI lag."""
        def poll_worker():
            while self.poll_active and self.running:
                time.sleep(3.0)
                if not self.poll_active:
                    break
                try:
                    latest = self.client.get_thread_messages(thread_id, amount=30)
                    if latest:
                        # Check if changed
                        if len(latest) != len(self.messages) or (self.messages and latest[-1]["id"] != self.messages[-1]["id"]):
                            # Preserve pending outgoing messages
                            pending = [m for m in self.messages if m.get("pending")]
                            self.messages = latest + pending
                            self.rebuild_line_buffer()
                            # If pinned to bottom, refresh view
                            if self.scroll_offset == 0:
                                self.render_chat_screen()
                except Exception:
                    pass

        self.poll_active = True
        t = threading.Thread(target=poll_worker, daemon=True)
        t.start()

    def chat_loop(self):
        """Active chat view with instant real-time feel and Vim scrolling."""
        if not self.current_thread:
            return

        thread_id = self.current_thread["id"]
        self.vanish_mode_active = self.current_thread.get("shh_mode_enabled", False)
        self.mode = "INSERT"
        self.input_buffer = ""
        self.scroll_offset = 0

        # Initial fetch
        self.messages = self.client.get_thread_messages(thread_id, amount=30)
        self.rebuild_line_buffer()

        # Start background polling
        self.start_background_poller(thread_id)

        try:
            with RawTerminal():
                self.render_chat_screen()

                last_g_time = 0.0

                while self.running:
                    key = read_key(timeout=0.1)
                    if not key:
                        continue

                    # Handle global quit / interrupt
                    if key == "CTRL_C":
                        self.running = False
                        break

                    # INSERT MODE
                    if self.mode == "INSERT":
                        if key == "ESC":
                            self.mode = "NORMAL"
                            self.render_chat_screen()

                        elif key == "UP":
                            total = len(self.rendered_lines)
                            cols, rows = self.get_term_size()
                            max_s = max(0, total - (rows - 6))
                            self.scroll_offset = min(max_s, self.scroll_offset + 1)
                            self.render_chat_screen()

                        elif key == "DOWN":
                            self.scroll_offset = max(0, self.scroll_offset - 1)
                            self.render_chat_screen()

                        elif key in ("PAGE_UP", "PAGE_DOWN"):
                            cols, rows = self.get_term_size()
                            page_step = max(4, rows // 2)
                            total = len(self.rendered_lines)
                            max_s = max(0, total - (rows - 6))
                            if key == "PAGE_UP":
                                self.scroll_offset = min(max_s, self.scroll_offset + page_step)
                            else:
                                self.scroll_offset = max(0, self.scroll_offset - page_step)
                            self.render_chat_screen()

                        elif key == "BACKSPACE":
                            if self.input_buffer:
                                self.input_buffer = self.input_buffer[:-1]
                                self.render_chat_screen()

                        elif key == "CTRL_U":
                            self.input_buffer = ""
                            self.render_chat_screen()

                        elif key == "ENTER":
                            text = self.input_buffer.strip()
                            self.input_buffer = ""

                            if not text:
                                self.render_chat_screen()
                                continue

                            # Check for commands
                            if text.startswith(":"):
                                should_exit = self.handle_chat_command(text, thread_id)
                                if should_exit:
                                    break
                                self.render_chat_screen()
                                continue

                            # INSTANT REAL-TIME SEND
                            # 1. Immediately append to in-memory messages
                            local_id = f"local_{uuid.uuid4().hex[:6]}"
                            local_msg = {
                                "id": local_id,
                                "user_id": self.client.user_id,
                                "is_me": True,
                                "timestamp": datetime.now(),
                                "text": text,
                                "item_type": "text",
                                "is_vanish": self.vanish_mode_active,
                                "media": None,
                                "pending": True
                            }
                            self.messages.append(local_msg)
                            self.scroll_offset = 0  # Snap to bottom
                            self.rebuild_line_buffer()
                            self.render_chat_screen()  # 0ms screen update!

                            # 2. Dispatch network send in background thread
                            def async_sender(th_id, msg_text, is_v, l_msg):
                                res = self.client.send_message(th_id, msg_text, is_vanish=is_v)
                                l_msg["pending"] = False
                                if res and res.get("id"):
                                    l_msg["id"] = res["id"]
                                self.rebuild_line_buffer()
                                if self.scroll_offset == 0:
                                    self.render_chat_screen()

                            threading.Thread(
                                target=async_sender,
                                args=(thread_id, text, self.vanish_mode_active, local_msg),
                                daemon=True
                            ).start()

                        else:
                            # Regular character typed
                            if len(key) == 1 and key.isprintable():
                                self.input_buffer += key
                                self.render_chat_screen()

                    # NORMAL (VIM SCROLL) MODE
                    elif self.mode == "NORMAL":
                        if key in ("i", "a"):
                            self.mode = "INSERT"
                            self.render_chat_screen()

                        elif key in ("j", "DOWN"):
                            self.scroll_offset = max(0, self.scroll_offset - 1)
                            self.render_chat_screen()

                        elif key in ("k", "UP"):
                            total = len(self.rendered_lines)
                            cols, rows = self.get_term_size()
                            max_s = max(0, total - (rows - 6))
                            self.scroll_offset = min(max_s, self.scroll_offset + 1)
                            self.render_chat_screen()

                        elif key in ("CTRL_D", "PAGE_DOWN"):
                            cols, rows = self.get_term_size()
                            self.scroll_offset = max(0, self.scroll_offset - (rows // 2))
                            self.render_chat_screen()

                        elif key in ("CTRL_U", "PAGE_UP"):
                            cols, rows = self.get_term_size()
                            total = len(self.rendered_lines)
                            max_s = max(0, total - (rows - 6))
                            self.scroll_offset = min(max_s, self.scroll_offset + (rows // 2))
                            self.render_chat_screen()

                        elif key == "G":
                            # Jump to bottom (latest)
                            self.scroll_offset = 0
                            self.render_chat_screen()

                        elif key == "g":
                            # Double-g (gg) jumps to top
                            now = time.time()
                            if now - last_g_time < 0.6:
                                total = len(self.rendered_lines)
                                cols, rows = self.get_term_size()
                                self.scroll_offset = max(0, total - (rows - 6))
                                self.render_chat_screen()
                                last_g_time = 0.0
                            else:
                                last_g_time = now

                        elif key == ":":
                            # Enter command prompt
                            self.mode = "INSERT"
                            self.input_buffer = ":"
                            self.render_chat_screen()

                        elif key == "v":
                            self.vanish_mode_active = not self.vanish_mode_active
                            state_str = "ON" if self.vanish_mode_active else "OFF"
                            self.set_status(f"Vanish Mode turned {state_str}")

                        elif key == "r":
                            self.set_status("Refreshing...")
                            self.messages = self.client.get_thread_messages(thread_id, amount=30)
                            self.rebuild_line_buffer()
                            self.render_chat_screen()

                        elif key == "t":
                            # Return to inbox
                            break

                        elif key == "q":
                            self.running = False
                            break

        finally:
            self.poll_active = False

    def handle_chat_command(self, cmd: str, thread_id: str) -> bool:
        """
        Handle :-prefixed commands in chat.
        Returns True if chat loop should exit back to inbox.
        """
        if cmd == ":t":
            return True
        elif cmd == ":q":
            self.running = False
            return True
        elif cmd == ":r":
            self.set_status("Refreshing...")
            self.messages = self.client.get_thread_messages(thread_id, amount=30)
            self.rebuild_line_buffer()
            return False
        elif cmd in (":v", ":vanish"):
            self.vanish_mode_active = not self.vanish_mode_active
            state_str = "ON" if self.vanish_mode_active else "OFF"
            self.set_status(f"Vanish Mode toggled {state_str}")
            return False
        elif cmd.startswith(":v "):
            # Send single vanish message
            vanish_text = cmd[3:].strip()
            if vanish_text:
                local_msg = {
                    "id": f"local_{uuid.uuid4().hex[:6]}",
                    "user_id": self.client.user_id,
                    "is_me": True,
                    "timestamp": datetime.now(),
                    "text": vanish_text,
                    "item_type": "text",
                    "is_vanish": True,
                    "media": None,
                    "pending": True
                }
                self.messages.append(local_msg)
                self.scroll_offset = 0
                self.rebuild_line_buffer()
                self.render_chat_screen()

                def async_vanish(th_id, v_text, l_msg):
                    res = self.client.send_message(th_id, v_text, is_vanish=True)
                    l_msg["pending"] = False
                    if res and res.get("id"):
                        l_msg["id"] = res["id"]
                    self.rebuild_line_buffer()
                    if self.scroll_offset == 0:
                        self.render_chat_screen()

                threading.Thread(target=async_vanish, args=(thread_id, vanish_text, local_msg), daemon=True).start()
            return False
        elif cmd == ":p" or cmd.startswith(":p "):
            self.handle_preview_command(cmd)
            return False
        elif cmd == ":d" or cmd.startswith(":d "):
            self.handle_download_command(cmd)
            return False
        elif cmd.startswith(":photo ") or cmd.startswith(":send-photo "):
            path = cmd.split(maxsplit=1)[1].strip().strip('"').strip("'")
            self.handle_send_photo(thread_id, path)
            return False
        elif cmd.startswith(":video ") or cmd.startswith(":send-video "):
            path = cmd.split(maxsplit=1)[1].strip().strip('"').strip("'")
            self.handle_send_video(thread_id, path)
            return False
        elif cmd.startswith(":audio ") or cmd.startswith(":send-audio "):
            path = cmd.split(maxsplit=1)[1].strip().strip('"').strip("'")
            self.handle_send_audio(thread_id, path)
            return False
        elif cmd in (":rec", ":record"):
            self.handle_voice_recording(thread_id)
            return False
        elif cmd in (":h", ":help", ":?"):
            self.show_help_dialog()
            return False
        else:
            self.set_status(f"Unknown command: {cmd}")
            return False

    def handle_send_photo(self, thread_id: str, path: str):
        """Send photo to conversation."""
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        if not p.exists():
            self.set_status(f"Error: Photo not found: {path}")
            return

        self.set_status(f"Sending photo: {p.name}...")
        local_msg = {
            "id": f"local_{uuid.uuid4().hex[:6]}",
            "user_id": self.client.user_id,
            "is_me": True,
            "timestamp": datetime.now(),
            "text": f"[Photo: {p.name}]",
            "item_type": "media",
            "is_vanish": self.vanish_mode_active,
            "media": {"type": "image", "url": None, "thumbnail_url": str(p), "label": "Photo"},
            "pending": True
        }
        self.messages.append(local_msg)
        self.scroll_offset = 0
        self.rebuild_line_buffer()
        self.render_chat_screen()

        def async_photo():
            res = self.client.send_photo(thread_id, str(p), is_vanish=self.vanish_mode_active)
            local_msg["pending"] = False
            if res.get("success") and res.get("id"):
                local_msg["id"] = res["id"]
                self.set_status("Photo sent successfully.")
            else:
                self.set_status(res.get("message", "Failed to send photo."))
            self.rebuild_line_buffer()
            if self.scroll_offset == 0:
                self.render_chat_screen()

        threading.Thread(target=async_photo, daemon=True).start()

    def handle_send_video(self, thread_id: str, path: str):
        """Send video to conversation."""
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        if not p.exists():
            self.set_status(f"Error: Video not found: {path}")
            return

        self.set_status(f"Sending video: {p.name}...")
        local_msg = {
            "id": f"local_{uuid.uuid4().hex[:6]}",
            "user_id": self.client.user_id,
            "is_me": True,
            "timestamp": datetime.now(),
            "text": f"[Video: {p.name}]",
            "item_type": "media",
            "is_vanish": self.vanish_mode_active,
            "media": {"type": "video", "url": None, "label": "Video"},
            "pending": True
        }
        self.messages.append(local_msg)
        self.scroll_offset = 0
        self.rebuild_line_buffer()
        self.render_chat_screen()

        def async_video():
            res = self.client.send_video(thread_id, str(p), is_vanish=self.vanish_mode_active)
            local_msg["pending"] = False
            if res.get("success") and res.get("id"):
                local_msg["id"] = res["id"]
                self.set_status("Video sent successfully.")
            else:
                self.set_status(res.get("message", "Failed to send video."))
            self.rebuild_line_buffer()
            if self.scroll_offset == 0:
                self.render_chat_screen()

        threading.Thread(target=async_video, daemon=True).start()

    def handle_send_audio(self, thread_id: str, path: str):
        """Send audio file as voice note."""
        from pathlib import Path
        p = Path(path).expanduser().resolve()
        if not p.exists():
            self.set_status(f"Error: Audio not found: {path}")
            return

        self.set_status(f"Sending voice note: {p.name}...")
        local_msg = {
            "id": f"local_{uuid.uuid4().hex[:6]}",
            "user_id": self.client.user_id,
            "is_me": True,
            "timestamp": datetime.now(),
            "text": f"[Voice Note: {p.name}]",
            "item_type": "voice_media",
            "is_vanish": self.vanish_mode_active,
            "media": {"type": "audio", "url": None, "label": "Voice Note"},
            "pending": True
        }
        self.messages.append(local_msg)
        self.scroll_offset = 0
        self.rebuild_line_buffer()
        self.render_chat_screen()

        def async_audio():
            res = self.client.send_voice(thread_id, str(p), is_vanish=self.vanish_mode_active)
            local_msg["pending"] = False
            if res.get("success") and res.get("id"):
                local_msg["id"] = res["id"]
                self.set_status("Voice note sent successfully.")
            else:
                self.set_status(res.get("message", "Failed to send audio."))
            self.rebuild_line_buffer()
            if self.scroll_offset == 0:
                self.render_chat_screen()

        threading.Thread(target=async_audio, daemon=True).start()

    def handle_voice_recording(self, thread_id: str):
        """Record audio directly from microphone in RAM and send."""
        from icli.media import record_voice_start, record_voice_stop

        proc, out_path = record_voice_start()
        if not proc or not out_path:
            self.set_status("Error: Could not access microphone with ffmpeg.")
            return

        start_time = time.time()
        cancelled = False

        while proc.poll() is None:
            elapsed = int(time.time() - start_time)
            self.set_status(f"🎙️  RECORDING VOICE NOTE ({elapsed}s)... [Enter: Send | Esc/c: Cancel]")
            k = read_key(timeout=0.4)
            if k in ("ENTER", "\r", "\n"):
                break
            elif k in ("ESC", "c", "C", "CTRL_C"):
                cancelled = True
                break

        record_voice_stop(proc, out_path)

        if cancelled:
            if out_path.exists():
                try:
                    out_path.unlink()
                except Exception:
                    pass
            self.set_status("Voice recording cancelled.")
            return

        if not out_path.exists() or out_path.stat().st_size < 100:
            self.set_status("Error: No audio captured.")
            return

        self.set_status("Sending recorded voice note...")
        local_msg = {
            "id": f"local_{uuid.uuid4().hex[:6]}",
            "user_id": self.client.user_id,
            "is_me": True,
            "timestamp": datetime.now(),
            "text": "[Voice Note]",
            "item_type": "voice_media",
            "is_vanish": self.vanish_mode_active,
            "media": {"type": "audio", "url": None, "label": "Voice Note"},
            "pending": True
        }
        self.messages.append(local_msg)
        self.scroll_offset = 0
        self.rebuild_line_buffer()
        self.render_chat_screen()

        def async_rec_voice():
            res = self.client.send_voice(thread_id, str(out_path), is_vanish=self.vanish_mode_active)
            local_msg["pending"] = False
            if res.get("success") and res.get("id"):
                local_msg["id"] = res["id"]
                self.set_status("Voice note sent successfully.")
            else:
                self.set_status(res.get("message", "Failed to send voice note."))
            self.rebuild_line_buffer()
            if self.scroll_offset == 0:
                self.render_chat_screen()

        threading.Thread(target=async_rec_voice, daemon=True).start()

    def handle_preview_command(self, cmd: str):
        """Preview media with imv/mpv purely in RAM."""
        if not self.media_registry:
            self.set_status("No media items in conversation.")
            return

        parts = cmd.split()
        target_idx = len(self.media_registry)
        if len(parts) > 1 and parts[1].isdigit():
            target_idx = int(parts[1])

        if not (1 <= target_idx <= len(self.media_registry)):
            self.set_status(f"Invalid media index (1-{len(self.media_registry)})")
            return

        media_item = self.media_registry[target_idx - 1]
        self.set_status(f"Streaming media #{target_idx} in RAM...")
        res = play_media(media_item)
        self.set_status(res)

    def handle_download_command(self, cmd: str):
        """Download media explicitly to ~/Downloads/."""
        if not self.media_registry:
            self.set_status("No media items to download.")
            return

        parts = cmd.split()
        target_idx = len(self.media_registry)
        if len(parts) > 1 and parts[1].isdigit():
            target_idx = int(parts[1])

        if not (1 <= target_idx <= len(self.media_registry)):
            self.set_status(f"Invalid media index (1-{len(self.media_registry)})")
            return

        media_item = self.media_registry[target_idx - 1]
        self.set_status(f"Downloading media #{target_idx}...")
        res = download_media(media_item, DOWNLOAD_DIR)
        self.set_status(res)

    def show_help_dialog(self):
        """Show command help modal."""
        sys.stdout.write("\033[2J\033[H")
        print(f"{BOLD}{CYAN}=== i-cli Commands & Navigation Help ==={RESET}\n")
        print(f"  {BOLD}INSERT Mode (Typing){RESET}:")
        print(f"    {BOLD}Up{RESET} / {BOLD}Down{RESET}       Scroll through message history directly while typing")
        print(f"    {BOLD}PgUp{RESET} / {BOLD}PgDn{RESET}     Scroll page-by-page through message history")
        print(f"    {BOLD}Esc{RESET}            Enter NORMAL mode for Vim navigation\n")
        print(f"  {BOLD}NORMAL Mode (Vim Navigation){RESET}:")
        print(f"    {BOLD}j{RESET} / {BOLD}Down{RESET}       Scroll down 1 line")
        print(f"    {BOLD}k{RESET} / {BOLD}Up{RESET}         Scroll up 1 line")
        print(f"    {BOLD}Ctrl+d{RESET} / {BOLD}PgDn{RESET} Scroll down half page")
        print(f"    {BOLD}Ctrl+u{RESET} / {BOLD}PgUp{RESET} Scroll up half page")
        print(f"    {BOLD}gg{RESET}             Jump to oldest message (top)")
        print(f"    {BOLD}G{RESET}              Jump to latest message (bottom)")
        print(f"    {BOLD}i{RESET} / {BOLD}a{RESET}          Enter INSERT mode to type\n")
        print(f"  {BOLD}Media Viewing & Downloading{RESET}:")
        print(f"    {BOLD}:p [n]{RESET}         Play media in RAM ({BOLD}imv{RESET} for images, {BOLD}mpv{RESET} for video/audio)")
        print(f"    {BOLD}:d [n]{RESET}         Download media to {BOLD}~/Downloads/{RESET}\n")
        print(f"  {BOLD}Sending Media & Voice Notes{RESET}:")
        print(f"    {BOLD}:rec{RESET}           Record audio voice note from microphone and send")
        print(f"    {BOLD}:photo <path>{RESET}  Send a photo file")
        print(f"    {BOLD}:video <path>{RESET}  Send a video file (.mp4)")
        print(f"    {BOLD}:audio <path>{RESET}  Send an audio file as a voice note\n")
        print(f"  {BOLD}Actions & Controls{RESET}:")
        print(f"    {BOLD}:v{RESET}             Toggle Vanish Mode on/off")
        print(f"    {BOLD}:v <text>{RESET}      Send single message in Vanish Mode")
        print(f"    {BOLD}:t{RESET}             Return to Inbox list")
        print(f"    {BOLD}:r{RESET}             Force refresh messages")
        print(f"    {BOLD}:q{RESET}             Quit i-cli\n")
        print(f"{DIM}Press any key to return to chat...{RESET}")
        with RawTerminal():
            read_key(timeout=30.0)
        self.render_chat_screen()
