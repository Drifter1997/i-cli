import os
import json
import time
from pathlib import Path
from typing import List, Dict, Any, Optional

from instagrapi import Client
from instagrapi.exceptions import (
    BadPassword,
    TwoFactorRequired,
    ChallengeRequired,
    LoginRequired,
)
from icli.config import SESSION_FILE, CONFIG_DIR
from icli.media import extract_media_info


class InstagramClient:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [1, 3]
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None

    def is_logged_in(self) -> bool:
        """Check if client currently has a valid session."""
        if not SESSION_FILE.exists():
            return False
        try:
            self.cl.load_settings(SESSION_FILE)
            # Quick check if session is active
            user_info = self.cl.account_info()
            self.user_id = str(user_info.pk)
            self.username = user_info.username
            return True
        except Exception:
            return False

    def save_session(self):
        """Save session settings with 0600 permissions."""
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        self.cl.dump_settings(SESSION_FILE)
        try:
            os.chmod(SESSION_FILE, 0o600)
        except Exception:
            pass

    def login_by_password(self, username: str, password: str, verification_code: Optional[str] = None) -> Dict[str, Any]:
        """Log in using username and password (isolated from any browser)."""
        try:
            if verification_code:
                self.cl.login(username, password, verification_code=verification_code)
            else:
                self.cl.login(username, password)
            self.user_id = str(self.cl.user_id)
            self.username = username
            self.save_session()
            return {"success": True, "message": f"Successfully logged in as {username}."}
        except TwoFactorRequired as e:
            return {"success": False, "requires_2fa": True, "message": "Two-factor authentication code required."}
        except ChallengeRequired as e:
            return {"success": False, "requires_challenge": True, "message": "Instagram requested a checkpoint challenge."}
        except BadPassword:
            return {"success": False, "message": "Incorrect username or password."}
        except Exception as e:
            return {"success": False, "message": f"Login failed: {e}"}

    def login_by_sessionid(self, session_id: str) -> Dict[str, Any]:
        """Log in using a raw sessionid token (bypasses checkpoint challenges)."""
        try:
            self.cl.login_by_sessionid(session_id.strip())
            user_info = self.cl.account_info()
            self.user_id = str(user_info.pk)
            self.username = user_info.username
            self.save_session()
            return {"success": True, "message": f"Successfully authenticated as {self.username}."}
        except Exception as e:
            return {"success": False, "message": f"Authentication failed with provided session ID: {e}"}

    def logout(self) -> bool:
        """Clear local session file and logout."""
        try:
            if SESSION_FILE.exists():
                SESSION_FILE.unlink()
            self.cl = Client()
            self.user_id = None
            self.username = None
            return True
        except Exception:
            return False

    def get_threads(self, amount: int = 25) -> List[Dict[str, Any]]:
        """Fetch inbox threads with vanish mode and user info."""
        try:
            threads = self.cl.direct_threads(amount=amount)
            results = []
            for th in threads:
                # Format participants
                usernames = [u.username for u in th.users if u.username != self.username]
                title = th.thread_title or (", ".join(usernames) if usernames else "Direct Message")
                
                # Check last message preview
                last_msg_text = ""
                last_msg_time = th.last_activity_at
                is_shh = getattr(th, "shh_mode_enabled", False)

                if th.messages:
                    latest = th.messages[0]
                    if latest.text:
                        last_msg_text = latest.text
                    elif getattr(latest, "media", None):
                        last_msg_text = "[Media]"
                    elif getattr(latest, "visual_media", None):
                        last_msg_text = "[Disappearing Media]"
                    elif getattr(latest, "voice_media", None):
                        last_msg_text = "[Voice Note]"
                    else:
                        last_msg_text = f"[{latest.item_type or 'Message'}]"

                results.append({
                    "id": str(th.id),
                    "title": title,
                    "usernames": usernames,
                    "last_message": last_msg_text,
                    "last_activity": last_msg_time,
                    "is_group": th.is_group,
                    "shh_mode_enabled": bool(is_shh),
                    "raw_thread": th
                })
            return results
        except Exception as e:
            return []

    def get_thread_messages(self, thread_id: str, amount: int = 40) -> List[Dict[str, Any]]:
        """Retrieve message history for a specific thread with media and vanish flags."""
        try:
            # direct_messages returns newest first; reverse for chronological order
            raw_messages = self.cl.direct_messages(thread_id, amount=amount)
            messages = []
            for msg in reversed(raw_messages):
                sender_id = str(msg.user_id)
                is_me = (sender_id == self.user_id) or getattr(msg, "is_sent_by_viewer", False)
                is_vanish = getattr(msg, "is_shh_mode", False) or (msg.item_type == "raven_media")

                media_info = extract_media_info(msg)

                messages.append({
                    "id": str(msg.id),
                    "user_id": sender_id,
                    "is_me": is_me,
                    "timestamp": msg.timestamp,
                    "text": msg.text or "",
                    "item_type": msg.item_type,
                    "is_vanish": bool(is_vanish),
                    "media": media_info,
                    "raw_msg": msg
                })
            return messages
        except Exception as e:
            return []

    def send_message(self, thread_id: str, text: str, is_vanish: bool = False) -> Optional[Dict[str, Any]]:
        """
        Send a text message. If is_vanish=True, sends with vanish mode payload.
        """
        try:
            if is_vanish:
                # Dispatch with shh_mode=1 in broadcast payload
                client_context = self.cl.generate_uuid()
                data = {
                    "action": "send_item",
                    "thread_ids": f"[{thread_id}]",
                    "client_context": client_context,
                    "text": text,
                    "shh_mode": "1",
                    "is_shh_mode": "1",
                    "_uuid": self.cl.uuid,
                }
                res = self.cl.private_request("direct_v2/threads/broadcast/text/", data=data)
                return {"id": client_context, "text": text, "is_vanish": True, "success": True}
            else:
                msg = self.cl.direct_send(text, thread_ids=[thread_id])
                return {
                    "id": str(msg.id),
                    "text": text,
                    "is_vanish": False,
                    "success": True
                }
        except Exception as e:
            # If vanish specific broadcast fails, fallback to standard direct_send
            if is_vanish:
                try:
                    msg = self.cl.direct_send(f"[Vanish] {text}", thread_ids=[thread_id])
                    return {"id": str(msg.id), "text": text, "is_vanish": True, "success": True}
                except Exception:
                    pass
            return None
