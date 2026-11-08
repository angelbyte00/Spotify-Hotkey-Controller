# Spotify Controller

A compact Windows desktop app for controlling Spotify with global hotkeys and your controller, with a clean "now playing" view, a system tray icon and an OBS stream overlay.

> **Windows only.** The app uses Windows APIs (media keys, media session, `winsound`), so it does not run on macOS or Linux.

<!-- Add screenshots here, e.g.:
![Home](screenshots/home.png)
-->

## Features

- **Global hotkeys** for Play/Pause, Next and Previous, freely configurable, work even when the window is hidden
- **Controller hotkeys**: skip, pause and like songs with your Xbox, PS4 or PS5 controller, including button combos (e.g. `LB + A`), without leaving your game
- **Like hotkey**: save the current song to your Spotify library with one key press (optional sound feedback)
- **Clear hotkey**: assign your own key to the Clear button
- **Now playing view** with cover art, progress bar and song history
- **3 now-playing designs**: Spotify, Spotlight, Clean
- **4 color themes**: Harbor, Nightfall, Moonlit, Steel
- **System tray**: minimize to tray, single-instance, optional `--tray` start
- **OBS overlay**: browser source with 3 styles (Card, Minimal, Badge)
- **Low RAM usage**: covers and images are released while the app sits in the tray
- **Always on top** option

## Download

1. Go to the [Releases](https://github.com/angelbyte00/Spotify-Hotkey-Controller/releases) page.
2. Download `SpotifyController.exe` from the latest release.
3. Run it. No installation needed.

Already using the app? Open **Settings → About** and click **Check for updates**.

Start minimized to the tray:

```
SpotifyController.exe --tray
```

### Requirements

- Windows 10 / 11
- Spotify desktop app

## Setup

### Controller hotkeys

Open the **Hotkeys** tab and switch to the controller page to assign buttons or button combos.

- **Xbox controllers** (360, One, Series X/S) work out of the box.
- **PS4 / PS5 controllers** (DualShock / DualSense) are detected automatically.
- **Other controllers** (e.g. Switch Pro) can be enabled in **Settings → General → Extended controllers (SDL)**. This uses more RAM and needs a restart.

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

This is an unofficial fan project. It is not affiliated with, endorsed by or sponsored by Spotify or Discord. All trademarks belong to their respective owners.
