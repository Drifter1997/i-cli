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
from icli.config import SESSION_FILE, DEVICE_FILE, CONFIG_DIR
from icli.media import extract_media_info


class InstagramClient:
    def __init__(self):
        self.cl = Client()
        self.cl.delay_range = [1, 3]
        self.user_id: Optional[str] = None
        self.username: Optional[str] = None
        self._init_stable_device()

    def _init_stable_device(self):
        """
        Maintain persistent device fingerprint across all app runs.
        Prevents Instagram from detecting a 'new device' on every startup,
        which is the #1 cause of checkpoint challenges.
        """
        try:
            CONFIG_DIR.mkdir(parents=True, exist_ok=True)
            if DEVICE_FILE.exists():
                data = json.loads(DEVICE_FILE.read_text())
                self.cl.set_settings(data)
            else:
                st = self.cl.get_settings()
                device_data = {
                    "uuids": st.get("uuids", {}),
                    "device_settings": st.get("device_settings", {}),
                    "user_agent": st.get("user_agent", "")
                }
                self.cl.set_settings(device_data)
                DEVICE_FILE.write_text(json.dumps(device_data, indent=2))
                os.chmod(DEVICE_FILE, 0o600)
        except Exception:
            pass

    def check_session(self) -> Dict[str, Any]:
        """
        Check session status with precise classification:
        'active', 'no_session', 'checkpoint', 'expired', or 'error'
        """
        if not SESSION_FILE.exists():
            return {"status": "no_session"}

        try:
            self.cl.load_settings(SESSION_FILE)
            user_info = self.cl.account_info()
            self.user_id = str(user_info.pk)
            self.username = user_info.username
            return {"status": "active", "username": self.username}
        except ChallengeRequired as e:
            return {"status": "checkpoint", "error": str(e)}
        except LoginRequired:
            return {"status": "expired"}
        except Exception as e:
            err_str = str(e).lower()
            if "checkpoint" in err_str or "challenge" in err_str:
                return {"status": "checkpoint", "error": str(e)}
            return {"status": "error", "error": str(e)}

    def is_logged_in(self) -> bool:
        """Simple boolean check for active session."""
        res = self.check_session()
        return res["status"] == "active"

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
        except TwoFactorRequired:
            return {"success": False, "requires_2fa": True, "message": "Two-factor authentication code required."}
        except ChallengeRequired as e:
            return {
                "success": False,
                "requires_challenge": True,
                "message": (
                    "Instagram requested a checkpoint challenge.\n"
                    "Please open Instagram on your phone/browser and tap 'This was me', "
                    "or log in via option 1 (Session ID Cookie)."
                )
            }
        except BadPassword:
            return {"success": False, "message": "Incorrect username or password."}
        except Exception as e:
            return {"success": False, "message": f"Login failed: {e}"}

    def login_by_sessionid(self, session_id: str) -> Dict[str, Any]:
        """
        Log in using a raw sessionid token.
        Bypasses native checkpoint challenges because it inherits a verified session.
        """
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
                usernames = [u.username for u in th.users if u.username != self.username]
                title = th.thread_title or (", ".join(usernames) if usernames else "Direct Message")

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
        except Exception:
            return []

    def get_thread_messages(self, thread_id: str, amount: int = 40) -> List[Dict[str, Any]]:
        """Retrieve message history for a specific thread with media and vanish flags."""
        try:
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
        except Exception:
            return []

    def send_message(self, thread_id: str, text: str, is_vanish: bool = False) -> Optional[Dict[str, Any]]:
        """Send a text message (standard or Vanish Mode)."""
        try:
            if is_vanish:
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
                self.cl.private_request("direct_v2/threads/broadcast/text/", data=data)
                return {"id": client_context, "text": text, "is_vanish": True, "success": True}
            else:
                msg = self.cl.direct_send(text, thread_ids=[thread_id])
                return {"id": str(msg.id), "text": text, "is_vanish": False, "success": True}
        except Exception:
            if is_vanish:
                try:
                    msg = self.cl.direct_send(f"[Vanish] {text}", thread_ids=[thread_id])
                    return {"id": str(msg.id), "text": text, "is_vanish": True, "success": True}
                except Exception:
                    pass
            return None

    def send_photo(self, thread_id: str, photo_path: str, is_vanish: bool = False) -> Dict[str, Any]:
        """Send a photo (JPG/PNG/WebP) to the thread."""
        try:
            p = Path(photo_path).expanduser().resolve()
            if not p.exists():
                return {"success": False, "message": f"File not found: {photo_path}"}
            msg = self.cl.direct_send_photo(p, thread_ids=[int(thread_id)])
            return {"success": True, "id": str(msg.id), "message": "Photo sent successfully."}
        except Exception as e:
            return {"success": False, "message": f"Failed to send photo: {e}"}

    def send_video(self, thread_id: str, video_path: str, is_vanish: bool = False) -> Dict[str, Any]:
        """Send an MP4 video to the thread."""
        try:
            p = Path(video_path).expanduser().resolve()
            if not p.exists():
                return {"success": False, "message": f"File not found: {video_path}"}
            msg = self.cl.direct_send_video(p, thread_ids=[int(thread_id)])
            return {"success": True, "id": str(msg.id), "message": "Video sent successfully."}
        except Exception as e:
            return {"success": False, "message": f"Failed to send video: {e}"}

    def send_voice(self, thread_id: str, audio_path: str, is_vanish: bool = False) -> Dict[str, Any]:
        """Send a voice note (auto-converted to AAC/m4a in RAM)."""
        try:
            from icli.media import convert_audio_to_m4a
            p = Path(audio_path).expanduser().resolve()
            if not p.exists():
                return {"success": False, "message": f"File not found: {audio_path}"}

            m4a_path = convert_audio_to_m4a(p)
            if not m4a_path or not m4a_path.exists():
                return {"success": False, "message": "Failed to convert audio to m4a format."}

            msg = self.cl.direct_send_voice(m4a_path, thread_ids=[int(thread_id)])
            if m4a_path != p and m4a_path.exists():
                try:
                    m4a_path.unlink()
                except Exception:
                    pass
            return {"success": True, "id": str(msg.id), "message": "Voice note sent successfully."}
        except Exception as e:
            return {"success": False, "message": f"Failed to send voice note: {e}"}
