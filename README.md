# Spotify Controller

A compact Windows desktop app for controlling Spotify with global hotkeys, a clean "now playing" view, a system tray icon, an OBS stream overlay.

> **Windows only.** The app uses Windows APIs (media keys, media session, `winsound`), so it does not run on macOS or Linux.

<p align="center">
  <img width="48%" alt="Screenshot 1" src="https://github.com/user-attachments/assets/75cd01fb-d946-42fd-9a86-483a871d0d39" />
  <img width="48%" alt="Screenshot 2" src="https://github.com/user-attachments/assets/1d43b1a7-5f50-4005-a8c8-17b0d2a8bca7" />
</p>
<p align="center">
  <img width="48%" alt="Screenshot 3" src="https://github.com/user-attachments/assets/bbbeba8a-16e1-4a11-a8c2-fa7d83c07a2f" />
  <img width="48%" alt="Screenshot 4" src="https://github.com/user-attachments/assets/1eebee70-4405-4a3a-a089-0c7098d5cd30" />
</p>
<p align="center">
  <img width="358" alt="Screenshot 5" src="https://github.com/user-attachments/assets/5361c521-18d1-437a-8079-c13349caf8d0" />
</p>

## Features

- **Global hotkeys** for Play/Pause, Next and Previous, freely configurable, work even when the window is hidden
- **Controller hotkeys**: skip, pause and like songs with your Xbox, PS4 or PS5 controller, including button combos (e.g. `LB + A`)
- **Like hotkey**: save the current song to your Spotify library with one key press (optional sound feedback)
- **Clear hotkey**: assign your own key to the Clear button
- **Now playing view** with cover art, progress bar and song history
- **3 now-playing designs**: Spotify, Spotlight, Clean
- **4 color themes**: Harbor, Nightfall, Moonlit, Steel
- **System tray**: minimize to tray, single-instance, optional `--tray` start
- **OBS overlay**: browser source with 3 styles (Card, Minimal, Badge)
- **Always on top** option

## Antivirus warning (false positive)

Some antivirus programs may flag `SpotifyController.exe` as a trojan (for example "Wacatac" or "Trojan.Python.Agent"). This is a **false positive**. It is a known issue with unsigned apps written in Python and packaged with PyInstaller, and with apps that use global hotkeys.

- The app does not download or run other programs and collects no personal data. It only connects to Spotify, cover art services and GitHub (version check).
- You can check the file yourself on [VirusTotal](https://www.virustotal.com/) with this SHA256 hash: `6ea42f5d045fc7110724e404ba592c9987d754253c144c7bb5cfc89101c56cf9`
- If your antivirus blocks it, add `SpotifyController.exe` to its exclusions list.
- I have reported the file to the antivirus vendors as a false positive.

If you are not comfortable running it, please don't.

## Requirements

- Windows 10 / 11
- Spotify desktop app

## Download

1. Go to the [Releases](https://github.com/angelbyte00/Spotify-Hotkey-Controller/releases) page.
2. Download `SpotifyController.exe` from the latest release.
3. Run it. No installation needed.

**Updating:** Open **Settings → About** and click **Check for updates**. If a new version is available, the app opens the download page in your browser.

Start minimized to the tray:

```
SpotifyController.exe --tray
```

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

## Data and privacy

Everything stays on your PC. The app creates these files next to the program (settings falls back to `%APPDATA%\SpotifyController` if the folder is read-only):

| File | Content |
|---|---|
| `settings.json` | Settings and your Spotify credentials / refresh token |
| `hotkeys.json` | Your hotkey assignments |
| `history.json` | Recently played songs |
| `cover_cache/` | Cached cover images |

**Never share `settings.json`.** It contains your Spotify credentials.

## Disclaimer

This is an unofficial fan project. It is not affiliated with, endorsed by or sponsored by Spotify. All trademarks belong to their respective owners.

## License

Copyright (c) 2026 angelbyte00. All rights reserved. See [LICENSE](LICENSE).
