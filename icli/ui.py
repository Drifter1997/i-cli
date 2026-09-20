import os
import sys
import time
import readline
import threading
from typing import Optional, List, Dict, Any

from icli.config import CONFIG_DIR, DOWNLOAD_DIR
from icli.client import InstagramClient
from icli.media import get_inline_thumbnail, play_media, download_media

# ANSI Color codes for clean, minimal UI
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


def clear_screen():
    os.system("clear" if os.name != "nt" else "cls")


class TerminalUI:
    def __init__(self, client: InstagramClient):
        self.client = client
        self.current_thread: Optional[Dict[str, Any]] = None
        self.threads: List[Dict[str, Any]] = []
        self.messages: List[Dict[str, Any]] = []
        self.media_registry: List[Dict[str, Any]] = []
        self.vanish_mode_active = False
        self.running = True

    def run(self):
        """Main application lifecycle."""
        clear_screen()
        self.show_banner()

        # Check authentication
        if not self.client.is_logged_in():
            if not self.interactive_auth_flow():
                print(f"\n{RED}Authentication required to proceed. Exiting.{RESET}")
                return

        # Enter inbox loop
        self.inbox_loop()

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
        while self.running:
            clear_screen()
            self.show_banner()
            print(f"{DIM}Logged in as: {BOLD}{self.client.username or 'Unknown'}{RESET}\n")
            print(f"{CYAN}Fetching direct conversations...{RESET}")

            self.threads = self.client.get_threads(amount=20)
            clear_screen()
            self.show_banner()
            print(f"{DIM}Logged in as: {BOLD}{self.client.username or 'Unknown'}{RESET}")
            print(f"{BOLD}Conversations:{RESET}\n")

            if not self.threads:
                print(f"{YELLOW}No active conversations found.{RESET}")
            else:
                for idx, th in enumerate(self.threads, start=1):
                    vanish_badge = f"{MAGENTA}👻 [VANISH]{RESET} " if th.get("shh_mode_enabled") else ""
                    group_badge = f"{BLUE}[GROUP]{RESET} " if th.get("is_group") else ""
                    title = th.get("title", "Direct Message")
                    preview = th.get("last_message", "")
                    if len(preview) > 55:
                        preview = preview[:52] + "..."

                    print(f"  {BOLD}[{idx:2d}]{RESET} {group_badge}{vanish_badge}{BOLD}{title}{RESET}")
                    print(f"       {DIM}└─ {preview}{RESET}")

            print(f"\n{DIM}Commands: {BOLD}[1-{len(self.threads)}]{RESET} Open chat  |  {BOLD}:r{RESET} Refresh  |  {BOLD}:logout{RESET}  |  {BOLD}:q{RESET} Quit{RESET}")

            try:
                cmd = input(f"\n{BOLD}> {RESET}").strip()
            except (KeyboardInterrupt, EOFError):
                self.running = False
                break

            if cmd == ":q":
                self.running = False
                break
            elif cmd == ":r":
                continue
            elif cmd == ":logout":
                self.client.logout()
                print(f"{YELLOW}Session cleared.{RESET}")
                return
            elif cmd.isdigit():
                val = int(cmd)
                if 1 <= val <= len(self.threads):
                    self.current_thread = self.threads[val - 1]
                    self.chat_loop()
                else:
                    print(f"{RED}Invalid thread number.{RESET}")
                    time.sleep(1)

    def chat_loop(self):
        """Active chat conversation view."""
        if not self.current_thread:
            return

        thread_id = self.current_thread["id"]
        # Sync initial vanish state with thread
        self.vanish_mode_active = self.current_thread.get("shh_mode_enabled", False)

        while self.running:
            clear_screen()
            self.render_chat_header()
            self.load_and_render_messages(thread_id)
            self.render_chat_status()

            try:
                prompt_label = f"{MAGENTA}👻 [VANISH] > {RESET}" if self.vanish_mode_active else f"{CYAN}> {RESET}"
                cmd = input(prompt_label).strip()
            except (KeyboardInterrupt, EOFError):
                break

            if not cmd:
                continue

            # Command parsing
            if cmd == ":t":
                # Return to thread list
                break
            elif cmd == ":q":
                self.running = False
                break
            elif cmd == ":r":
                continue
            elif cmd in (":v", ":vanish"):
                self.vanish_mode_active = not self.vanish_mode_active
                status_str = "ENABLED" if self.vanish_mode_active else "DISABLED"
                print(f"{MAGENTA}Vanish Mode {status_str} for outgoing messages.{RESET}")
                time.sleep(0.7)
                continue
            elif cmd.startswith(":v "):
                # Send single vanish message
                vanish_text = cmd[3:].strip()
                if vanish_text:
                    self.client.send_message(thread_id, vanish_text, is_vanish=True)
                continue
            elif cmd == ":p" or cmd.startswith(":p "):
                # Preview / play media in RAM
                self.handle_preview_command(cmd)
                continue
            elif cmd == ":d" or cmd.startswith(":d "):
                # Explicit download media to ~/Downloads
                self.handle_download_command(cmd)
                continue
            elif cmd in (":h", ":help", ":?"):
                self.show_help_dialog()
                continue
            elif cmd.startswith(":"):
                print(f"{RED}Unknown command: {cmd}. Type :h for help.{RESET}")
                time.sleep(1)
                continue
            else:
                # Regular text message
                self.client.send_message(thread_id, cmd, is_vanish=self.vanish_mode_active)

    def render_chat_header(self):
        title = self.current_thread.get("title", "Direct Message")
        vanish_banner = f"  {BOLD}{MAGENTA}[👻 VANISH MODE ACTIVE]{RESET}" if self.vanish_mode_active else ""
        print(f"{BOLD}{BLUE}========================================================================{RESET}")
        print(f" {BOLD}Chat: {CYAN}@{title}{RESET}{vanish_banner}")
        print(f" {DIM}Commands: :p (play in RAM) | :d (download) | :v (vanish) | :t (inbox) | :h (help){RESET}")
        print(f"{BOLD}{BLUE}========================================================================{RESET}\n")

    def load_and_render_messages(self, thread_id: str):
        """Fetch and render messages with inline chafa thumbnails."""
        self.messages = self.client.get_thread_messages(thread_id, amount=30)
        self.media_registry = []

        if not self.messages:
            print(f"{DIM}No messages in this conversation yet.{RESET}\n")
            return

        for msg in self.messages:
            is_me = msg.get("is_me", False)
            sender = "You" if is_me else (self.current_thread.get("title", "User"))
            sender_color = GREEN if is_me else CYAN
            timestamp = msg.get("timestamp")
            time_str = timestamp.strftime("%H:%M") if timestamp else ""

            is_vanish = msg.get("is_vanish", False)
            vanish_tag = f"{MAGENTA}👻 [VANISH]{RESET} " if is_vanish else ""

            # Check for media content
            media_info = msg.get("media")
            if media_info:
                self.media_registry.append(media_info)
                media_idx = len(self.media_registry)
                m_type = media_info.get("type", "media")
                m_label = media_info.get("label", m_type.capitalize())

                print(f"{DIM}[{time_str}]{RESET} {sender_color}{BOLD}{sender}{RESET}: {vanish_tag}")
                print(f"   {YELLOW}{BOLD}[Media #{media_idx}: {m_label}]{RESET} {DIM}(Type :p {media_idx} to play in RAM, :d {media_idx} to save){RESET}")

                # Display inline thumbnail via chafa if image/video
                thumb_url = media_info.get("thumbnail_url") or (media_info.get("url") if m_type == "image" else None)
                if thumb_url:
                    rendered_thumb = get_inline_thumbnail(thumb_url, max_width=26, max_height=10)
                    if rendered_thumb:
                        # Indent thumbnail lines
                        for line in rendered_thumb.split("\n"):
                            print(f"   {line}")

                if msg.get("text"):
                    print(f"   {msg['text']}")
                print()
            else:
                # Text message
                text = msg.get("text", "")
                print(f"{DIM}[{time_str}]{RESET} {sender_color}{BOLD}{sender}{RESET}: {vanish_tag}{text}")

        print()

    def render_chat_status(self):
        latest_media_str = f"Latest Media: #{len(self.media_registry)}" if self.media_registry else "No Media"
        v_state = f"{MAGENTA}ON{RESET}" if self.vanish_mode_active else f"{DIM}OFF{RESET}"
        print(f"{DIM}────────────────────────────────────────────────────────────────────────{RESET}")
        print(f" [Vanish: {v_state}]  [{latest_media_str}]  [:p=Preview in RAM :d=Download :r=Refresh]")

    def handle_preview_command(self, cmd: str):
        """Preview media with imv/mpv purely in RAM."""
        if not self.media_registry:
            print(f"\n{YELLOW}No media in current chat history.{RESET}")
            time.sleep(1)
            return

        parts = cmd.split()
        target_idx = len(self.media_registry)  # default: most recent
        if len(parts) > 1 and parts[1].isdigit():
            target_idx = int(parts[1])

        if not (1 <= target_idx <= len(self.media_registry)):
            print(f"\n{RED}Invalid media index. Choose 1 to {len(self.media_registry)}.{RESET}")
            time.sleep(1)
            return

        media_item = self.media_registry[target_idx - 1]
        print(f"\n{CYAN}Streaming media #{target_idx} in RAM...{RESET}")
        res = play_media(media_item)
        print(f"{GREEN}{res}{RESET}")
        time.sleep(1)

    def handle_download_command(self, cmd: str):
        """Download media to ~/Downloads only on explicit request."""
        if not self.media_registry:
            print(f"\n{YELLOW}No media to download.{RESET}")
            time.sleep(1)
            return

        parts = cmd.split()
        target_idx = len(self.media_registry)
        if len(parts) > 1 and parts[1].isdigit():
            target_idx = int(parts[1])

        if not (1 <= target_idx <= len(self.media_registry)):
            print(f"\n{RED}Invalid media index. Choose 1 to {len(self.media_registry)}.{RESET}")
            time.sleep(1)
            return

        media_item = self.media_registry[target_idx - 1]
        print(f"\n{CYAN}Downloading media #{target_idx} to {DOWNLOAD_DIR}...{RESET}")
        res = download_media(media_item, DOWNLOAD_DIR)
        print(f"{GREEN}{res}{RESET}")
        time.sleep(1.5)

    def show_help_dialog(self):
        clear_screen()
        print(f"{BOLD}{CYAN}=== i-cli Commands & Help ==={RESET}\n")
        print(f"  {BOLD}:p [n]{RESET}       Play / preview media #{BOLD}n{RESET} (or latest if omitted).")
        print(f"               • {BOLD}Photo{RESET}: Opened in {BOLD}imv{RESET} via /dev/shm (Linux RAM tmpfs).")
        print(f"               • {BOLD}Video{RESET}: Streamed directly via {BOLD}mpv{RESET} in RAM.")
        print(f"               • {BOLD}Voice Note{RESET}: Audio played directly via {BOLD}mpv{RESET} in RAM.")
        print(f"               {GREEN}* Guaranteed 100% in RAM - zero drive clutter.{RESET}\n")
        print(f"  {BOLD}:d [n]{RESET}       Explicitly download media #{BOLD}n{RESET} to {BOLD}~/Downloads/{RESET}.")
        print(f"  {BOLD}:v{RESET}           Toggle {MAGENTA}Vanish Mode{RESET} on/off for subsequent messages.")
        print(f"  {BOLD}:v <text>{RESET}    Send a single message in {MAGENTA}Vanish Mode{RESET}.")
        print(f"  {BOLD}:t{RESET}           Return to Inbox / Thread List.")
        print(f"  {BOLD}:r{RESET}           Refresh conversation messages.")
        print(f"  {BOLD}:q{RESET}           Quit application.")
        print(f"\n{DIM}Press Enter to return to chat...{RESET}")
        input()
