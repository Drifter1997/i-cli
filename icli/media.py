import os
import time
import uuid
import threading
import subprocess
from io import BytesIO
from pathlib import Path
from typing import Optional, Dict, Any, Tuple

import requests
from icli.config import (
    RAM_DIR,
    DOWNLOAD_DIR,
    IMV_PATH,
    MPV_PATH,
    CHAFA_PATH,
    THUMB_MAX_WIDTH,
    THUMB_MAX_HEIGHT,
)

# In-memory RAM cache for rendered ANSI thumbnails
_THUMBNAIL_CACHE: Dict[str, str] = {}


def fetch_bytes_in_ram(url: str, timeout: int = 15) -> Optional[bytes]:
    """Fetch media directly into RAM memory without touching disk."""
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Instagram 300.0.0.0.0"})
        if resp.status_code == 200:
            return resp.content
    except Exception:
        pass
    return None


def get_inline_thumbnail(image_url: str, max_width: int = THUMB_MAX_WIDTH, max_height: int = THUMB_MAX_HEIGHT) -> str:
    """Generate ANSI terminal thumbnail using chafa, cached in RAM."""
    if not image_url:
        return ""

    cache_key = f"{image_url}:{max_width}x{max_height}"
    if cache_key in _THUMBNAIL_CACHE:
        return _THUMBNAIL_CACHE[cache_key]

    raw_bytes = fetch_bytes_in_ram(image_url)
    if not raw_bytes:
        return ""

    try:
        # Run chafa with input piped via stdin to keep it 100% in RAM
        result = subprocess.run(
            [
                CHAFA_PATH,
                "-s", f"{max_width}x{max_height}",
                "--format=symbols",
                "--colors=256",
                "-"
            ],
            input=raw_bytes,
            capture_output=True,
            timeout=8
        )
        if result.returncode == 0 and result.stdout:
            rendered = result.stdout.decode("utf-8", errors="replace").strip("\n")
            _THUMBNAIL_CACHE[cache_key] = rendered
            return rendered
    except Exception:
        pass

    return ""


def _cleanup_ram_file_delayed(file_path: Path, proc: subprocess.Popen):
    """Wait for external viewer to finish, then delete temporary file in RAM."""
    try:
        proc.wait()
    except Exception:
        pass
    finally:
        try:
            if file_path.exists():
                file_path.unlink()
        except Exception:
            pass


def play_media(media_info: Dict[str, Any]) -> str:
    """
    Play/preview media strictly in RAM.
    Images: launched in imv via /dev/shm (Linux RAM tmpfs).
    Videos/Audios: streamed directly via mpv over HTTPS.
    """
    media_type = media_info.get("type", "unknown")
    url = media_info.get("url")

    if not url:
        return "Error: No media URL available."

    if media_type == "image":
        if not IMV_PATH:
            return "Error: 'imv' command not found on system."

        # Fetch image bytes into RAM
        raw_bytes = fetch_bytes_in_ram(url)
        if not raw_bytes:
            return "Error: Failed to fetch image stream into RAM."

        # Write to /dev/shm (Linux RAM tmpfs - never hits physical disk)
        unique_id = uuid.uuid4().hex[:8]
        ram_file = RAM_DIR / f"icli_preview_{unique_id}.jpg"
        with open(ram_file, "wb") as f:
            f.write(raw_bytes)

        # Launch imv in background and delete file upon exit
        proc = subprocess.Popen([IMV_PATH, str(ram_file)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        threading.Thread(target=_cleanup_ram_file_delayed, args=(ram_file, proc), daemon=True).start()
        return f"Opened image in imv (in RAM)"

    elif media_type == "video":
        if not MPV_PATH:
            return "Error: 'mpv' command not found on system."

        # Stream directly into mpv in RAM (zero disk writes)
        subprocess.Popen(
            [
                MPV_PATH,
                "--title=i-cli Video",
                "--cache=yes",
                "--demuxer-max-bytes=64MiB",
                "--force-window=yes",
                url
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"Streaming video in mpv (in RAM)"

    elif media_type == "audio":
        if not MPV_PATH:
            return "Error: 'mpv' command not found on system."

        # Stream audio directly into mpv in RAM
        subprocess.Popen(
            [
                MPV_PATH,
                "--no-video",
                "--title=i-cli Audio",
                url
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return f"Playing audio in mpv (in RAM)"

    else:
        return f"Unsupported media type: {media_type}"


def download_media(media_info: Dict[str, Any], target_dir: Path = DOWNLOAD_DIR) -> str:
    """Explicitly save media to disk when requested via :d."""
    url = media_info.get("url")
    if not url:
        return "Error: No media URL available to download."

    media_type = media_info.get("type", "media")
    ext = "jpg" if media_type == "image" else ("mp4" if media_type == "video" else "mp3")

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    filename = f"ig_{media_type}_{timestamp}_{uuid.uuid4().hex[:4]}.{ext}"
    dest_path = target_dir / filename

    raw_bytes = fetch_bytes_in_ram(url, timeout=30)
    if not raw_bytes:
        return "Error: Failed to download media."

    with open(dest_path, "wb") as f:
        f.write(raw_bytes)

    return f"Saved to {dest_path}"


def extract_media_info(msg: Any) -> Optional[Dict[str, Any]]:
    """Extract media type, playback URL, and thumbnail URL from instagrapi DirectMessage."""
    # Check regular media or media_share
    media = getattr(msg, "media", None)
    if media:
        # Check if video
        video_versions = getattr(media, "video_versions", None)
        if video_versions and len(video_versions) > 0:
            thumb_url = None
            image_versions = getattr(media, "image_versions2", None)
            if image_versions and hasattr(image_versions, "candidates") and len(image_versions.candidates) > 0:
                thumb_url = image_versions.candidates[0].url
            return {
                "type": "video",
                "url": video_versions[0].url,
                "thumbnail_url": thumb_url,
                "label": "Video"
            }

        # Check if photo
        image_versions = getattr(media, "image_versions2", None)
        if image_versions and hasattr(image_versions, "candidates") and len(image_versions.candidates) > 0:
            img_url = image_versions.candidates[0].url
            return {
                "type": "image",
                "url": img_url,
                "thumbnail_url": img_url,
                "label": "Photo"
            }

    # Check visual_media (disappearing / raven media in vanish mode)
    visual_media = getattr(msg, "visual_media", None)
    if visual_media:
        v_media = getattr(visual_media, "media", None)
        if v_media:
            video_versions = getattr(v_media, "video_versions", None)
            if video_versions and len(video_versions) > 0:
                thumb_url = None
                image_versions = getattr(v_media, "image_versions2", None)
                if image_versions and hasattr(image_versions, "candidates") and len(image_versions.candidates) > 0:
                    thumb_url = image_versions.candidates[0].url
                return {
                    "type": "video",
                    "url": video_versions[0].url,
                    "thumbnail_url": thumb_url,
                    "label": "Disappearing Video"
                }

            image_versions = getattr(v_media, "image_versions2", None)
            if image_versions and hasattr(image_versions, "candidates") and len(image_versions.candidates) > 0:
                img_url = image_versions.candidates[0].url
                return {
                    "type": "image",
                    "url": img_url,
                    "thumbnail_url": img_url,
                    "label": "Disappearing Photo"
                }

    # Check voice_media (audio voice notes)
    voice_media = getattr(msg, "voice_media", None)
    if voice_media:
        v_media = getattr(voice_media, "media", None)
        if v_media:
            audio_obj = getattr(v_media, "audio", None)
            if audio_obj and hasattr(audio_obj, "audio_src"):
                return {
                    "type": "audio",
                    "url": audio_obj.audio_src,
                    "thumbnail_url": None,
                    "label": "Voice Note"
                }

    # Check clip (reels shared in DM)
    clip = getattr(msg, "clip", None)
    if clip:
        clip_clip = getattr(clip, "clip", None)
        if clip_clip:
            video_versions = getattr(clip_clip, "video_versions", None)
            if video_versions and len(video_versions) > 0:
                thumb_url = None
                image_versions = getattr(clip_clip, "image_versions2", None)
                if image_versions and hasattr(image_versions, "candidates") and len(image_versions.candidates) > 0:
                    thumb_url = image_versions.candidates[0].url
                return {
                    "type": "video",
                    "url": video_versions[0].url,
                    "thumbnail_url": thumb_url,
                    "label": "Reel"
                }

    # Check animated_media (GIFs)
    animated = getattr(msg, "animated_media", None)
    if animated and isinstance(animated, dict):
        images = animated.get("images", {})
        downsized = images.get("downsized", {}) or images.get("fixed_height", {})
        if downsized and "url" in downsized:
            return {
                "type": "image",
                "url": downsized["url"],
                "thumbnail_url": downsized["url"],
                "label": "GIF"
            }

    # Check video_call_event (Audio / Video Call notification)
    if getattr(msg, "item_type", None) == "video_call_event":
        raw = getattr(msg, "video_call_event", {}) or {}
        action = raw.get("action", "call") if isinstance(raw, dict) else "call"
        return {
            "type": "call",
            "url": None,
            "thumbnail_url": None,
            "label": f"Call Event ({action})"
        }

    return None


def convert_audio_to_m4a(input_path: Path) -> Optional[Path]:
    """Convert any audio file to AAC/m4a in RAM for Instagram voice DM compatibility."""
    from icli.config import FFMPEG_PATH, RAM_DIR

    input_path = Path(input_path)
    if not input_path.exists():
        return None

    if input_path.suffix.lower() == ".m4a":
        return input_path

    output_path = RAM_DIR / f"converted_{uuid.uuid4().hex[:6]}.m4a"
    try:
        res = subprocess.run(
            [
                FFMPEG_PATH,
                "-y",
                "-i", str(input_path),
                "-c:a", "aac",
                "-b:a", "64k",
                "-ar", "44100",
                str(output_path)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=30
        )
        if res.returncode == 0 and output_path.exists():
            return output_path
    except Exception:
        pass
    return None


def record_voice_start() -> Tuple[Optional[subprocess.Popen], Optional[Path]]:
    """Start recording microphone audio directly into RAM using ffmpeg."""
    import signal
    from icli.config import FFMPEG_PATH, RAM_DIR

    output_path = RAM_DIR / f"mic_rec_{uuid.uuid4().hex[:6]}.m4a"
    try:
        proc = subprocess.Popen(
            [
                FFMPEG_PATH,
                "-y",
                "-f", "pulse",
                "-i", "default",
                "-c:a", "aac",
                "-b:a", "64k",
                "-ar", "44100",
                str(output_path)
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        return proc, output_path
    except Exception:
        return None, None


def record_voice_stop(proc: subprocess.Popen, output_path: Path) -> bool:
    """Stop recording audio gracefully and finalize the m4a container."""
    import signal
    try:
        proc.send_signal(signal.SIGINT)
        proc.wait(timeout=5)
        return output_path.exists() and output_path.stat().st_size > 100
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass
        return output_path.exists() and output_path.stat().st_size > 100
