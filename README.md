# 📱 i-cli

> **Minimal, keyboard-centric, and ephemeral Instagram CLI & TUI.**  
> Built for terminal power-users, tiling window manager workflows (Sway / Hyprland / i3), and Neovim enthusiasts.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Linux%20%2F%20Wayland-green.svg)]()
[![Security](https://img.shields.io/badge/Security-Isolated%20Storage%20%2B%20Zero%20Git%20Leaks-brightgreen.svg)]()
[![License](https://img.shields.io/badge/License-MIT-purple.svg)]()

---

## ✨ Features

- **👻 Vanish Mode**: Native support for Instagram disappearing messages and thread vanish states (`shh_mode`).
- **⚡ Keyboard & Terminal-Centric**: Instant single-mode prompt (no clunky modal switching), unbuffered raw arrow key navigation, fast page jumping, and smooth SGR mouse/touchpad scrolling.
- **🚀 100% RAM-Only Ephemeral Media (`:p`)**: All media previews stream strictly in Linux tmpfs RAM (`/dev/shm`):
  - **Photos**: Opened in `imv` directly from memory.
  - **Videos**: Streamed in RAM using `mpv`.
  - **Voice Notes**: Played in RAM using `mpv`.
  - Zero disk clutter — media vanishes on exit.
- **🖼️ Inline Terminal Thumbnails**: Compact ANSI previews rendered directly in your terminal cells via `chafa`.
- **🎙️ Voice Note Recording (`:rec`)**: Record voice notes straight from your microphone in RAM and send immediately.
- **💾 Explicit Downloads (`:d`)**: Media is only written to disk (`~/Downloads/`) when you explicitly command `:d`.
- **🔒 Zero Credential Leakage Architecture**:
  - Auth sessions and device configurations are stored strictly in `~/.config/i-cli/session.json` with strict `0600` permissions.
  - Storage is completely isolated outside the Git repository.
  - Built-in `.gitignore` rules and automated Git pre-commit hooks actively prevent credentials, cookies, and tokens from ever being committed or uploaded to Git.

---

## 🔒 Security & Privacy Guarantee

`i-cli` takes privacy and security seriously:
1. **Isolated Auth Directory**: Credentials, session cookies, and device fingerprints are stored exclusively in `~/.config/i-cli/` with restricted user-only permissions (`chmod 0600`).
2. **Never Committed to Git**: The repository includes strict `.gitignore` configurations and pre-commit verification hooks preventing any session files or tokens from entering Git history or being pushed to public repositories.
3. **RAM-First Ephemeral Footprint**: Previewed photos and streamed videos/audios live exclusively in `/dev/shm` (Linux RAM tmpfs) and are cleared automatically on exit.

---

## 📦 Requirements

- **Linux** (Arch Linux, Ubuntu, Fedora, Debian, etc.)
- **Python 3.10+** (Python 3.14 supported)
- **imv** (fast Wayland/X11 image viewer for `:p`)
- **mpv** (video and audio playback for `:p`)
- **chafa** (high-performance inline terminal graphics)
- **ffmpeg** (audio/video processing and voice note encoding)

On Arch Linux:
```bash
sudo pacman -S imv mpv chafa ffmpeg python
```

---

## 🚀 Installation & Quick Start

1. **Clone the repository**:
   ```bash
   git clone https://github.com/Drifter1997/i-cli.git ~/repo/i-cli
   cd ~/repo/i-cli
   ```

2. **Run the setup script**:
   ```bash
   bash setup.sh
   ```
   *(This initializes the virtual environment, installs requirements, and sets up Git security hooks.)*

3. **Launch i-cli**:
   ```bash
   ./i-cli
   ```

4. **Global Access (Optional)**:
   Add a symlink to your `$PATH` to launch `i-cli` from anywhere:
   ```bash
   ln -sf ~/repo/i-cli/i-cli ~/.local/bin/i-cli
   ```

---

## ⌨️ Controls & Navigation

### Single-Mode Unified Chat Prompt
No complex modal transitions (like NORMAL vs INSERT):
- **Send a message**: Type text and hit `Enter` (optimistic 0ms instant display).
- **Command Palette**: Type `:` to open the interactive command bar.
- **Scroll History**: Use `Up` / `Down` arrows, `PageUp` / `PageDown`, or your touchpad / mouse wheel.
- **Clear Input / Jump to Bottom**: Press `Esc`.

### Chat Commands (Type `:`)

| Command | Action |
|---|---|
| `<text>` | Send regular message (or vanish message if Vanish Mode is enabled) |
| `:rec` / `:record` | **Record voice note** from microphone and send |
| `:photo <path>` | Send a photo (JPG/PNG/WebP) |
| `:video <path>` | Send an MP4 video file |
| `:audio <path>` | Send an audio file as an Instagram voice note (auto-transcoded in RAM) |
| `:p` | Play / preview most recent media in RAM (`imv` / `mpv`) |
| `:p <n>` | Play / preview media item `#n` in RAM |
| `:d` | Download most recent media to `~/Downloads/` |
| `:d <n>` | Download media item `#n` to `~/Downloads/` |
| `:v` | Toggle Vanish Mode on/off for conversation |
| `:v <text>` | Send a single message in Vanish Mode |
| `:t` | Return to Inbox / Thread List |
| `:r` | Refresh conversation messages |
| `:h` / `:help` | Show command cheat sheet |
| `:q` | Quit application |

### Inbox / Thread List Navigation

| Key / Command | Action |
|---|---|
| `j` / `Down` | Move down thread list |
| `k` / `Up` | Move up thread list |
| `Enter` / `1-9` | Open selected conversation |
| `:r` | Refresh threads |
| `:logout` | Clear saved session and log out |
| `:q` | Quit application |

---

## 📁 Repository Structure

```
i-cli/
├── icli/
│   ├── __init__.py
│   ├── config.py       # Paths, tmpfs RAM configuration, external tool paths
│   ├── client.py       # Instagram API wrapper, auth, Vanish Mode
│   ├── media.py        # RAM streaming, chafa thumbnails, imv/mpv integration
│   └── ui.py           # Single-mode terminal UI, chat pagination, keyparser
├── .githooks/
│   └── pre-commit      # Automated secret leak prevention hook
├── i-cli               # Global CLI launcher script
├── main.py             # CLI entrypoint and argument parser
├── setup.sh            # One-step environment installer
├── requirements.txt    # Python dependencies
└── README.md
```

---

## 📄 License

MIT License. Designed with love for minimal terminal setups.
