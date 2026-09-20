#!/usr/bin/env python3
import sys
import argparse
from icli.client import InstagramClient
from icli.ui import TerminalUI
from icli.config import CONFIG_DIR, SESSION_FILE


def main():
    parser = argparse.ArgumentParser(
        description="i-cli: Minimal Instagram CLI/TUI with Vanish Mode and RAM-Only Media."
    )
    parser.add_argument("--login", action="store_true", help="Interactively log in and save session")
    parser.add_argument("--session", type=str, help="Authenticate directly with an Instagram sessionid cookie")
    parser.add_argument("--logout", action="store_true", help="Remove saved session credentials and logout")
    args = parser.parse_args()

    client = InstagramClient()

    if args.logout:
        if client.logout():
            print("Successfully logged out and removed session from ~/.config/i-cli/session.json")
        else:
            print("No active session to remove.")
        return

    if args.session:
        print("Authenticating with provided session ID...")
        res = client.login_by_sessionid(args.session)
        if res["success"]:
            print(f"Success: {res['message']}")
        else:
            print(f"Error: {res['message']}")
            sys.exit(1)
        return

    if args.login:
        ui = TerminalUI(client)
        if ui.interactive_auth_flow():
            print("Login complete. Run `i-cli` to start chatting.")
        else:
            print("Login cancelled or failed.")
        return

    # Default: launch interactive terminal UI
    ui = TerminalUI(client)
    ui.run()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nExiting i-cli.")
        sys.exit(0)
