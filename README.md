# Spotify Controller

A compact Windows desktop app for controlling Spotify with global hotkeys, a clean "now playing" view, a system tray icon, an OBS stream overlay and Discord Rich Presence.

> **Windows only.** The app uses Windows APIs (media keys, media session, `winsound`), so it does not run on macOS or Linux.

<!-- Add screenshots here, e.g.:
![Home](screenshots/home.png)
-->

## Features

- **Global hotkeys** for Play/Pause, Next and Previous, freely configurable, work even when the window is hidden
- **Like hotkey**: save the current song to your Spotify library with one key press (optional sound feedback)
- **Now playing view** with cover art, progress bar and song history
- **3 now-playing designs**: Spotify, Spotlight, Clean
- **4 color themes**: Harbor, Nightfall, Moonlit, Steel
- **System tray**: minimize to tray, single-instance, optional `--tray` start
- **OBS overlay**: browser source with 3 styles (Card, Minimal, Badge)
- **Discord Rich Presence**: show your current song on your Discord profile, including a "Listen on Spotify" button
- **Always on top** option

## Requirements

- Windows 10 / 11
- Python 3.9+
- Spotify desktop app

## Installation

```bash
git clone https://github.com/angelbyte00/Spotify-Hotkey-Controller.git
cd <your-repo>
pip install -r requirements.txt
python SpotifyController.py
```

Start minimized to the tray:

```bash
python SpotifyController.py --tray
```

### Optional packages

| Package | Needed for |
|---|---|
| `winsdk` | Cover art and playback state straight from the Windows media session. Without it, the song is read from the Spotify window title and covers are loaded from the web. Alternative: `winrt-Windows.Media.Control` + `winrt-Windows.Storage.Streams` |
| `pypresence` | Discord Rich Presence |

## Setup

### Like hotkey (Spotify)

1. Open the [Spotify Developer Dashboard](https://developer.spotify.com/dashboard) and create an app.
2. Add this Redirect URI: `http://127.0.0.1:8888/callback`
3. Copy the **Client ID** (and secret if requested) into **Settings → Spotify** and connect your account.
4. Assign a key to the Like action in the **Hotkeys** tab.

The app only requests the `user-library-modify` scope.

### OBS overlay

1. Enable the overlay in **Settings → Stream**.
2. In OBS, add a **Browser Source** with the URL:
   `http://127.0.0.1:8787/overlay` (port can be changed in the settings)

### Discord Rich Presence

1. Create an application at the [Discord Developer Portal](https://discord.com/developers/applications).
2. Paste its **Application ID** into **Settings → Discord** and enable it.
3. Keep the Discord desktop app running.

## Data and privacy

Everything stays on your PC. The app creates these files next to the program (settings falls back to `%APPDATA%\SpotifyController` if the folder is read-only):

| File | Content |
|---|---|
| `settings.json` | Settings and your Spotify credentials / refresh token |
| `hotkeys.json` | Your hotkey assignments |
| `history.json` | Recently played songs |
| `cover_cache/` | Cached cover images |

**Never share `settings.json`.** It contains your Spotify credentials.

## Build an EXE (optional)

```bash
pip install pyinstaller
pyinstaller --noconsole --onefile --icon spotify_pulse.ico ^
  --add-data "icon.png;." --add-data "spotify_pulse.ico;." SpotifyController.py
```

The finished `.exe` is in `dist/`.

## Disclaimer

This is an unofficial fan project. It is not affiliated with, endorsed by or sponsored by Spotify or Discord. All trademarks belong to their respective owners.

## License

[MIT](LICENSE)
