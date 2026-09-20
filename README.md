# i-cli

A minimal, fast, and simple CLI/TUI Instagram messaging client designed for Neovim users and terminal enthusiasts.

## ✨ Features

- **👻 Vanish Mode**: Native support for Instagram disappearing messages and thread vanish states (`shh_mode`).
- **🚀 RAM-Only Media Playback (`:p`)**: All media is previewed strictly in RAM without touching your SSD/drive:
  - **Photos**: Viewed in `imv` via `/dev/shm` (Linux RAM tmpfs).
  - **Videos**: Streamed directly in RAM using `mpv`.
  - **Voice Notes / Audios**: Played directly in RAM using `mpv`.
- **🖼️ Inline Terminal Thumbnails**: Compact ANSI thumbnails rendered directly inside the chat window using `chafa`.
- **💾 Explicit Download (`:d`)**: Media is only written to disk (`~/Downloads/`) when you explicitly command `:d`.
- **🔒 Isolated Credentials**: Authentication and session cookies are stored exclusively in `~/.config/i-cli/session.json` (chmod `0600`). Never touches Firefox or other browser profiles.
- **🛠️ Clean & Hackable**: Built cleanly in `~/repo/i-cli` so you can customize and extend it effortlessly in `nvim`.

---

## 📦 Requirements

- **Linux** (Arch Linux / any system with standard tools)
- **Python 3.10+** (Python 3.14 supported)
- **imv** (for image preview)
- **mpv** (for video and audio playback)
- **chafa** (for inline terminal thumbnails)

---

## 🚀 Setup & Launch

1. Navigate to the repository:
   ```bash
   cd ~/repo/i-cli
   ```

2. Run the automated setup script:
   ```bash
   bash setup.sh
   ```

3. Launch the client:
   ```bash
   ./i-cli
   ```

4. (Optional) Symlink to your PATH for global access:
   ```bash
   ln -sf ~/repo/i-cli/i-cli ~/.local/bin/i-cli
   # or
   sudo ln -sf ~/repo/i-cli/i-cli /usr/local/bin/i-cli
   ```

---

## ⌨️ Controls & Navigation

### Unified Single-Mode Interface
There are no confusing modes or mode-switching keys (like NORMAL vs INSERT):
- **Send Messages**: Simply start typing your message and hit `Enter` to send instantly (0ms optimistic latency).
- **Commands**: Type `:` in the prompt to immediately display the interactive command bar with all available commands and shortcuts.
- **Scroll History**: Use `Up` and `Down` arrow keys to scroll through older messages line-by-line.
- **Clear / Reset**: Press `Esc` to clear your input or snap back to the latest message.

### In Chat Window

#### Navigation
- `Up` Arrow: Scroll up through older messages
- `Down` Arrow: Scroll down towards recent messages
- `Esc`: Clear input buffer or snap back to the bottom

#### Chat Commands (Type `:` to view inline)
| Command | Action |
|---|---|
| `<text>` | Send regular message (or vanish message if Vanish Mode is on) — instant 0ms optimistic send |
| `:rec` / `:record` | **Record voice note from microphone** in RAM and send |
| `:photo <path>` | Send a photo file (JPG/PNG/WebP) to conversation |
| `:video <path>` | Send an MP4 video file to conversation |
| `:audio <path>` | Send any audio file as a voice note (auto-converted to AAC/m4a in RAM) |
| `:p` | Play / preview most recent media in RAM (`imv` / `mpv`) |
| `:p <n>` | Play / preview media item `#n` in RAM |
| `:d` | Explicitly download most recent media to `~/Downloads/` |
| `:d <n>` | Explicitly download media item `#n` to `~/Downloads/` |
| `:v` | Toggle Vanish Mode on/off for conversation |
| `:v <text>` | Send a single message in Vanish Mode |
| `:t` | Return to Inbox / Thread List |
| `:r` | Refresh conversation messages |
| `:h` / `:help` | Show command reference |
| `:q` | Quit application |

### In Inbox / Thread List
| Key / Command | Action |
|---|---|
| `j` / `Down` | Move selector down |
| `k` / `Up` | Move selector up |
| `Enter` / `1-9` | Open selected conversation |
| `:r` | Refresh inbox threads |
| `:logout` | Clear saved session and logout |
| `:q` | Quit application |

---

## 📞 Audio / Video Calls Notice
- **Why Live Calls Aren't Supported in CLI**: Instagram audio/video calling relies on Meta's internal, proprietary WebRTC signaling and private encrypted TURN gateways. These protocols are closed-source, unversioned, and not exposed through any public or reverse-engineered API.
- **What is Supported**:
  - **Voice Notes (`:rec`)**: Record and send voice notes with your microphone.
  - **Video Sharing (`:video`)**: Send and receive video messages with instant RAM playback (`:p`).
  - **Call Event Alerts**: Incoming and missed call events appear directly in chat (`📞 [Call Event]`).

---

## 📁 Project Structure (for editing in `nvim`)

```
~/repo/i-cli/
├── icli/
│   ├── __init__.py
│   ├── config.py     # Paths, RAM tmpfs directory, tool paths
│   ├── client.py     # Instagram API wrapper, auth, Vanish Mode
│   ├── media.py      # RAM media streaming, chafa thumbnails, imv/mpv
│   └── ui.py         # Terminal interface, chat flow, commands
├── i-cli             # Executable launcher script
├── main.py           # Application entry point
├── setup.sh          # Environment and dependency installer
├── requirements.txt  # Python package dependencies
└── README.md
```
