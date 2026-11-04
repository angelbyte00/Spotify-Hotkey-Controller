import asyncio
import base64
import colorsys
import ctypes
import hashlib
import http.server
import io
import json
import math
import os
import queue
import re
import secrets
import sys
import threading
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
import winsound
from ctypes import wintypes
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
from pystray import Icon, Menu, MenuItem
from PIL import (Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter,
                 ImageFont, ImageGrab, ImageOps, ImageTk)

# Optional: cover art + playback state straight from the Windows media session.
#   pip install winsdk   (or: pip install winrt-Windows.Media.Control winrt-Windows.Storage.Streams)
# Without it the app still works: song from the Spotify window title, covers from the web.
HAS_MEDIA = False
try:
    from winsdk.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as SessionManager,
        GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
    )
    from winsdk.windows.storage.streams import DataReader
    HAS_MEDIA = True
except Exception:
    try:
        from winrt.windows.media.control import (
            GlobalSystemMediaTransportControlsSessionManager as SessionManager,
            GlobalSystemMediaTransportControlsSessionPlaybackStatus as PlaybackStatus,
        )
        from winrt.windows.storage.streams import DataReader
        HAS_MEDIA = True
    except Exception:
        pass

# Optional: Discord Rich Presence ("now playing" on your Discord profile).
#   pip install -U pypresence   (needs a recent version for the "buttons" field)
# Without it the app still works, the Discord tab in Settings just says so.
HAS_DISCORD = False
try:
    from pypresence import Presence as _DiscordPresence
    HAS_DISCORD = True
except Exception:
    pass

APP_NAME = "Spotify Controller"
APP_VERSION = "2.2"
APP_ID = "airangelic.SpotifyController"

# Snapshot-Fade beim Tab-Wechsel. Macht Screenshots vom Bildschirm und ein extra
# Fenster -> verursacht Lag und Geisterbilder. Auf True stellen, falls du ihn zurueck willst.
FADES = False

# Wie schnell Spotify abgefragt wird (Sekunden bzw. Millisekunden)
WATCH_INTERVAL = 0.25
UI_TICK_MS = 200
OPTIMISTIC_S = 1.5    # so lange wird der echte Play-Status nach Klick/Hotkey ignoriert
LIST_MAX = 30         # max. Zeilen in der History-Liste (ohne Suche)
LIKE_SOUND = True     # kurzer Ton nach erfolgreichem Like (hilfreich, wenn das Fenster im Tray ist)
LIKE_REDIRECT_PORT = 8888   # Redirect URI in der Spotify-App: http://127.0.0.1:8888/callback
OVERLAY_DEFAULT_PORT = 8787  # OBS Browser-Source: http://127.0.0.1:8787/overlay

BASE_DIR = os.path.dirname(sys.executable if getattr(sys, "frozen", False)
                           else os.path.abspath(__file__))
RESOURCE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)
CONFIG_FILE = os.path.join(BASE_DIR, "hotkeys.json")


def _data_dir():
    """Ordner fuer settings.json: neben dem Programm, sonst %APPDATA% (z.B. wenn die EXE
    in einem schreibgeschuetzten Ordner liegt - sonst wuerde die Theme-Wahl nie gespeichert)."""
    try:
        test = os.path.join(BASE_DIR, ".write_test")
        with open(test, "w") as f:
            f.write("x")
        os.remove(test)
        return BASE_DIR
    except Exception:
        pass
    try:
        d = os.path.join(os.environ.get("APPDATA") or BASE_DIR, "SpotifyController")
        os.makedirs(d, exist_ok=True)
        old = os.path.join(BASE_DIR, "settings.json")
        new = os.path.join(d, "settings.json")
        if os.path.exists(old) and not os.path.exists(new):
            with open(old, "rb") as a, open(new, "wb") as b:
                b.write(a.read())
        return d
    except Exception:
        return BASE_DIR


SETTINGS_FILE = os.path.join(_data_dir(), "settings.json")
HISTORY_FILE = os.path.join(BASE_DIR, "history.json")
CACHE_DIR = os.path.join(BASE_DIR, "cover_cache")
ICON_PNG_PATH = os.path.join(RESOURCE_DIR, "icon.png")
ICO_PATH = os.path.join(RESOURCE_DIR, "spotify_pulse.ico")   # Fenster-, Taskleisten- und Tray-Icon

# =============================
# THEMES
# =============================
THEMES = {
    # Blue-grey themes (palette inspired: Blue Serenity / Moonlit Shadow Dance)
    "harbor": dict(
        name="Harbor",
        accent="#AEC6FF",
        accent_h="#C9D9FF",
        glow=(174, 198, 255),
        glow2=(60, 80, 140),
        bg="#0A0D16",
        panel="#0F1420",
        soft="#151B2B",
        soft_h="#1E2740",
        line="#1F2842",
        dim="#222F52",
        sel="#2C3D6B",
        on_accent="#0A1228"
    ),
    "nightfall": dict(
        name="Nightfall",
        accent="#7FA3C0",
        accent_h="#A2C0D6",
        glow=(49, 70, 95),
        glow2=(16, 27, 36),
        bg="#0A1218",
        panel="#0F1A22",
        soft="#15232E",
        soft_h="#1D2F3E",
        line="#1B2B38",
        dim="#1F3347",
        sel="#2B435D",
        on_accent="#08121A"
    ),
    "moonlit": dict(
        name="Moonlit",
        accent="#9A8FC0",
        accent_h="#B5ABD8",
        glow=(74, 65, 97),
        glow2=(22, 30, 26),
        bg="#08090B",
        panel="#0E0F12",
        soft="#16151B",
        soft_h="#201E28",
        line="#25222E",
        dim="#2A2638",
        sel="#3A3450",
        on_accent="#120F1C"
    ),
    "steel": dict(
        name="Steel",
        accent="#94A3B8",
        accent_h="#B4C0D0",
        glow=(100, 116, 139),
        glow2=(30, 41, 59),
        bg="#0C0E11",
        panel="#12151A",
        soft="#191D24",
        soft_h="#222730",
        line="#222730",
        dim="#262D3A",
        sel="#323B4D",
        on_accent="#0C0E11"
    ),
}
COMMON = dict(text="#F2F2F7", muted="#808792")
T = {}


def apply_theme(key):
    if key not in THEMES:
        key = "harbor"
    T.clear()
    T.update(THEMES[key])
    T.update(COMMON)
    T["key"] = key


def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def rgb2hex(c):
    return "#%02x%02x%02x" % tuple(int(v) for v in c[:3])


def mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


# =============================
# SETTINGS & HOTKEY CONFIG
# =============================
settings = {"close_action": "tray", "look": "harbor", "appearance_version": 1,
            "always_on_top": True, "now_playing_style": "Spotify",
            "spotify_id": "", "spotify_secret": "", "spotify_refresh": "",
            "overlay_enabled": False, "overlay_port": OVERLAY_DEFAULT_PORT, "overlay_style": "Card",
            "discord_enabled": False, "discord_client_id": ""}


def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r") as f:
                loaded = json.load(f)
            for k in settings:
                if k in loaded:
                    settings[k] = loaded[k]
            if loaded.get("appearance_version", 0) < 1:
                settings["look"] = "harbor"
                settings["appearance_version"] = 1
                save_settings()
            elif settings["look"] not in THEMES:
                settings["look"] = "harbor"
                save_settings()
            elif settings["now_playing_style"] not in NOW_PLAYING_STYLES:
                settings["now_playing_style"] = "Spotify"
                save_settings()
            elif settings.get("overlay_style") not in OVERLAY_STYLES:
                settings["overlay_style"] = "Card"
                save_settings()
    except Exception:
        pass


def save_settings():
    try:
        tmp = SETTINGS_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(settings, f, indent=4)
        os.replace(tmp, SETTINGS_FILE)   # atomar: keine halb geschriebene Datei beim Schliessen
    except Exception:
        pass


DEFAULT_CONFIG = {
    "next": 0x78,        # F9
    "prev": 0x76,        # F7
    "play_pause": 0x77,  # F8
    "like": 0x79,        # F10
}
ACTION_ORDER = ["prev", "play_pause", "next", "like"]
LABELS = {
    "prev": "Previous song",
    "play_pause": "Play / Pause",
    "next": "Next song",
    "like": "Like song",
}

config = DEFAULT_CONFIG.copy()
key_state = {}
runtime = {"capturing": False}


def load_config():
    config.clear()
    config.update(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
            for k, v in loaded.items():
                if k in DEFAULT_CONFIG:
                    config[k] = int(v) if v is not None else None
            if "vol_up" in loaded or "vol_down" in loaded:
                save_config()
        else:
            save_config()
    except Exception:
        config.clear()
        config.update(DEFAULT_CONFIG)
        save_config()


def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, indent=4)


def load_history():
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            j = json.load(f)
        hist = [tuple(x) for x in j.get("history", []) if isinstance(x, list) and len(x) == 2]
        return hist[:50], dict(j.get("ids", {}))
    except Exception:
        return [], {}


def save_history(hist, ids):
    try:
        keep = {"\t".join(k): ids["\t".join(k)] for k in hist if "\t".join(k) in ids}
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump({"history": [list(k) for k in hist], "ids": keep}, f, ensure_ascii=False)
        return True
    except Exception:
        return False


# =============================
# WINDOWS API
# =============================
VK_MEDIA_NEXT, VK_MEDIA_PREV, VK_MEDIA_PLAY = 0xB0, 0xB1, 0xB3

ACTIONS = {
    "next": VK_MEDIA_NEXT,
    "prev": VK_MEDIA_PREV,
    "play_pause": VK_MEDIA_PLAY,
}


def press_key(code):
    ctypes.windll.user32.keybd_event(code, 0, 0, 0)
    ctypes.windll.user32.keybd_event(code, 0, 2, 0)


def _build_names():
    n = {}
    for i in range(24):
        n[0x70 + i] = f"F{i + 1}"
    for i in range(10):
        n[0x30 + i] = str(i)
        n[0x60 + i] = f"NUM {i}"
    for i in range(26):
        n[0x41 + i] = chr(0x41 + i)
    n.update({
        0x20: "SPACE", 0x0D: "ENTER", 0x08: "BACKSPACE", 0x09: "TAB",
        0x2D: "INSERT", 0x2E: "DELETE", 0x24: "HOME", 0x23: "END",
        0x21: "PG UP", 0x22: "PG DOWN", 0x25: "←", 0x26: "↑", 0x27: "→", 0x28: "↓",
        0x13: "PAUSE", 0x91: "SCROLL", 0x6A: "NUM *", 0x6B: "NUM +",
        0x6D: "NUM -", 0x6F: "NUM /", 0x6E: "NUM .",
        0x10: "SHIFT", 0x11: "CTRL", 0x12: "ALT",
        0xA0: "L-SHIFT", 0xA1: "R-SHIFT", 0xA2: "L-CTRL", 0xA3: "R-CTRL",
        0xA4: "L-ALT", 0xA5: "R-ALT",
    })
    return n


VK_NAMES = _build_names()


def key_name(vk):
    if vk is None:
        return "—"
    return VK_NAMES.get(vk, f"KEY {vk}")


def is_pressed(vk):
    if vk is None:
        return False
    return bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)


def hotkey_loop():
    while True:
        if not runtime["capturing"]:
            for action, vk in list(config.items()):
                if vk is None:
                    continue
                if is_pressed(vk):
                    if not key_state.get(vk, False):
                        if action == "like":
                            # kein Media-Key, sondern Spotify Web API (siehe SpotifyUser)
                            if hud:
                                hud.post(hud.like_current)
                        else:
                            press_key(ACTIONS[action])
                            # UI sofort informieren (optimistisches Update), nicht auf Spotify warten
                            if hud:
                                hud.post(lambda a=action: hud.after_action(a))
                        key_state[vk] = True
                else:
                    key_state[vk] = False
        time.sleep(0.03)


_u = ctypes.WinDLL("user32", use_last_error=True)
_k = ctypes.WinDLL("kernel32", use_last_error=True)

EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
_k.OpenProcess.restype = wintypes.HANDLE
_k.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
_k.QueryFullProcessImageNameW.argtypes = [
    wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
_k.CloseHandle.argtypes = [wintypes.HANDLE]
_k.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
_k.CreateMutexW.restype = wintypes.HANDLE
_k.CreateEventW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
_k.CreateEventW.restype = wintypes.HANDLE
_k.SetEvent.argtypes = [wintypes.HANDLE]
_k.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
_u.GetWindowTextLengthW.argtypes = [wintypes.HWND]
_u.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
_u.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
_u.EnumWindows.argtypes = [EnumWindowsProc, wintypes.LPARAM]
_u.GetParent.argtypes = [wintypes.HWND]
_u.GetParent.restype = wintypes.HWND
_u.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
_u.GetWindowLongW.restype = ctypes.c_long
_u.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_long]
_u.SetWindowLongW.restype = ctypes.c_long
_u.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]

_pid_cache = {}


def _is_spotify(pid):
    if pid in _pid_cache:
        return _pid_cache[pid]
    ok = False
    h = _k.OpenProcess(0x1000, False, pid)
    if h:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if _k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            ok = os.path.basename(buf.value).lower() == "spotify.exe"
        _k.CloseHandle(h)
    _pid_cache[pid] = ok
    return ok


def read_window_title():
    """Fallback without media session: Spotify shows 'Artist - Song' while playing."""
    found = {"running": False, "title": None}

    def cb(hwnd, lparam):
        length = _u.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        pid = wintypes.DWORD()
        _u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not _is_spotify(pid.value):
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _u.GetWindowTextW(hwnd, buf, length + 1)
        text = buf.value
        found["running"] = True
        if " - " in text and not text.startswith("Spotify"):
            found["title"] = text
        return True

    _u.EnumWindows(EnumWindowsProc(cb), 0)
    return found


class MediaWatcher(threading.Thread):
    """Polls Spotify in the background (media session first, window title as fallback)."""

    def __init__(self):
        super().__init__(daemon=True)
        self.lock = threading.Lock()
        self.state = {"running": False, "artist": "", "title": "", "playing": False, "thumb": None}
        self._last_key = None
        self._thumb = None
        self._tries = 0
        self._mgr = None   # SessionManager wiederverwenden statt jedes Mal neu anfragen

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    async def _read_thumb(self, ref):
        stream = await ref.open_read_async()
        size = int(stream.size)
        if size <= 0:
            return None
        reader = DataReader(stream)
        await reader.load_async(size)
        buf = bytearray(size)
        reader.read_bytes(buf)
        return bytes(buf)

    async def _media(self):
        if self._mgr is None:
            self._mgr = await SessionManager.request_async()
        mgr = self._mgr
        session = None
        for s in mgr.get_sessions():
            if "spotify" in (s.source_app_user_model_id or "").lower():
                session = s
                break
        if session is None:
            return None
        props = await session.try_get_media_properties_async()
        info = session.get_playback_info()
        artist, title = props.artist or "", props.title or ""
        key = (artist, title)
        if key != self._last_key:
            self._last_key, self._thumb, self._tries = key, None, 0
        if self._thumb is None and self._tries < 6 and props.thumbnail is not None:
            self._tries += 1
            try:
                self._thumb = await self._read_thumb(props.thumbnail)
            except Exception:
                pass
        position = duration = None
        try:
            timeline = session.get_timeline_properties()
            start = self._timeline_seconds(timeline.start_time)
            position = max(0, self._timeline_seconds(timeline.position) - start)
            duration = max(0, self._timeline_seconds(timeline.end_time) - start)
        except (AttributeError, OSError, TypeError, ValueError, OverflowError):
            pass
        return {"running": True, "artist": artist, "title": title,
                "playing": info.playback_status == PlaybackStatus.PLAYING,
                "thumb": self._thumb, "position": position, "duration": duration}

    @staticmethod
    def _timeline_seconds(value):
        return value.total_seconds()

    def _from_title(self):
        info = read_window_title()
        artist, title = "", ""
        if info["title"]:
            artist, title = info["title"].split(" - ", 1)
        return {"running": info["running"], "artist": artist.strip(), "title": title.strip(),
                "playing": bool(info["title"]), "thumb": None,
                "position": None, "duration": None}

    def run(self):
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            st = None
            try:
                if HAS_MEDIA:
                    st = loop.run_until_complete(self._media())
            except Exception:
                self._mgr = None
                st = None
            if st is None:
                try:
                    st = self._from_title()
                except Exception:
                    st = {"running": False, "artist": "", "title": "", "playing": False, "thumb": None}
            with self.lock:
                self.state = st
            time.sleep(WATCH_INTERVAL)


# =============================
# WEB LOOKUPS: COVERS + TRACK IDS (no login needed)
# =============================
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) SpotifyController/2.2"


def http_get(url, headers=None, data=None, timeout=8):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, data=data, headers=h)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def http_json(url, headers=None, data=None, timeout=8):
    return json.loads(http_get(url, headers, data, timeout).decode("utf-8", "replace"))


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").lower()
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def _base_title(s):
    s = re.sub(r"[\(\[][^\)\]]*[\)\]]", " ", s or "")
    s = re.split(r"\s-\s", s)[0]
    return _norm(s)


def _artist_ok(a, b):
    nb = _norm(b)
    if not _norm(a) or not nb:
        return False
    parts = [_norm(p) for p in re.split(r",|&|;|/|\bfeat\.?\b|\bft\.?\b|\bx\b", (a or "").lower())]
    parts = [p for p in parts if p]
    na = _norm(a)
    return na in nb or nb in na or any(p in nb for p in parts)


def pick_match(cands, artist, title, min_score=1):
    """cands: [(title, artist, payload)]. Score 3 = same title, 2 = same without (…)/- suffix,
    1 = one contains the other. Artist must always match."""
    ft, bt = _norm(title), _base_title(title)
    best, best_score = None, 0
    for ct, ca, payload in cands:
        if not _artist_ok(artist, ca):
            continue
        cft, cbt = _norm(ct), _base_title(ct)
        if cft == ft:
            score = 3
        elif bt and cbt == bt:
            score = 2
        elif bt and cbt and (bt in cbt or cbt in bt):
            score = 1
        else:
            continue
        if score >= min_score and score > best_score:
            best, best_score = payload, score
    return best


class SpotifyAPI:
    """Optional: Spotify Web API with client credentials (no user login)."""

    def __init__(self):
        self.token, self.exp = None, 0.0

    def configured(self):
        return bool(settings.get("spotify_id") and settings.get("spotify_secret"))

    def reset(self):
        self.token, self.exp = None, 0.0

    def get_token(self):
        if self.token and time.time() < self.exp - 30:
            return self.token
        cred = base64.b64encode(
            f'{settings["spotify_id"]}:{settings["spotify_secret"]}'.encode()).decode()
        j = http_json("https://accounts.spotify.com/api/token",
                      headers={"Authorization": "Basic " + cred,
                               "Content-Type": "application/x-www-form-urlencoded"},
                      data=b"grant_type=client_credentials")
        self.token = j["access_token"]
        self.exp = time.time() + int(j.get("expires_in", 3600))
        return self.token

    def find(self, artist, title, min_score=2):
        tok = self.get_token()
        clean_t, clean_a = title.replace('"', " "), artist.replace('"', " ")
        for q in (f'track:"{clean_t}" artist:"{clean_a}"', f"{clean_a} {clean_t}"):
            j = http_json("https://api.spotify.com/v1/search?type=track&limit=10&q="
                          + urllib.parse.quote(q), headers={"Authorization": "Bearer " + tok})
            items = j.get("tracks", {}).get("items", [])
            cands = [(it.get("name", ""), ", ".join(a.get("name", "") for a in it.get("artists", [])), it)
                     for it in items]
            hit = pick_match(cands, artist, title, min_score)
            if hit:
                imgs = hit.get("album", {}).get("images", [])
                return {"id": hit.get("id"), "image": imgs[0]["url"] if imgs else None}
        return None


spotify_api = SpotifyAPI()


class SpotifyUser:
    """Spotify-Login (Authorization Code + PKCE, kein Client Secret noetig).
    Wird nur fuer den Like-Hotkey gebraucht. Der Refresh-Token liegt in settings.json."""
    REDIRECT = f"http://127.0.0.1:{LIKE_REDIRECT_PORT}/callback"
    SCOPE = "user-library-modify"

    def __init__(self):
        self.token, self.exp = None, 0.0
        self._lock = threading.Lock()

    def linked(self):
        return bool(settings.get("spotify_id") and settings.get("spotify_refresh"))

    def unlink(self):
        self.token, self.exp = None, 0.0
        settings["spotify_refresh"] = ""
        save_settings()

    def _store(self, j):
        self.token = j["access_token"]
        self.exp = time.time() + int(j.get("expires_in", 3600))
        if j.get("refresh_token"):
            settings["spotify_refresh"] = j["refresh_token"]
            save_settings()

    def _token_call(self, params):
        return http_json("https://accounts.spotify.com/api/token",
                         headers={"Content-Type": "application/x-www-form-urlencoded"},
                         data=urllib.parse.urlencode(params).encode())

    def connect(self, timeout=180):
        """Oeffnet den Browser zum Login und wartet auf den Redirect. Blockiert -> in Thread aufrufen."""
        cid = settings.get("spotify_id", "").strip()
        if not cid:
            raise RuntimeError("Client ID fehlt")
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
        state = secrets.token_urlsafe(12)
        result = {}

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                if u.path != "/callback":
                    self.send_response(404)
                    self.end_headers()
                    return
                q = urllib.parse.parse_qs(u.query)
                result["code"] = (q.get("code") or [None])[0]
                result["error"] = (q.get("error") or [None])[0]
                result["state"] = (q.get("state") or [None])[0]
                ok = bool(result["code"])
                body = ("<html><body style='font-family:Segoe UI;background:#09090B;color:#F2F2F7;"
                        "text-align:center;padding-top:80px'><h2>"
                        + ("Connected &#10003;" if ok else "Login cancelled")
                        + "</h2><p>You can close this tab.</p></body></html>").encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *a):
                pass

        srv = http.server.HTTPServer(("127.0.0.1", LIKE_REDIRECT_PORT), Handler)
        srv.timeout = 1
        try:
            webbrowser.open("https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
                "client_id": cid, "response_type": "code", "redirect_uri": self.REDIRECT,
                "scope": self.SCOPE, "state": state,
                "code_challenge_method": "S256", "code_challenge": challenge}))
            deadline = time.time() + timeout
            while time.time() < deadline and "code" not in result:
                srv.handle_request()
        finally:
            srv.server_close()
        if not result.get("code") or result.get("state") != state:
            raise RuntimeError(result.get("error") or "Login abgebrochen")
        with self._lock:
            self._store(self._token_call({
                "grant_type": "authorization_code", "code": result["code"],
                "redirect_uri": self.REDIRECT, "client_id": cid, "code_verifier": verifier}))

    def get_token(self):
        with self._lock:
            if self.token and time.time() < self.exp - 30:
                return self.token
            if not self.linked():
                raise RuntimeError("not linked")
            self._store(self._token_call({
                "grant_type": "refresh_token", "refresh_token": settings["spotify_refresh"],
                "client_id": settings["spotify_id"]}))
            return self.token

    def save_track(self, tid):
        """Song zu 'Lieblingssongs' hinzufuegen (PUT /me/library, Fallback: PUT /me/tracks)."""
        tok = self.get_token()

        def put(url):
            req = urllib.request.Request(url, data=b"", method="PUT", headers={
                "Authorization": "Bearer " + tok, "User-Agent": UA,
                "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=8).read()

        try:
            put("https://api.spotify.com/v1/me/library?uris="
                + urllib.parse.quote("spotify:track:" + tid, safe=""))
        except urllib.error.HTTPError as e:
            if e.code in (404, 405, 410):
                put("https://api.spotify.com/v1/me/tracks?ids=" + tid)
            else:
                raise


spotify_user = SpotifyUser()


def itunes_find(artist, title, min_score=1):
    q = urllib.parse.quote(f"{artist} {title}")
    j = http_json(f"https://itunes.apple.com/search?term={q}&media=music&entity=song&limit=10")
    cands = [(r.get("trackName", ""), r.get("artistName", ""), r) for r in j.get("results", [])]
    return pick_match(cands, artist, title, min_score)


def deezer_find(artist, title, min_score=1):
    q = urllib.parse.quote(f'artist:"{artist}" track:"{title}"')
    j = http_json(f"https://api.deezer.com/search?limit=10&q={q}")
    cands = [(r.get("title", ""), r.get("artist", {}).get("name", ""), r) for r in j.get("data", [])]
    hit = pick_match(cands, artist, title, min_score)
    if not hit:
        q = urllib.parse.quote(f"{artist} {title}")
        j = http_json(f"https://api.deezer.com/search?limit=10&q={q}")
        cands = [(r.get("title", ""), r.get("artist", {}).get("name", ""), r) for r in j.get("data", [])]
        hit = pick_match(cands, artist, title, min_score)
    return hit


def find_cover_url(key):
    artist, title = key
    if spotify_api.configured():
        try:
            t = spotify_api.find(artist, title, 1)
            if t and t.get("image"):
                return t["image"]
        except Exception:
            pass
    try:
        r = itunes_find(artist, title, 1)
        if r and r.get("artworkUrl100"):
            return r["artworkUrl100"].replace("100x100", "600x600")
    except Exception:
        pass
    try:
        r = deezer_find(artist, title, 1)
        if r:
            alb = r.get("album", {})
            return alb.get("cover_xl") or alb.get("cover_big") or alb.get("cover_medium")
    except Exception:
        pass
    return None


def resolve_track_id(key):
    """Spotify track id for (artist, title) or None. Only exact titles are accepted for the
    free path, so a sped-up / remix version is never swapped for the original."""
    artist, title = key
    if spotify_api.configured():
        try:
            t = spotify_api.find(artist, title, 2)
            if t and t.get("id"):
                return t["id"]
        except Exception:
            pass
    r = itunes_find(artist, title, 3)
    if not r or not r.get("trackId"):
        return None
    j = http_json("https://api.song.link/v1-alpha.1/links?platform=itunes&type=song&id="
                  f"{r['trackId']}&userCountry=US", timeout=10)
    sp = j.get("linksByPlatform", {}).get("spotify", {})
    m = re.search(r"track/([A-Za-z0-9]+)", sp.get("url", "") or "")
    if m:
        return m.group(1)
    m = re.search(r"SPOTIFY_SONG::([A-Za-z0-9]+)", sp.get("entityUniqueId", "") or "")
    return m.group(1) if m else None


class CoverFetcher(threading.Thread):
    """Background cover downloads with a disk cache and gentle pacing."""

    def __init__(self):
        super().__init__(daemon=True)
        self.q = queue.PriorityQueue()
        self.seen = set()
        self.done = {}
        self.lock = threading.Lock()
        self.n = 0

    def request(self, key, prio=5):
        with self.lock:
            if key in self.seen:
                return
            self.seen.add(key)
            self.n += 1
            self.q.put((prio, self.n, key))

    def take(self):
        with self.lock:
            out, self.done = self.done, {}
        return out

    @staticmethod
    def path(key):
        return os.path.join(CACHE_DIR, hashlib.md5("\t".join(key).encode("utf-8")).hexdigest() + ".jpg")

    def run(self):
        while True:
            prio, _, key = self.q.get()
            data = None
            pace = 0.0
            try:
                p = self.path(key)
                if os.path.exists(p):
                    with open(p, "rb") as f:
                        data = f.read()
                else:
                    url = find_cover_url(key)
                    pace = 0.4 if prio == 0 else (1.2 if spotify_api.configured() else 2.6)
                    if url:
                        raw = http_get(url, timeout=10)
                        im = Image.open(io.BytesIO(raw))
                        im.load()
                        os.makedirs(CACHE_DIR, exist_ok=True)
                        im.convert("RGB").save(p, "JPEG", quality=90)
                        with open(p, "rb") as f:
                            data = f.read()
            except Exception:
                pace = 2.0
            if data:
                with self.lock:
                    self.done[key] = data
            if pace:
                time.sleep(pace)


# =============================
# OBS OVERLAY (local HTTP server, "Browser Source")
# =============================
_overlay_lock = threading.Lock()
_overlay_state = {"artist": "", "title": "", "playing": False, "running": False, "cover_ver": 0}
_overlay_cover = None


def update_overlay_state(artist, title, playing, running, cover_bytes=None):
    """Called from the UI thread (see App._poll) whenever the state might have changed."""
    global _overlay_cover
    with _overlay_lock:
        if cover_bytes is not None:
            _overlay_cover = cover_bytes
            _overlay_state["cover_ver"] = _overlay_state.get("cover_ver", 0) + 1
        _overlay_state["artist"] = artist
        _overlay_state["title"] = title
        _overlay_state["playing"] = playing
        _overlay_state["running"] = running


OVERLAY_HTML = r"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Now Playing</title>
<style>
  :root{ --accent: __ACCENT__; }
  html,body{
    margin:0; padding:0; background:transparent;
    font-family:"Segoe UI",-apple-system,Roboto,Arial,sans-serif;
    overflow:hidden;
  }
  /* The box has a FIXED width/height per design below, so a song switch - longer or
     shorter title, cover or no cover - never changes the overlay's size, only its content. */
  #card{
    position:fixed; left:24px; bottom:24px;
    display:flex; align-items:center; gap:14px;
    box-sizing:border-box;
    border-radius:16px;
    background:rgba(10,12,18,.72);
    backdrop-filter:blur(10px);
    -webkit-backdrop-filter:blur(10px);
    border:1px solid rgba(255,255,255,.08);
    box-shadow:0 10px 28px rgba(0,0,0,.35);
    opacity:0; transform:translateY(10px);
    transition:opacity .4s ease, transform .4s ease;
  }
  #card.show{ opacity:1; transform:translateY(0); }

  #card[data-style="card"]{ width:380px; height:74px; padding:10px 20px 10px 10px; }
  #card[data-style="minimal"]{ width:380px; height:56px; padding:0 22px; border-radius:14px; }
  #card[data-style="badge"]{ width:330px; height:64px; padding:8px 18px 8px 8px; border-radius:36px; }

  /* Artwork slot: a real cover and a gradient placeholder sit on top of each other at the
     same fixed size, so loading / missing art never changes the layout either. */
  #artwrap{ position:relative; flex:none; overflow:hidden; border-radius:10px; background:#15171c; }
  #card[data-style="card"] #artwrap{ width:54px; height:54px; }
  #card[data-style="badge"] #artwrap{ width:48px; height:48px; border-radius:50%; }
  #card[data-style="minimal"] #artwrap{ display:none; }
  #art, #artFallback{ position:absolute; inset:0; width:100%; height:100%; }
  #art{ object-fit:cover; opacity:0; transition:opacity .3s ease; }
  #art.show{ opacity:1; }
  #artFallback{
    display:flex; align-items:center; justify-content:center;
    background:linear-gradient(135deg, var(--accent), #15171c 85%);
    color:rgba(255,255,255,.65); font-size:18px;
  }

  #meta{ flex:1; min-width:0; }
  #card[data-style="minimal"] #meta{ border-left:3px solid var(--accent); padding-left:14px; }
  #title, #artist{
    opacity:0; transform:translateY(4px);
    transition:opacity .3s ease, transform .3s ease;
    white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:100%;
  }
  #title.show, #artist.show{ opacity:1; transform:translateY(0); }
  #title{ color:#fff; font-size:15px; font-weight:600; }
  #artist{ color:rgba(255,255,255,.65); font-size:12.5px; margin-top:2px; transition-delay:.05s; }
  #card[data-style="badge"] #title{ font-size:13.5px; }
  #card[data-style="badge"] #artist{ font-size:11px; }

  #eq{ display:flex; align-items:flex-end; gap:3px; height:13px; margin-top:6px; }
  #card[data-style="badge"] #eq{ display:none; }
  #eq span{ width:3px; background:var(--accent); border-radius:2px; animation:bounce 1s ease-in-out infinite; }
  #eq span:nth-child(1){ animation-delay:-.9s; }
  #eq span:nth-child(2){ animation-delay:-.45s; }
  #eq span:nth-child(3){ animation-delay:-.2s; }
  #eq.paused span{ animation-play-state:paused; height:25% !important; }
  @keyframes bounce{ 0%,100%{ height:20%; } 50%{ height:100%; } }
</style>
</head>
<body>
<div id="card" data-style="card">
  <div id="artwrap">
    <div id="artFallback">&#9834;</div>
    <img id="art" src="" alt="">
  </div>
  <div id="meta">
    <div id="title">&nbsp;</div>
    <div id="artist">&nbsp;</div>
    <div id="eq"><span></span><span></span><span></span></div>
  </div>
</div>
<script>
  let lastKey = null;
  let lastCoverVer = 0;
  const card = document.getElementById('card');
  const art = document.getElementById('art');
  const titleEl = document.getElementById('title');
  const artistEl = document.getElementById('artist');
  const eq = document.getElementById('eq');

  function swap(d){
    titleEl.textContent = d.title;
    artistEl.textContent = d.artist;
    if(d.cover_ver && d.cover_ver !== lastCoverVer){
      lastCoverVer = d.cover_ver;
      art.src = '/api/cover.jpg?v=' + d.cover_ver;
    }
    eq.classList.toggle('paused', !d.playing);
    card.classList.add('show');
    requestAnimationFrame(() => {
      titleEl.classList.add('show');
      artistEl.classList.add('show');
      art.classList.toggle('show', !!d.cover_ver);
    });
  }

  async function poll(){
    try{
      const r = await fetch('/api/nowplaying', {cache:'no-store'});
      const d = await r.json();
      card.dataset.style = d.style || 'card';
      const hasSong = d.running && d.title;
      const key = hasSong ? (d.artist + '|' + d.title) : null;

      if(!hasSong){
        card.classList.remove('show');
        lastKey = null;
      } else if(key !== lastKey){
        const wasShown = card.classList.contains('show');
        lastKey = key;
        titleEl.classList.remove('show');
        artistEl.classList.remove('show');
        art.classList.remove('show');
        setTimeout(() => swap(d), wasShown ? 220 : 0);
      } else {
        eq.classList.toggle('paused', !d.playing);
      }
    }catch(e){ /* overlay server not reachable yet */ }
  }
  poll();
  setInterval(poll, 1000);
</script>
</body>
</html>
"""


class _OverlayHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path in ("/", "/overlay"):
            self._html()
        elif path == "/api/nowplaying":
            self._json()
        elif path == "/api/cover.jpg":
            self._cover()
        else:
            self.send_response(404)
            self.end_headers()

    def _html(self):
        accent = T.get("accent", "#AEC6FF")
        body = OVERLAY_HTML.replace("__ACCENT__", accent).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        self.wfile.write(body)

    def _json(self):
        with _overlay_lock:
            data = dict(_overlay_state)
        data["style"] = settings.get("overlay_style", "Card").lower()
        body = json.dumps(data).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _cover(self):
        with _overlay_lock:
            data = _overlay_cover
        if not data:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/jpeg")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class OverlayServer:
    """Local HTTP server for the OBS Now-Playing overlay (Browser Source)."""

    def __init__(self):
        self.httpd = None

    def start(self, port):
        self.stop()
        try:
            self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", port), _OverlayHandler)
        except OSError:
            self.httpd = None
            return False
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        return True

    def stop(self):
        if self.httpd:
            try:
                self.httpd.shutdown()
                self.httpd.server_close()
            except Exception:
                pass
            self.httpd = None


overlay_server = OverlayServer()


# =============================
# DISCORD RICH PRESENCE
# =============================
class DiscordRPC:
    """Optional: Discord Rich Presence via local IPC (needs the Discord desktop app running
    and your own free Application ID from https://discord.com/developers/applications)."""

    def __init__(self):
        self.rpc = None
        self.connected = False
        self.lock = threading.Lock()
        self._last_sig = None

    def connect(self, client_id):
        with self.lock:
            self._disconnect_locked()
            if not HAS_DISCORD:
                return False, "pypresence not installed"
            if not client_id:
                return False, "No Application ID"
            try:
                self.rpc = _DiscordPresence(client_id)
                self.rpc.connect()
                self.connected = True
                return True, "Connected"
            except Exception as e:
                self.rpc = None
                self.connected = False
                return False, str(e) or "Couldn't connect (Discord running?)"

    def _disconnect_locked(self):
        if self.rpc:
            try:
                self.rpc.clear()
            except Exception:
                pass
            try:
                self.rpc.close()
            except Exception:
                pass
        self.rpc = None
        self.connected = False
        self._last_sig = None

    def disconnect(self):
        with self.lock:
            self._disconnect_locked()

    def clear(self):
        with self.lock:
            if self.rpc and self.connected and self._last_sig is not None:
                try:
                    self.rpc.clear()
                except Exception:
                    self.connected = False
            self._last_sig = None

    def update(self, title, artist, playing, position, duration, track_url):
        sig = (title, artist, playing, track_url, round(duration) if duration else None)
        with self.lock:
            if not self.rpc or not self.connected or sig == self._last_sig:
                return
            self._last_sig = sig
            kwargs = dict(
                details=short(title, 128) if title else "Browsing",
                state=f"by {short(artist, 120)}" if artist else None,
                large_image="logo", large_text=APP_NAME,
                small_image="play" if playing else "pause",
                small_text="Playing" if playing else "Paused",
            )
            if duration and position is not None and playing:
                now = time.time()
                kwargs["start"] = int(now - position)
                kwargs["end"] = int(now - position + duration)
            if track_url:
                kwargs["buttons"] = [{"label": "Play on Spotify", "url": track_url}]
            try:
                self.rpc.update(**kwargs)
            except Exception:
                self.connected = False


discord_rpc = DiscordRPC()


# =============================
# START WITH WINDOWS
# =============================
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
RUN_NAME = "SpotifyController"


def launch_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --tray'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.abspath(__file__)}" --tray'


def get_autostart():
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as k:
            winreg.QueryValueEx(k, RUN_NAME)
        return True
    except Exception:
        return False


def set_autostart(on):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if on:
            winreg.SetValueEx(k, RUN_NAME, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(k, RUN_NAME)
            except FileNotFoundError:
                pass


# =============================
# IMAGE HELPERS
# =============================
def pil_font(size, bold=False):
    win = os.environ.get("WINDIR", "C:/Windows")
    names = ["segoeuib.ttf" if bold else "segoeui.ttf",
             "DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf"]
    for n in names:
        for path in (os.path.join(win, "Fonts", n), n):
            try:
                return ImageFont.truetype(path, int(size))
            except Exception:
                continue
    return ImageFont.load_default()


def short(s, n):
    return s if len(s) <= n else s[: n - 1] + "…"


def gradient_cover(seed, size=256, colors=None):
    h = int(hashlib.md5(seed.encode("utf-8")).hexdigest(), 16)
    if colors:
        c1, c2 = colors
    else:
        c1 = tuple(int(v * 255) for v in colorsys.hsv_to_rgb((h % 360) / 360, 0.60, 0.95))
        c2 = tuple(int(v * 255) for v in colorsys.hsv_to_rgb(((h >> 12) % 360) / 360, 0.75, 0.35))
    n = 48
    g = Image.new("RGB", (n, n))
    px = g.load()
    for y in range(n):
        for x in range(n):
            t = (x + y) / (2 * (n - 1))
            px[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    img = g.resize((size, size), Image.BICUBIC).convert("RGBA")
    ov = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    r = size * (0.25 + ((h >> 24) % 30) / 100)
    cx = size * (0.2 + ((h >> 30) % 60) / 100)
    cy = size * (0.2 + ((h >> 36) % 60) / 100)
    ImageDraw.Draw(ov).ellipse((cx - r, cy - r, cx + r, cy + r), fill=(255, 255, 255, 34))
    return Image.alpha_composite(img, ov).convert("RGB")


def round_image(img, px, frac=0.12):
    img = ImageOps.fit(img.convert("RGB"), (px, px), Image.LANCZOS)
    ss = 4
    m = Image.new("L", (px * ss, px * ss), 0)
    ImageDraw.Draw(m).rounded_rectangle((0, 0, px * ss - 1, px * ss - 1),
                                        radius=int(px * ss * frac), fill=255)
    m = m.resize((px, px), Image.LANCZOS)
    out = img.convert("RGBA")
    out.putalpha(m)
    return out


def rr_layer(w, h, r, fill=None, outline=None, ow=1, ss=3):
    """Anti-aliased RGBA rounded rectangle (supersampled)."""
    W, H = max(1, int(w)), max(1, int(h))
    big = Image.new("RGBA", (W * ss, H * ss), (0, 0, 0, 0))
    d = ImageDraw.Draw(big)
    box = (0, 0, W * ss - 1, H * ss - 1)
    if fill is not None:
        d.rounded_rectangle(box, radius=int(r * ss), fill=fill)
    if outline is not None:
        d.rounded_rectangle(box, radius=int(r * ss), outline=outline, width=max(1, int(ow * ss)))
    return big.resize((W, H), Image.LANCZOS)


_icon_cache = {}


def make_app_icon(size=256):
    """Load the tray icon from the shared app artwork."""
    if size in _icon_cache:
        return _icon_cache[size].copy()
    with Image.open(ICON_PNG_PATH) as source:
        frame = source.convert("RGBA")
    img = frame if frame.size == (size, size) else frame.resize((size, size), Image.LANCZOS)
    _icon_cache[size] = img
    return img.copy()


def ensure_icon_file():
    """Create the shared window and tray icon from the app artwork if needed."""
    try:
        if os.path.exists(ICO_PATH) and os.path.getmtime(ICO_PATH) >= os.path.getmtime(ICON_PNG_PATH):
            return
    except OSError:
        if os.path.exists(ICO_PATH):
            return
    with Image.open(ICON_PNG_PATH) as source:
        source.convert("RGBA").save(
            ICO_PATH, format="ICO",
            sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def make_window_bg(w, h, scale):
    """Dark neutral canvas with subtle blue-grey corner glows."""
    W, H = int(w * scale), int(h * scale)
    gw, gh = 196, 124
    bg = hex2rgb(T["bg"])
    g1, g2 = T["glow"], T["glow2"]
    small = Image.new("RGB", (gw, gh))
    px = small.load()
    for y in range(gh):
        v = y / (gh - 1)
        for x in range(gw):
            u = x / (gw - 1)
            a = math.exp(-((u / 0.48) ** 2 + (v / 0.70) ** 2) * 2.0)
            b = math.exp(-(((1 - u) / 0.48) ** 2 + ((1 - v) / 0.70) ** 2) * 2.0)
            out = []
            for i in range(3):
                val = bg[i] + (g1[i] - bg[i]) * 0.16 * a + (g2[i] - bg[i]) * 0.08 * b
                out.append(max(0, min(255, int(val))))
            px[x, y] = tuple(out)
    img = small.resize((W, H), Image.BICUBIC)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((0, 0, W - 1, H - 1), radius=int(16 * scale),
                        outline=hex2rgb(T["line"]), width=max(1, int(scale)))
    icon = make_app_icon(int(34 * scale))
    img.paste(icon, (int(28 * scale), int(18 * scale)), icon)
    d.text((int(72 * scale), int(18 * scale)), APP_NAME, font=pil_font(15 * scale, True),
           fill=hex2rgb(T["text"]))
    d.text((int(72 * scale), int(40 * scale)), "HOTKEYS & NOW PLAYING",
           font=pil_font(9 * scale, True), fill=hex2rgb(T["accent"]))
    return img


def make_hero(base, w, hero_h, cover_px, scale, style="Spotify"):
    W, H = int(w * scale), int(hero_h * scale)
    if style == "Clean":
        bg = Image.new("RGB", (W, H), hex2rgb(T["panel"]))
        accent = Image.new("RGB", (W, H), hex2rgb(T["dim"]))
        grad = Image.linear_gradient("L").rotate(90, expand=True).resize((W, H), Image.BILINEAR)
        bg = Image.composite(accent, bg, grad.point(lambda value: int(value * 0.32)))
        cs, cy = int(166 * scale), int(66 * scale)
    else:
        bg = ImageOps.fit(base.convert("RGB"), (W, H), Image.LANCZOS)
        small = bg.resize((max(1, W // 4), max(1, H // 4)), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(24 if style == "Spotlight" else 18))
        bg = small.resize((W, H), Image.BICUBIC)
        bg = ImageEnhance.Brightness(bg).enhance(0.66 if style == "Spotlight" else 0.78)
        bg = ImageEnhance.Color(bg).enhance(1.05)
        bg = Image.blend(bg, Image.new("RGB", (W, H), hex2rgb(T["accent"])), 0.055)
        grad = Image.linear_gradient("L").point(lambda v: int(255 * ((v / 255.0) ** 1.6)))
        grad = grad.resize((W, H), Image.BILINEAR)
        bg = Image.composite(Image.new("RGB", (W, H), hex2rgb(T["panel"])), bg, grad)
        cs = int((248 if style == "Spotlight" else cover_px) * scale)
        cy = int((18 if style == "Spotlight" else 28) * scale)
    cx = (W - cs) // 2
    shadow = Image.new("L", (W, H), 0)
    off = int(10 * scale)
    ImageDraw.Draw(shadow).rounded_rectangle((cx, cy + off, cx + cs, cy + cs + off),
                                             radius=int(cs * 0.07), fill=170)
    shadow = shadow.filter(ImageFilter.GaussianBlur(16 * scale))
    bg.paste(Image.new("RGB", (W, H), (0, 0, 0)), (0, 0), shadow)
    cover = round_image(base, cs, 0.07)
    bg.paste(cover, (cx, cy), cover)
    return bg


def card_image(bg_img, ax, ay, w, h, scale, hero=None, radius=16):
    W, H = int(w * scale), int(h * scale)
    x0, y0 = int(ax * scale), int(ay * scale)
    base = bg_img.crop((x0, y0, x0 + W, y0 + H)).convert("RGB")
    fill = Image.new("RGB", (W, H), hex2rgb(T["panel"]))
    if hero is not None:
        fill.paste(hero, (0, 0))
    ss = 3

    def rr(inset):
        m = Image.new("L", (W * ss, H * ss), 0)
        ImageDraw.Draw(m).rounded_rectangle(
            (inset * ss, inset * ss, W * ss - 1 - inset * ss, H * ss - 1 - inset * ss),
            radius=max(1, int((radius * scale - inset) * ss)), fill=255)
        return m.resize((W, H), Image.LANCZOS)

    outer, inner = rr(0), rr(max(1, int(round(scale))))
    base.paste(fill, (0, 0), outer)
    base.paste(Image.new("RGB", (W, H), hex2rgb(T["line"])), (0, 0), ImageChops.subtract(outer, inner))
    return base


def icon_minus(size=64):
    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    ImageDraw.Draw(img).line((S * 0.26, S * 0.5, S * 0.74, S * 0.5),
                             fill=hex2rgb(T["text"]) + (255,), width=int(S * 0.085))
    return img.resize((size, size), Image.LANCZOS)


def icon_x(angle, size=64):
    S = size * 3
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = S * 0.28
    col = hex2rgb(T["text"]) + (255,)
    wdt = int(S * 0.085)
    d.line((m, m, S - m, S - m), fill=col, width=wdt)
    d.line((S - m, m, m, S - m), fill=col, width=wdt)
    img = img.rotate(angle, resample=Image.BICUBIC)
    return img.resize((size, size), Image.LANCZOS)


def swatch_image(key, selected, px=120):
    th = THEMES[key]
    S = px * 3
    c1 = hex2rgb(th["accent_h"])
    c2 = tuple(int(v * 0.45) for v in hex2rgb(th["accent"]))
    g = Image.new("RGB", (32, 32))
    p = g.load()
    for y in range(32):
        for x in range(32):
            t = (x + y) / 62
            p[x, y] = tuple(int(c1[i] + (c2[i] - c1[i]) * t) for i in range(3))
    g = g.resize((S, S), Image.BICUBIC)
    pad = int(S * (0.17 if selected else 0.07))
    m = Image.new("L", (S, S), 0)
    ImageDraw.Draw(m).ellipse((pad, pad, S - pad, S - pad), fill=255)
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    glow_mask = Image.new("L", (S, S), 0)
    gd = ImageDraw.Draw(glow_mask)
    glow_pad = int(S * (0.04 if selected else 0.12))
    gd.ellipse((glow_pad, glow_pad, S - glow_pad, S - glow_pad),
               fill=105 if selected else 32)
    glow_mask = glow_mask.filter(ImageFilter.GaussianBlur(S * (0.08 if selected else 0.06)))
    glow_color = Image.new("RGBA", (S, S), c1 + (0,))
    glow_color.putalpha(glow_mask)
    img.alpha_composite(glow_color)
    img.paste(g, (0, 0), m)
    d = ImageDraw.Draw(img)
    if selected:
        d.ellipse((int(S * 0.04), int(S * 0.04), int(S * 0.96), int(S * 0.96)),
                  outline=c1 + (255,), width=max(2, int(S * 0.035)))
        d.line([(S * .37, S * .52), (S * .46, S * .61), (S * .64, S * .40)],
               fill=(255, 255, 255, 255), width=max(3, int(S * 0.07)), joint="curve")
    return img.resize((px, px), Image.LANCZOS)


# =============================
# UI
# =============================
WIN_W, WIN_H = 980, 620
PX, PY, PW, PH = 22, 84, 936, 514
PAGES = ["player", "keys", "settings"]
PAGE_LABELS = {"player": "Home", "keys": "Hotkeys", "settings": "Settings"}
SECTIONS = ["general", "look", "stream", "discord", "spotify", "about"]
SECTION_LABELS = {"general": "General", "look": "Look", "stream": "Stream", "discord": "Discord",
                  "spotify": "Spotify", "about": "About"}
SPIN_FRAMES = 10
TRANSITION_S = 0.22   # page crossfade (nur wenn FADES = True)
SECTION_S = 0.16      # settings section crossfade (nur wenn FADES = True)
LOOK_ORDER = ("harbor", "nightfall", "moonlit", "steel")
NOW_PLAYING_STYLES = ("Spotify", "Spotlight", "Clean")
OVERLAY_STYLES = ("Card", "Minimal", "Badge")


class PillNav:
    """Image-rendered navigation with a highlight pill that glides to the selected item.
    Used for the top tabs (horizontal) and the settings sidebar (vertical)."""

    def __init__(self, app, parent, base, labels, rects, size, vertical, on_select):
        self.app, self.labels, self.rects, self.size = app, labels, rects, size
        self.vertical, self.on_select = vertical, on_select
        self.S = app.scale
        self.base = base.convert("RGB")
        self.font = pil_font(13 * self.S, True)
        self.g = int(16 * self.S)
        self.sprite = self._make_sprite(int(rects[0][2] * self.S), int(rects[0][3] * self.S))
        self.pos, self.target, self.hover = 0.0, 0, None
        self._job, self._from, self._t0, self._dur = None, 0.0, 0.0, 0.3
        self._ci = None
        self.label = ctk.CTkLabel(parent, text="", width=size[0], height=size[1],
                                  corner_radius=0, fg_color=T["bg"])
        self.label.bind("<Button-1>", self._click, add="+")
        self.label.bind("<Motion>", self._motion, add="+")
        self.label.bind("<Leave>", self._leave, add="+")
        for part in ("_label", "_canvas"):
            try:
                getattr(self.label, part).configure(cursor="hand2")
            except Exception:
                pass
        self.render()

    def _make_sprite(self, pw, ph):
        S, g = self.S, self.g
        acc = hex2rgb(T["accent"])
        W, H = pw + 2 * g, ph + 2 * g
        m = Image.new("L", (W, H), 0)
        m.paste(rr_layer(pw, ph, 12 * S, fill=(255, 255, 255, 110)).split()[3], (g, g))
        m = m.filter(ImageFilter.GaussianBlur(6 * S))
        sprite = Image.new("RGBA", (W, H), acc + (0,))
        sprite.putalpha(m)
        body = rr_layer(pw, ph, 12 * S, fill=hex2rgb(T["sel"]) + (255,),
                        outline=hex2rgb(T["accent_h"]) + (120,), ow=1.2 * S)
        sprite.alpha_composite(body, (g, g))
        if self.vertical:
            bh = int(ph * 0.5)
            bar = rr_layer(3 * S, bh, 1.5 * S, fill=acc + (255,))
            sprite.alpha_composite(bar, (g + int(9 * S), g + (ph - bh) // 2))
        return sprite

    # ----- rendering -----
    def render(self):
        S = self.S
        img = self.base.copy()
        n = len(self.rects)
        p = min(max(self.pos, 0.0), n - 1)
        i0 = int(p)
        i1 = min(i0 + 1, n - 1)
        f = p - i0
        x = self.rects[i0][0] + (self.rects[i1][0] - self.rects[i0][0]) * f
        y = self.rects[i0][1] + (self.rects[i1][1] - self.rects[i0][1]) * f
        img.paste(self.sprite, (int(x * S) - self.g, int(y * S) - self.g), self.sprite)
        d = ImageDraw.Draw(img)
        muted, text = hex2rgb(T["muted"]), hex2rgb(T["text"])
        for i, (label, (rx, ry, rw, rh)) in enumerate(zip(self.labels, self.rects)):
            w = max(0.0, 1.0 - abs(p - i))
            if i == self.hover and w < 0.45:
                w = 0.45
            col = mix(muted, text, w)
            cy = int((ry + rh / 2) * S)
            try:
                if self.vertical:
                    d.text((int((rx + 24) * S), cy), label, font=self.font, fill=col, anchor="lm")
                else:
                    d.text((int((rx + rw / 2) * S), cy), label, font=self.font, fill=col, anchor="mm")
            except (TypeError, ValueError, OSError):
                tw = d.textlength(label, font=self.font)
                tx = int((rx + 24) * S) if self.vertical else int((rx + rw / 2) * S - tw / 2)
                d.text((tx, cy - int(7 * S)), label, font=self.font, fill=col)
        ci = ctk.CTkImage(img, img, size=self.size)
        try:
            self.label.configure(image=ci)
        except Exception:
            self._job = None
            return
        self._ci = ci

    # ----- interaction -----
    def _index_at(self, e):
        lx = (e.x_root - self.label.winfo_rootx()) / self.S
        ly = (e.y_root - self.label.winfo_rooty()) / self.S
        for i, (x, y, w, h) in enumerate(self.rects):
            if x <= lx < x + w and y <= ly < y + h:
                return i
        return None

    def _click(self, e):
        i = self._index_at(e)
        if i is not None and self.on_select:
            self.on_select(i)

    def _motion(self, e):
        i = self._index_at(e)
        if i != self.hover:
            self.hover = i
            if self._job is None:
                self.render()

    def _leave(self, e):
        px = self.label.winfo_pointerx() - self.label.winfo_rootx()
        py = self.label.winfo_pointery() - self.label.winfo_rooty()
        if 0 <= px < self.label.winfo_width() and 0 <= py < self.label.winfo_height():
            return
        if self.hover is not None:
            self.hover = None
            if self._job is None:
                self.render()

    # ----- animation -----
    def select(self, i, animate=True):
        self.target = i
        if not animate:
            self.pos = float(i)
            self.render()
            return
        self._from, self._t0 = self.pos, time.perf_counter()
        self._dur = 0.22 + 0.06 * abs(i - self.pos)
        if self._job is None:
            self._tick()

    def _tick(self):
        t = (time.perf_counter() - self._t0) / self._dur
        if t >= 1:
            self.pos = float(self.target)
            self._job = None
        else:
            e = 1 - (1 - t) ** 3
            self.pos = self._from + (self.target - self._from) * e
            try:
                self._job = self.label.after(8, self._tick)
            except Exception:
                self._job = None
        self.render()

    def stop(self):
        if self._job:
            try:
                self.label.after_cancel(self._job)
            except Exception:
                pass
            self._job = None


class HeroCard:
    """Card with the blurred cover as backdrop + sharp cover on top."""

    def __init__(self, app, page, x, y, w, h, hero_h, cover, controls):
        self.app, self.x, self.y, self.w, self.h = app, x, y, w, h
        self.hero_h, self.cover_sz = hero_h, cover
        self._sig = None
        panel = T["panel"]
        self.card = ctk.CTkLabel(page, text="", width=w, height=h, corner_radius=0, fg_color=panel)
        self.card.place(x=x, y=y)
        big = w > 400
        self.max_title = 34 if big else 24
        self.title = ctk.CTkLabel(self.card, text="", font=("Segoe UI", 24 if big else 20, "bold"),
                                  text_color=T["text"], fg_color=panel, bg_color=panel)
        self.title.place(relx=0.5, y=hero_h + 4, anchor="n")
        self.artist = ctk.CTkLabel(self.card, text="", font=("Segoe UI", 14),
                                   text_color=T["muted"], fg_color=panel, bg_color=panel)
        self.artist.place(relx=0.5, y=hero_h + 40, anchor="n")
        self.pill = ctk.CTkLabel(self.card, text="", font=("Segoe UI", 11, "bold"), corner_radius=10,
                                 height=24, width=110, fg_color=T["soft"], text_color=T["muted"],
                                 bg_color=panel)
        self.pill.place(relx=0.5, y=hero_h + 72, anchor="n")
        self.play_btn = None
        self.progress = None
        self.elapsed = None
        self.duration = None
        if controls:
            self._controls()

    def _controls(self):
        panel = T["panel"]
        cyc = self.hero_h + 158
        primary_size = 52
        control_gap = 32
        spec = (
            ("prev", "⏮", 44, False),
            ("play_pause", "▶", primary_size, True),
            ("next", "⏭", 44, False),
        )
        controls_width = sum(size for _, _, size, _ in spec) + control_gap * (len(spec) - 1)
        x = (self.w - controls_width) / 2
        for action, glyph, size, primary in spec:
            font = ("Segoe UI Symbol", 20 if primary else 16)
            b = ctk.CTkButton(
                self.card, text=glyph, width=size, height=size, corner_radius=size // 2, font=font,
                fg_color=T["accent"] if primary else T["soft"],
                hover_color=T["accent_h"] if primary else T["soft_h"],
                text_color=T["on_accent"] if primary else T["text"], bg_color=panel,
                command=lambda a=action: self.app.do_action(a))
            b.place(x=x, y=cyc - size / 2)
            if action == "play_pause":
                self.play_btn = b
            x += size + control_gap
        self.elapsed = ctk.CTkLabel(
            self.card, text="--:--", font=("Segoe UI", 10), text_color=T["muted"],
            fg_color=panel, bg_color=panel)
        self.elapsed.place(x=38, y=self.hero_h + 98, anchor="nw")
        self.duration = ctk.CTkLabel(
            self.card, text="--:--", font=("Segoe UI", 10), text_color=T["muted"],
            fg_color=panel, bg_color=panel)
        self.duration.place(x=self.w - 38, y=self.hero_h + 98, anchor="ne")
        self.progress = ctk.CTkProgressBar(
            self.card, width=self.w - 76, height=6, corner_radius=3,
            fg_color=T["soft"], progress_color=T["accent"], bg_color=panel)
        self.progress.set(0)
        self.progress.place(x=38, y=self.hero_h + 120)

    def update(self, key, cover, playing, running):
        app = self.app
        if key:
            artist, title = key
            seed = f"{artist}{title}"
        else:
            seed = "idle"
            title = "Nothing playing" if running else "Spotify isn't running"
            artist = "Play something in Spotify" if running else "Open Spotify to get started"
        self.title.configure(text=short(title, self.max_title))
        self.artist.configure(text=short(artist, 48))

        style = (settings.get("now_playing_style", "Spotify")
                 if self.play_btn is not None else "Spotify")
        sig = (key, id(cover) if cover is not None else 0, T["accent"], style)
        if sig != self._sig:
            self._sig = sig
            if cover is not None:
                base = cover
            elif key:
                base = gradient_cover(seed)
            else:
                base = gradient_cover("idle", colors=(hex2rgb(T["accent"]), hex2rgb(T["dim"])))
            hero = make_hero(base, self.w, self.hero_h, self.cover_sz, app.scale, style)
            img = card_image(app.bg_pil, PX + self.x, PY + self.y, self.w, self.h, app.scale, hero)
            self.card.configure(image=ctk.CTkImage(img, img, size=(self.w, self.h)))

        self.set_status(playing, running)
        self.set_progress(None, None)

    @staticmethod
    def _time_text(seconds):
        total = max(0, int(seconds))
        return f"{total // 60}:{total % 60:02d}"

    def set_progress(self, position, duration):
        if self.progress is None:
            return
        if duration is None or duration <= 0 or position is None:
            self.progress.set(0)
            self.elapsed.configure(text="--:--")
            self.duration.configure(text="--:--")
            return
        current = min(max(position, 0), duration)
        self.progress.set(current / duration)
        self.elapsed.configure(text=self._time_text(current))
        self.duration.configure(text=self._time_text(duration))

    def set_status(self, playing, running):
        """Leichtgewichtig: nur Pill + Play/Pause-Button (kein Bild-Rebuild)."""
        if not running:
            self.pill.configure(text="OFFLINE", fg_color=T["soft"], text_color=T["muted"])
        elif playing:
            self.pill.configure(text="●  PLAYING", fg_color=T["dim"], text_color=T["accent"])
        else:
            self.pill.configure(text="PAUSED", fg_color=T["soft"], text_color=T["muted"])
        if self.play_btn is not None:
            self.play_btn.configure(text="⏸" if playing else "▶")


class App:
    def __init__(self, start_hidden=False):
        ctk.set_appearance_mode("dark")
        self.root = ctk.CTk(fg_color=T["bg"])
        self.root.title(APP_NAME)
        self.scale = self._scale()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        x = (sw - int(WIN_W * self.scale)) // 2
        y = (sh - int(WIN_H * self.scale)) // 2
        self.root.geometry(f"{WIN_W}x{WIN_H}+{x}+{y}")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", bool(settings["always_on_top"]))
        self.root.update_idletasks()
        self._round_window()

        self.covers = {}
        self.smtc_done = set()
        self.history, self.ids = load_history()
        self.hist_ver = 0
        self.cover_ver = 0
        self._cover_seen = 0
        self._last_list = 0.0
        self.current = None
        self.playing = False
        self.running = False
        self.track_position = None
        self.track_duration = None
        self._media_position = None
        self._media_position_at = None
        self._last_media_position = None
        self.last_state = None
        self.page_name = "player"
        self.section = "general"
        self.animating = False
        self._pending = None
        self._fades = {}
        self.version = 0
        self.ui = []
        self.captions = {}
        self.key_buttons = {}
        self.row_cache = {}
        self._x_hover = False
        self._x_p = 0.0
        self._x_job = None
        self._notice_job = None
        self._opt_until = 0.0      # bis dahin gilt der optimistische Play-Status
        self._last_playing = False
        self.cur_glyph = None      # Glyph-Label der aktuellen Zeile in der Liste
        self.ui_q = queue.Queue()
        self._overlay_cover_id = 0
        self._discord_connecting = False
        self._discord_retry_at = 0.0
        self._discord_track_ids = {}
        self._discord_resolving = set()

        self.fetcher = CoverFetcher()
        self.build_ui()

        self.watcher = MediaWatcher()
        self.watcher.start()
        self.fetcher.start()
        for i, k in enumerate(self.history[:12]):
            self.fetcher.request(k, 2 + i)
        if start_hidden:
            self.root.withdraw()
        self.root.after(80, lambda: self._taskbar_fix(not start_hidden))
        self.root.after(400, self._set_icon)
        self.tick()
        self._drain()

    # ---------- thread bridge ----------
    def post(self, fn):
        self.ui_q.put(fn)

    def _drain(self):
        try:
            while True:
                fn = self.ui_q.get_nowait()
                try:
                    fn()
                except Exception:
                    pass
        except queue.Empty:
            pass
        self.root.after(40, self._drain)

    def bump(self):
        self.version += 1

    # ---------- window helpers ----------
    def _scale(self):
        try:
            return float(self.root._get_window_scaling())
        except Exception:
            return 1.0

    def _hwnd(self):
        wid = self.root.winfo_id()
        return _u.GetParent(wid) or wid

    def _round_window(self):
        try:
            hwnd = self._hwnd()

            class Margins(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_int),
                    ("right", ctypes.c_int),
                    ("top", ctypes.c_int),
                    ("bottom", ctypes.c_int),
                ]

            dwm = ctypes.windll.dwmapi
            dwm.DwmSetWindowAttribute.argtypes = [
                wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
            dwm.DwmSetWindowAttribute.restype = ctypes.c_long
            dwm.DwmExtendFrameIntoClientArea.argtypes = [
                wintypes.HWND, ctypes.POINTER(Margins)]
            dwm.DwmExtendFrameIntoClientArea.restype = ctypes.c_long

            corner_preference = ctypes.c_int(2)  # DWMWCP_ROUND
            result = dwm.DwmSetWindowAttribute(
                hwnd, 33, ctypes.byref(corner_preference), ctypes.sizeof(corner_preference))
            if result == 0:
                margins = Margins(1, 1, 1, 1)
                dwm.DwmExtendFrameIntoClientArea(hwnd, ctypes.byref(margins))
                return

            w, h = self.root.winfo_width(), self.root.winfo_height()
            r = int(16 * self.scale * 2)
            region = ctypes.windll.gdi32.CreateRoundRectRgn(0, 0, w + 1, h + 1, r, r)
            ctypes.windll.user32.SetWindowRgn(hwnd, region, True)
        except Exception:
            pass

    def _taskbar_fix(self, show):
        """Borderless windows get no taskbar button by default - add one."""
        try:
            hwnd = self._hwnd()
            ex = _u.GetWindowLongW(hwnd, -20)
            ex = (ex & ~0x00000080) | 0x00040000          # no TOOLWINDOW, APPWINDOW
            _u.SetWindowLongW(hwnd, -20, ex)
            st = _u.GetWindowLongW(hwnd, -16)
            _u.SetWindowLongW(hwnd, -16, st | 0x00020000 | 0x00080000)  # MINIMIZEBOX | SYSMENU
            self.root.withdraw()
            if show:
                self.root.after(40, self.root.deiconify)
        except Exception:
            pass

    def _set_icon(self):
        try:
            if os.path.exists(ICO_PATH):
                self.root.iconbitmap(ICO_PATH)
        except Exception:
            pass

    def start_move(self, e):
        self._dx, self._dy = e.x_root - self.root.winfo_x(), e.y_root - self.root.winfo_y()

    def do_move(self, e):
        self.root.geometry(f"+{e.x_root - self._dx}+{e.y_root - self._dy}")

    def sample(self, x, y):
        px = min(max(int(x * self.scale), 0), self.bg_pil.width - 1)
        py = min(max(int(y * self.scale), 0), self.bg_pil.height - 1)
        return rgb2hex(self.bg_pil.getpixel((px, py)))

    # ---------- build ----------
    def build_ui(self):
        self.ui = []
        self.captions = {}
        self.key_buttons = {}
        self.bg_pil = make_window_bg(WIN_W, WIN_H, self.scale)
        bg = ctk.CTkImage(self.bg_pil, self.bg_pil, size=(WIN_W, WIN_H))
        self.bg_label = ctk.CTkLabel(self.root, text="", image=bg, width=WIN_W, height=WIN_H,
                                     corner_radius=0, fg_color=T["bg"])
        self.bg_label.place(x=0, y=0)
        self.bg_label.bind("<ButtonPress-1>", self.start_move)
        self.bg_label.bind("<B1-Motion>", self.do_move)
        self.ui.append(self.bg_label)

        self._build_topbar()

        self.pages = {}
        for name in PAGES:
            self.pages[name] = self._new_page()
        self._build_player(self.pages["player"])
        self._build_keys(self.pages["keys"])
        self._build_settings(self.pages["settings"])
        for name, page in self.pages.items():
            if name == self.page_name:
                page.place(x=PX, y=PY)
            else:
                page.place_forget()
        self.ui.extend(self.pages.values())
        self.refresh_keys()
        self.last_state = None
        self.apply_state()

    def rebuild(self):
        for k in list(getattr(self, "_fades", {})):
            self._fade_cancel(k)
        self.animating = False
        self._pending = None
        for nav in (getattr(self, "tabs", None), getattr(self, "side_nav", None)):
            if nav is not None:
                nav.stop()
        for w in self.ui:
            try:
                w.destroy()
            except Exception:
                pass
        self.row_cache.clear()
        self.cur_glyph = None
        self.root.configure(fg_color=T["bg"])
        self.build_ui()

    def _new_page(self):
        S = self.scale
        x0, y0 = int(PX * S), int(PY * S)
        img = self.bg_pil.crop((x0, y0, x0 + int(PW * S), y0 + int(PH * S))).convert("RGB")
        return ctk.CTkLabel(self.root, text="", width=PW, height=PH, corner_radius=0,
                            fg_color=T["bg"], image=ctk.CTkImage(img, img, size=(PW, PH)))

    def make_card(self, page, x, y, w, h):
        img = card_image(self.bg_pil, PX + x, PY + y, w, h, self.scale)
        card = ctk.CTkLabel(page, text="", width=w, height=h, corner_radius=0, fg_color=T["panel"],
                            image=ctk.CTkImage(img, img, size=(w, h)))
        card.place(x=x, y=y)
        card.pil_img = img
        return card

    def _build_topbar(self):
        S = self.scale
        bw, bh = 328, 46
        bx, by = (WIN_W - bw) // 2, 17
        x0, y0 = int(bx * S), int(by * S)
        crop = self.bg_pil.crop((x0, y0, x0 + int(bw * S), y0 + int(bh * S))).convert("RGBA")
        crop.alpha_composite(rr_layer(int(bw * S), int(bh * S), 17 * S,
                                      fill=hex2rgb(T["panel"]) + (228,),
                                      outline=hex2rgb(T["line"]) + (255,), ow=max(1.0, S)))
        rects = [(5 + i * 106, 5, 106, 36) for i in range(len(PAGES))]
        self.tabs = PillNav(self, self.root, crop, [PAGE_LABELS[p] for p in PAGES], rects,
                            (bw, bh), False, lambda i: self.go(PAGES[i]))
        self.tabs.label.place(x=bx, y=by)
        self.tabs.select(PAGES.index(self.page_name), animate=False)
        self.ui.append(self.tabs.label)

        self.icon_min = ctk.CTkImage(icon_minus(), icon_minus(), size=(16, 16))
        self.spin_imgs = []
        for i in range(SPIN_FRAMES):
            t = i / (SPIN_FRAMES - 1)
            ang = 90 * (1 - (1 - t) ** 2)
            im = icon_x(ang)
            self.spin_imgs.append(ctk.CTkImage(im, im, size=(16, 16)))

        c_min, c_x = self.sample(892, 38), self.sample(940, 38)
        self.min_btn = ctk.CTkButton(self.root, text="", image=self.icon_min, width=40, height=36,
                                     corner_radius=12, fg_color=c_min, bg_color=c_min,
                                     hover_color=T["soft_h"], command=self.minimize)
        self.min_btn.place(x=872, y=20)
        self.close_btn = ctk.CTkButton(self.root, text="", image=self.spin_imgs[0], width=40,
                                       height=36, corner_radius=12, fg_color=c_x, bg_color=c_x,
                                       hover_color=T["soft_h"], command=self.close_window)
        self.close_btn.place(x=920, y=20)
        self.close_btn.bind("<Enter>", self._x_enter, add="+")
        self.close_btn.bind("<Leave>", self._x_leave, add="+")
        self.ui.extend([self.min_btn, self.close_btn])

    # ---------- spinning X ----------
    def _pointer_inside(self, w):
        x = w.winfo_pointerx() - w.winfo_rootx()
        y = w.winfo_pointery() - w.winfo_rooty()
        return 0 <= x < w.winfo_width() and 0 <= y < w.winfo_height()

    def _x_enter(self, e=None):
        if not self._x_hover:
            self._x_hover = True
            self._x_run()

    def _x_leave(self, e=None):
        if self._x_hover and not self._pointer_inside(self.close_btn):
            self._x_hover = False
            self._x_run()

    def _x_run(self):
        if self._x_job is None:
            self._x_step()

    def _x_step(self):
        target = 1.0 if self._x_hover else 0.0
        d = target - self._x_p
        if abs(d) < 0.01:
            self._x_p = target
            self._x_job = None
        else:
            self._x_p += max(-0.16, min(0.16, d))
            self._x_job = self.root.after(14, self._x_step)
        idx = int(round(self._x_p * (SPIN_FRAMES - 1)))
        try:
            self.close_btn.configure(image=self.spin_imgs[idx])
        except Exception:
            self._x_job = None

    # ---------- page transitions ----------
    # Mit FADES = False wird einfach direkt umgeschaltet (schnell, keine Geisterbilder).
    # Mit FADES = True: Snapshot des alten Inhalts in einem Overlay-Fenster ausblenden.
    def _fade_cancel(self, key):
        fx = self._fades.pop(key, None)
        if not fx:
            return
        try:
            if fx["job"]:
                self.root.after_cancel(fx["job"])
        except Exception:
            pass
        try:
            fx["ov"].destroy()
        except Exception:
            pass

    def _fade_swap(self, key, widget, swap, dur, shift=(0, 0), done=None):
        """Snapshot `widget`, call swap() to change the live UI, then fade the
        snapshot away. Falls back to a plain instant swap if anything fails."""
        if not FADES:
            swap()
            if done:
                done()
            return

        self._fade_cancel(key)
        ov = None
        try:
            if not self.root.winfo_viewable():
                raise RuntimeError("window not visible")
            self.root.update_idletasks()
            x, y = widget.winfo_rootx(), widget.winfo_rooty()
            w, h = widget.winfo_width(), widget.winfo_height()
            if w < 10 or h < 10:
                raise RuntimeError("bad size")
            shot = ImageGrab.grab((x, y, x + w, y + h), all_screens=True).convert("RGB")
            ov = tk.Toplevel(self.root)
            ov.withdraw()
            ov.overrideredirect(True)
            ov.configure(bg=T["bg"])
            try:
                ov.attributes("-alpha", 1.0)
                ov.attributes("-disabled", True)
            except Exception:
                pass
            photo = ImageTk.PhotoImage(shot)
            lbl = tk.Label(ov, image=photo, bd=0, highlightthickness=0, bg=T["bg"])
            lbl.image = photo
            lbl.pack()
            ov.geometry(f"{w}x{h}+{x}+{y}")
            ov.deiconify()
            ov.update()                      # snapshot is now on screen
        except Exception:
            if ov is not None:
                try:
                    ov.destroy()
                except Exception:
                    pass
            swap()
            if done:
                done()
            return

        swap()                               # real UI changes underneath the snapshot
        try:
            self.root.update_idletasks()     # make sure the new content is painted
        except Exception:
            pass

        S = self.scale
        sx, sy = shift[0] * S, shift[1] * S
        fx = {"ov": ov, "job": None}
        self._fades[key] = fx
        t0 = time.perf_counter()

        def finish():
            if self._fades.get(key) is fx:
                self._fades.pop(key, None)
            try:
                ov.destroy()
            except Exception:
                pass
            if done:
                done()

        def step():
            t = (time.perf_counter() - t0) / dur
            if t >= 1:
                finish()
                return
            e = 1 - (1 - t) ** 3
            try:
                ov.attributes("-alpha", max(0.0, 1.0 - t ** 0.8))
                ov.geometry(f"+{x + int(sx * e)}+{y + int(sy * e)}")
            except Exception:
                finish()
                return
            fx["job"] = self.root.after(8, step)

        step()

    def go(self, name):
        self.tabs.select(PAGES.index(name))
        if self.animating:
            self._pending = name
            return
        if name == self.page_name:
            return
        self._fade_cancel("section")
        old, new = self.pages[self.page_name], self.pages[name]
        d = 1 if PAGES.index(name) > PAGES.index(self.page_name) else -1
        self.page_name = name
        self.animating = True

        def swap():
            new.place(x=PX, y=PY)
            new.lift()
            old.place_forget()

        self._fade_swap("page", old, swap, TRANSITION_S, shift=(-d * 26, 0), done=self._finish)

    def _finish(self):
        self.animating = False
        nxt, self._pending = self._pending, None
        if nxt and nxt != self.page_name:
            self.go(nxt)

    # ---------- player page ----------
    def _build_player(self, page):
        panel = T["panel"]
        self.hero_main = HeroCard(self, page, 0, 0, 562, PH, 300, 200, True)

        card = self.make_card(page, 574, 0, 362, PH)
        ctk.CTkLabel(card, text="RECENTLY PLAYED", font=("Segoe UI", 12, "bold"), text_color=T["text"],
                     fg_color=panel, bg_color=panel).place(x=22, y=22)
        self.count_lbl = ctk.CTkLabel(card, text="0 songs", font=("Segoe UI", 10, "bold"),
                                      fg_color=T["dim"], text_color=T["accent"], corner_radius=10,
                                      height=22, width=70, bg_color=panel)
        self.count_lbl.place(relx=1, x=-22, y=21, anchor="ne")
        self.sub_lbl = ctk.CTkLabel(card, text="Recently played · click to play again",
                                    font=("Segoe UI", 11), text_color=T["muted"],
                                    fg_color=panel, bg_color=panel)
        self.sub_lbl.place(x=22, y=48)
        self.search = ctk.CTkEntry(card, placeholder_text="Search songs ...", width=330, height=36,
                                   corner_radius=10, fg_color=T["bg"], border_color=T["line"],
                                   border_width=1, text_color=T["text"],
                                   placeholder_text_color=T["muted"], font=("Segoe UI", 12),
                                   bg_color=panel)
        self.search.place(x=16, y=78)
        self.search.bind("<KeyRelease>", lambda e: self.refresh_list())
        self.clear_history_btn = ctk.CTkButton(
            card, text="Clear", width=54, height=24, corner_radius=8,
            fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["muted"],
            font=("Segoe UI", 10, "bold"), bg_color=panel, command=self.clear_history)
        self.clear_history_btn.place(x=204, y=20)
        self.list = ctk.CTkScrollableFrame(card, width=312, height=370, fg_color=panel,
                                           bg_color=panel, corner_radius=0,
                                           scrollbar_button_color=T["soft_h"],
                                           scrollbar_button_hover_color=T["muted"])
        self.list.place(x=8, y=130)

    def notify(self, msg, ms=3400):
        try:
            self.sub_lbl.configure(text=msg, text_color=T["accent"])
            if self._notice_job:
                self.root.after_cancel(self._notice_job)
            self._notice_job = self.root.after(ms, self._clear_notice)
        except Exception:
            pass

    def clear_history(self):
        if not self.history:
            return
        if not messagebox.askyesno(
                "Clear song history",
                "Remove all songs from your listening history?",
                parent=self.root):
            return
        if not save_history([], {}):
            messagebox.showerror(
                "Couldn't clear history",
                "The song history file could not be updated. Your history has not been cleared.",
                parent=self.root)
            return
        self.history.clear()
        self.ids.clear()
        self.row_cache.clear()
        self.hist_ver += 1
        self.bump()
        self.refresh_list()

    def _clear_notice(self):
        self._notice_job = None
        try:
            self.sub_lbl.configure(text="Recently played · click to play again", text_color=T["muted"])
        except Exception:
            pass

    def _row_cover(self, key):
        real = self.covers.get(key)
        ck = (key, id(real) if real is not None else 0)
        ci = self.row_cache.get(ck)
        if ci is None:
            base = real if real is not None else gradient_cover(f"{key[0]}{key[1]}", 96)
            img = round_image(base, int(42 * self.scale), 0.16)
            ci = ctk.CTkImage(img, img, size=(42, 42))
            if len(self.row_cache) > 400:
                self.row_cache.clear()
            self.row_cache[ck] = ci
        return ci

    def refresh_list(self):
        self.bump()
        self._last_list = time.time()
        self._cover_seen = self.cover_ver
        self.cur_glyph = None
        for w in self.list.winfo_children():
            w.destroy()
        q = self.search.get().strip().lower()
        items = [k for k in self.history if q in f"{k[0]} {k[1]}".lower()]
        self.count_lbl.configure(text=f"{len(self.history)} songs")
        if not q:
            items = items[:LIST_MAX]   # ohne Suche nur die neuesten -> weniger Widgets
        if not items:
            ctk.CTkLabel(self.list, text="No songs yet" if not self.history else "No results",
                         font=("Segoe UI", 13, "bold"), text_color=T["muted"]).pack(pady=(40, 2))
            if not self.history:
                ctk.CTkLabel(self.list, text="Play a song in Spotify\nand it will show up here.",
                             font=("Segoe UI", 11), text_color=T["muted"]).pack()
            return
        for i, key in enumerate(items):
            if key not in self.covers:
                self.fetcher.request(key, 3 + i)
            self._make_row(key)

    def _idle_glyph(self, cur):
        return ("▶" if self.playing else "⏸") if cur else ""

    def _make_row(self, key):
        artist, song = key
        cur = key == self.current
        base_c = T["dim"] if cur else T["soft"]
        hover_c = T["sel"] if cur else T["soft_h"]
        row = ctk.CTkFrame(self.list, height=58, corner_radius=10, fg_color=base_c)
        row.pack(fill="x", pady=2, padx=4)
        row.pack_propagate(False)
        cover = ctk.CTkLabel(row, image=self._row_cover(key), text="", fg_color="transparent")
        cover.pack(side="left", padx=(10, 12))
        txt = ctk.CTkFrame(row, fg_color="transparent")
        txt.pack(side="left", fill="both", expand=True, pady=10)
        t1 = ctk.CTkLabel(txt, text=short(song, 26), font=("Segoe UI", 12, "bold"),
                          text_color=T["accent"] if cur else T["text"], anchor="w")
        t1.pack(anchor="w")
        t2 = ctk.CTkLabel(txt, text=short(artist, 30), font=("Segoe UI", 10),
                          text_color=T["muted"], anchor="w")
        t2.pack(anchor="w")
        glyph = ctk.CTkLabel(row, text=self._idle_glyph(cur), font=("Segoe UI Symbol", 13),
                             text_color=T["accent"], width=24)
        glyph.pack(side="right", padx=14)
        if cur:
            self.cur_glyph = glyph

        def enter(e=None):
            row.configure(fg_color=hover_c)
            glyph.configure(text="▶")

        def leave(e=None):
            if self._pointer_inside(row):
                return
            row.configure(fg_color=base_c)
            glyph.configure(text=self._idle_glyph(cur))

        def click(e=None, k=key):
            self.play_track(k)

        for w in (row, cover, txt, t1, t2, glyph):
            w.bind("<Enter>", enter, add="+")
            w.bind("<Leave>", leave, add="+")
            w.bind("<Button-1>", click, add="+")
            for part in ("_label", "_canvas"):
                try:
                    getattr(w, part).configure(cursor="hand2")
                except Exception:
                    pass

    def play_track(self, key):
        artist, title = key
        self.notify(f"Starting “{short(title, 26)}” …")

        def work():
            kid = "\t".join(key)
            tid = self.ids.get(kid)
            if not tid:
                try:
                    tid = resolve_track_id(key)
                except Exception:
                    tid = None
                if tid:
                    self.ids[kid] = tid
                    save_history(self.history, self.ids)
            if tid:
                uri, msg = "spotify:track:" + tid, f"Playing “{short(title, 26)}”"
            else:
                uri = "spotify:search:" + urllib.parse.quote(f"{artist} {title}")
                msg = "No exact match found – opened search in Spotify"
            try:
                os.startfile(uri)
            except Exception:
                msg = "Couldn't open Spotify"
            self.post(lambda: self.notify(msg))

        threading.Thread(target=work, daemon=True).start()

    # ---------- hotkeys page ----------
    def _build_keys(self, page):
        panel = T["panel"]
        self.hero_keys = HeroCard(self, page, 0, 0, 360, PH, 300, 190, False)
        card = self.make_card(page, 374, 0, 562, PH)
        ctk.CTkLabel(card, text="Hotkeys", font=("Segoe UI", 24, "bold"), text_color=T["text"],
                     fg_color=panel, bg_color=panel).place(x=28, y=22)
        ctk.CTkLabel(card, text="Click a key, then press the new one. ESC cancels.",
                     font=("Segoe UI", 12), text_color=T["muted"], fg_color=panel,
                     bg_color=panel).place(x=28, y=58)
        for i, action in enumerate(ACTION_ORDER):
            row = ctk.CTkFrame(card, fg_color=T["bg"], corner_radius=16, border_width=1,
                               border_color=T["line"], bg_color=panel, width=506, height=46)
            row.place(x=28, y=96 + i * 54)
            row.pack_propagate(False)
            ctk.CTkLabel(row, text=LABELS[action], font=("Segoe UI", 13, "bold"),
                         text_color=T["text"]).pack(side="left", padx=18)
            b = ctk.CTkButton(row, text="", width=130, height=34, corner_radius=17,
                              font=("Segoe UI", 12, "bold"), fg_color=T["soft"],
                              hover_color=T["soft_h"], text_color=T["accent"],
                              command=lambda a=action: self.change_key(a))
            b.pack(side="right", padx=10)
            self.key_buttons[action] = b
        ctk.CTkButton(card, text="Reset", width=130, height=40, corner_radius=14, fg_color=T["soft"],
                      hover_color=T["soft_h"], text_color=T["text"], font=("Segoe UI", 12, "bold"),
                      bg_color=panel, command=self.reset_keys).place(x=28, y=438)
        ctk.CTkButton(card, text="Save", width=150, height=40, corner_radius=14,
                      fg_color=T["accent"], hover_color=T["accent_h"], text_color=T["on_accent"],
                      font=("Segoe UI", 13, "bold"), bg_color=panel,
                      command=self.save_hotkeys).place(x=562 - 28 - 150, y=438)
        self.toast = ctk.CTkLabel(card, text="✓  Saved", font=("Segoe UI", 12, "bold"),
                                  fg_color=T["dim"], text_color=T["accent"], corner_radius=14,
                                  height=34, width=130, bg_color=panel)

    def refresh_keys(self):
        self.bump()
        for a, b in self.key_buttons.items():
            b.configure(text=key_name(config.get(a)), text_color=T["accent"], fg_color=T["soft"])
        for a, cap in self.captions.items():
            cap.configure(text=key_name(config.get(a)))

    def change_key(self, action):
        if runtime["capturing"]:
            return
        runtime["capturing"] = True
        self.key_buttons[action].configure(text="Press a key …", text_color=T["text"],
                                           fg_color=T["dim"])
        threading.Thread(target=self._capture, args=(action,), daemon=True).start()

    def _capture(self, action):
        while any(is_pressed(v) for v in range(8, 255)):
            time.sleep(0.03)
        vk = None
        deadline = time.time() + 10
        while vk is None and time.time() < deadline:
            for v in range(8, 255):
                if is_pressed(v):
                    vk = v
                    break
            time.sleep(0.01)
        self.post(lambda: self._apply_key(action, vk))

    def _apply_key(self, action, vk):
        if vk is not None and vk != 0x1B:
            for k in config:
                if config[k] == vk:
                    config[k] = None
            config[action] = vk
        runtime["capturing"] = False
        self.refresh_keys()

    def reset_keys(self):
        config.clear()
        config.update(DEFAULT_CONFIG)
        self.refresh_keys()

    def save_hotkeys(self):
        save_config()
        self.toast.place(relx=0.5, y=480, anchor="n")
        self.root.after(1600, self.toast.place_forget)

    # ---------- settings page ----------
    def _build_settings(self, page):
        side = self.make_card(page, 0, 0, 210, PH)
        S = self.scale
        nx, ny, nw = 20, 24, 170
        nh = len(SECTIONS) * 50 - 8
        crop = side.pil_img.crop((int(nx * S), int(ny * S), int(nx * S) + int(nw * S),
                                  int(ny * S) + int(nh * S)))
        rects = [(0, i * 50, nw, 42) for i in range(len(SECTIONS))]
        self.side_nav = PillNav(self, side, crop, [SECTION_LABELS[k] for k in SECTIONS], rects,
                                (nw, nh), True, lambda i: self.show_section(SECTIONS[i]))
        self.side_nav.label.place(x=nx, y=ny)

        panel = T["panel"]
        main = self.make_card(page, 224, 0, 712, PH)
        self.sections = {}
        for k in SECTIONS:
            self.sections[k] = ctk.CTkFrame(main, fg_color=panel, bg_color=panel, corner_radius=0,
                                            width=656, height=466)
        self._build_general(self.sections["general"])
        self._build_look(self.sections["look"])
        self._build_stream(self.sections["stream"])
        self._build_discord(self.sections["discord"])
        self._build_spotify(self.sections["spotify"])
        self._build_about(self.sections["about"])
        self.show_section(self.section, animate=False)

    def show_section(self, name, animate=True):
        prev = self.section
        self.section = name
        self.bump()

        def swap():
            for k, f in self.sections.items():
                if k == name:
                    f.place(x=28, y=24)
                else:
                    f.place_forget()

        self.side_nav.select(SECTIONS.index(name), animate=animate)
        if (FADES and animate and name != prev and not self.animating
                and self.page_name == "settings" and prev in self.sections):
            d = 1 if SECTIONS.index(name) > SECTIONS.index(prev) else -1
            self._fade_swap("section", self.sections[prev], swap, SECTION_S, shift=(0, -d * 10))
        else:
            self._fade_cancel("section")
            swap()

    def _heading(self, parent, title, sub, label):
        panel = T["panel"]
        ctk.CTkLabel(parent, text=title, font=("Segoe UI", 28, "bold"), text_color=T["text"],
                     fg_color=panel, bg_color=panel).place(x=0, y=0)
        ctk.CTkLabel(parent, text=sub, font=("Segoe UI", 12), text_color=T["muted"],
                     fg_color=panel, bg_color=panel).place(x=0, y=44)
        ctk.CTkLabel(parent, text=label, font=("Segoe UI", 10, "bold"), text_color=T["muted"],
                     fg_color=panel, bg_color=panel).place(x=2, y=88)

    def _group(self, parent, y, h):
        g = ctk.CTkFrame(parent, fg_color=T["bg"], bg_color=T["panel"], corner_radius=18,
                         border_width=1, border_color=T["line"], width=656, height=h)
        g.place(x=0, y=y)
        return g

    def _row(self, group, i, title, desc, factory, last=False, desc_command=None,
             row_height=72):
        row = ctk.CTkFrame(group, fg_color="transparent", width=652, height=row_height,
                           corner_radius=0)
        row.place(x=2, y=2 + i * row_height)
        ctk.CTkLabel(row, text=title, font=("Segoe UI", 14, "bold"),
                     text_color=T["text"]).place(x=20, y=13)
        if desc_command:
            ctk.CTkButton(row, text=desc, font=("Segoe UI", 11), anchor="w",
                          width=280, height=20, corner_radius=0, fg_color="transparent",
                          hover_color=T["soft"], text_color=T["accent"],
                          command=desc_command).place(x=20, y=39)
        else:
            ctk.CTkLabel(row, text=desc, font=("Segoe UI", 11),
                         text_color=T["muted"]).place(x=20, y=39)
        ctrl = factory(row)
        ctrl.place(relx=1, x=-20, rely=0.5, anchor="e")
        if not last:
            ctk.CTkFrame(group, fg_color=T["line"], height=1, width=620,
                         corner_radius=0).place(x=18, y=2 + (i + 1) * row_height)

    def _switch(self, parent, value, command):
        sw = ctk.CTkSwitch(parent, text="", width=48, height=24, switch_width=44, switch_height=22,
                           fg_color=T["soft_h"], progress_color=T["accent"], button_color="#FFFFFF",
                           button_hover_color="#E4E4EA", command=lambda: command(sw))
        if value:
            sw.select()
        return sw

    def _build_general(self, parent):
        self._heading(parent, "Settings", "Everything Spotify Controller does, in one place.", "GENERAL")
        g = self._group(parent, 112, 4 * 72 + 4)

        def on_autostart(sw):
            try:
                set_autostart(bool(sw.get()))
            except Exception:
                sw.deselect() if sw.get() else sw.select()
            self.bump()

        def on_top(sw):
            settings["always_on_top"] = bool(sw.get())
            save_settings()
            self.root.attributes("-topmost", settings["always_on_top"])
            self.bump()

        def close_seg(p):
            seg = ctk.CTkSegmentedButton(
                p, values=["Tray", "Quit"], height=34, corner_radius=12, font=("Segoe UI", 12, "bold"),
                fg_color=T["bg"], selected_color=T["sel"], selected_hover_color=T["sel"],
                unselected_color=T["bg"], unselected_hover_color=T["soft"], text_color=T["text"],
                command=self._on_close_action)
            seg.set("Quit" if settings["close_action"] == "quit" else "Tray")
            return seg

        self._row(g, 0, "Start with Windows", "Starts quietly in the tray when you log in.",
                  lambda p: self._switch(p, get_autostart(), on_autostart))
        self._row(g, 1, "Always on top", "Keeps the window above other apps.",
                  lambda p: self._switch(p, settings["always_on_top"], on_top))
        self._row(g, 2, "Close button", "What the X in the top right does.", close_seg)
        self._row(g, 3, "Config folder", "Where your hotkeys and settings are saved.",
                  lambda p: ctk.CTkButton(p, text="Open", width=90, height=34, corner_radius=12,
                                          fg_color=T["soft"], hover_color=T["soft_h"],
                                          text_color=T["text"], font=("Segoe UI", 12, "bold"),
                                          command=lambda: os.startfile(BASE_DIR)), last=True)

    def _on_close_action(self, value):
        settings["close_action"] = "quit" if value == "Quit" else "tray"
        save_settings()
        self.bump()

    def _build_look(self, parent):
        self._heading(parent, "Look", "Choose an accent color and now-playing design.", "ACCENT")
        g = self._group(parent, 112, 150)
        for i, key in enumerate(LOOK_ORDER):
            sel = key == T["key"]
            cx = 82 + 164 * i
            img = swatch_image(key, sel, 120)
            b = ctk.CTkButton(g, text="", image=ctk.CTkImage(img, img, size=(60, 60)), width=64,
                              height=64, corner_radius=32, fg_color=T["bg"], hover_color=T["bg"],
                              bg_color=T["bg"], command=lambda k=key: self.set_look(k))
            b.place(x=cx - 32, y=24)
            ctk.CTkLabel(g, text=THEMES[key]["name"], font=("Segoe UI", 12, "bold"),
                         text_color=T["text"] if sel else T["muted"], fg_color=T["bg"],
                         bg_color=T["bg"]).place(x=cx, y=100, anchor="n")
        ctk.CTkLabel(parent, text="NOW PLAYING DESIGN", font=("Segoe UI", 10, "bold"),
                     text_color=T["muted"], fg_color=T["panel"],
                     bg_color=T["panel"]).place(x=2, y=286)
        design = self._group(parent, 312, 82)
        selected_style = settings.get("now_playing_style", "Spotify")
        self.now_playing_style = ctk.CTkSegmentedButton(
            design, values=list(NOW_PLAYING_STYLES), width=612, height=38, corner_radius=12,
            font=("Segoe UI", 12, "bold"), fg_color=T["panel"],
            selected_color=T["sel"], selected_hover_color=T["sel"],
            unselected_color=T["panel"], unselected_hover_color=T["soft"],
            text_color=T["text"], command=self.set_now_playing_style)
        self.now_playing_style.set(selected_style)
        self.now_playing_style.place(x=20, y=21)
        self.now_playing_hint = ctk.CTkLabel(
            parent, text=f"Selected: {selected_style} · Home player updates immediately.",
            font=("Segoe UI", 11), text_color=T["muted"],
            fg_color=T["panel"], bg_color=T["panel"])
        self.now_playing_hint.place(x=2, y=404)

    def set_look(self, key):
        if key == T["key"]:
            return
        settings["look"] = key
        save_settings()
        apply_theme(key)
        self.root.after(10, self.rebuild)

    def set_now_playing_style(self, style):
        if style not in NOW_PLAYING_STYLES:
            return
        settings["now_playing_style"] = style
        save_settings()
        self.now_playing_hint.configure(
            text=f"Selected: {style} · Home player updates immediately.")
        self.hero_main._sig = None
        self.hero_main.update(
            self.current, self.covers.get(self.current) if self.current else None,
            self.playing, self.running)
        self._update_track_progress()

    def _build_stream(self, parent):
        self._heading(parent, "Stream", "A small Now Playing overlay for OBS.", "OBS OVERLAY")
        g = self._group(parent, 112, 3 * 68 + 4)

        def on_overlay(sw):
            self.toggle_overlay(bool(sw.get()))

        self._row(g, 0, "Show overlay", "Starts a local overlay you add as a Browser Source.",
                  lambda p: self._switch(p, settings.get("overlay_enabled", False), on_overlay),
                  row_height=68)
        self._row(g, 1, "Browser source URL", "Paste this into OBS as a Browser Source.",
                  self._overlay_url_box, row_height=68)
        self._row(g, 2, "Port", "Change only if 8787 is already used by something else.",
                  self._overlay_port_box, last=True, row_height=68)

        design_y = 112 + 3 * 68 + 4 + 18
        ctk.CTkLabel(parent, text="OVERLAY DESIGN", font=("Segoe UI", 10, "bold"),
                     text_color=T["muted"], fg_color=T["panel"],
                     bg_color=T["panel"]).place(x=2, y=design_y)
        dg = self._group(parent, design_y + 24, 50)
        self.overlay_style_seg = ctk.CTkSegmentedButton(
            dg, values=list(OVERLAY_STYLES), width=612, height=36, corner_radius=12,
            font=("Segoe UI", 12, "bold"), fg_color=T["panel"],
            selected_color=T["sel"], selected_hover_color=T["sel"],
            unselected_color=T["panel"], unselected_hover_color=T["soft"],
            text_color=T["text"], command=self.set_overlay_style)
        self.overlay_style_seg.set(settings.get("overlay_style", "Card"))
        self.overlay_style_seg.place(x=20, y=7)

        tip = ("OBS: Sources -> + -> Browser -> paste the URL above (420x120 works well). "
               "The design updates live, no browser-source refresh needed.")
        ctk.CTkLabel(parent, text=tip, font=("Segoe UI", 11), text_color=T["muted"],
                     fg_color=T["panel"], bg_color=T["panel"], justify="left",
                     wraplength=640).place(x=2, y=design_y + 24 + 50 + 12)

    def set_overlay_style(self, style):
        if style not in OVERLAY_STYLES:
            return
        settings["overlay_style"] = style
        save_settings()

    def _overlay_url(self):
        return f"http://127.0.0.1:{settings.get('overlay_port', OVERLAY_DEFAULT_PORT)}/overlay"

    def _overlay_url_box(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent", width=250, height=36)
        self.overlay_url_label = ctk.CTkLabel(
            frame, text=self._overlay_url(), width=220, anchor="w",
            font=("Segoe UI", 10), text_color=T["muted"])
        self.overlay_url_label.pack(side="left", padx=(0, 6))
        self.copy_overlay_btn = ctk.CTkButton(
            frame, text="Copy", width=62, height=34, corner_radius=12,
            fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["text"],
            font=("Segoe UI", 11, "bold"), command=self.copy_overlay_url)
        self.copy_overlay_btn.pack(side="left")
        return frame

    def _overlay_port_box(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent", width=250, height=36)
        self.overlay_port_entry = ctk.CTkEntry(
            frame, width=90, height=34, corner_radius=12, fg_color=T["panel"],
            border_color=T["line"], border_width=1, text_color=T["text"], font=("Segoe UI", 12))
        self.overlay_port_entry.insert(0, str(settings.get("overlay_port", OVERLAY_DEFAULT_PORT)))
        self.overlay_port_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            frame, text="Apply", width=70, height=34, corner_radius=12,
            fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["text"],
            font=("Segoe UI", 11, "bold"), command=self.apply_overlay_port).pack(side="left")
        return frame

    def copy_overlay_url(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(self._overlay_url())
            self.root.update_idletasks()
        except tk.TclError as exc:
            messagebox.showerror("Copy failed", f"Couldn't copy the overlay URL:\n{exc}",
                                 parent=self.root)
            return
        self.copy_overlay_btn.configure(text="Copied!")

    def toggle_overlay(self, on):
        settings["overlay_enabled"] = on
        save_settings()
        if on:
            port = settings.get("overlay_port", OVERLAY_DEFAULT_PORT)
            if not overlay_server.start(port):
                settings["overlay_enabled"] = False
                save_settings()
                self.notify(f"Couldn't start the overlay on port {port} (already in use?)", 5000)
        else:
            overlay_server.stop()
        self.bump()

    def apply_overlay_port(self):
        raw = self.overlay_port_entry.get().strip()
        try:
            port = int(raw)
            if not (1024 <= port <= 65535):
                raise ValueError
        except ValueError:
            self.notify("Enter a port number between 1024 and 65535", 3500)
            return
        settings["overlay_port"] = port
        save_settings()
        if settings.get("overlay_enabled"):
            if not overlay_server.start(port):
                self.notify(f"Couldn't start the overlay on port {port} (already in use?)", 5000)
                return
        self.overlay_url_label.configure(text=self._overlay_url())
        self.notify("Overlay port updated", 2500)

    def _build_discord(self, parent):
        self._heading(parent, "Discord", "#22234In Development...", "Show the current song as your Discord status.",)
        g = self._group(parent, 112, 3 * 68 + 4)

        def on_discord(sw):
            self.toggle_discord(bool(sw.get()))

        self._row(g, 0, "Show on Discord", "Needs the Discord desktop app running.",
                  lambda p: self._switch(p, settings.get("discord_enabled", False), on_discord),
                  row_height=68)
        self._row(g, 1, "Application ID", "Open the Discord Developer Portal",
                  self._discord_id_box,
                  desc_command=lambda: webbrowser.open(
                      "https://discord.com/developers/applications"), row_height=68)
        self._row(g, 2, "Connection", "Reconnects automatically while enabled.",
                  self._discord_status_box, last=True, row_height=68)

        if HAS_DISCORD:
            tip = ("Create a free app at discord.com/developers, copy its Application ID "
                   "above. Optional: under Rich Presence -> Art Assets, upload images named "
                   "exactly \"logo\", \"play\" and \"pause\" for icons - without them Discord "
                   "just shows the song as text. Shows a “Play on Spotify” button, "
                   "a live progress bar and a play/pause icon - note Discord never shows "
                   "buttons on your own profile, only to other people.")
        else:
            tip = "Needs the pypresence package. Install it, then rebuild: pip install pypresence"
        ctk.CTkLabel(parent, text=tip, font=("Segoe UI", 11), text_color=T["muted"],
                     fg_color=T["panel"], bg_color=T["panel"], justify="left",
                     wraplength=640).place(x=2, y=112 + 3 * 68 + 4 + 16)

    def _discord_id_box(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent", width=300, height=36)
        self.discord_id_entry = ctk.CTkEntry(
            frame, width=210, height=34, corner_radius=12, fg_color=T["panel"],
            border_color=T["line"], border_width=1, text_color=T["text"], font=("Segoe UI", 12))
        if settings.get("discord_client_id"):
            self.discord_id_entry.insert(0, settings["discord_client_id"])
        self.discord_id_entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            frame, text="Save", width=70, height=34, corner_radius=12,
            fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["text"],
            font=("Segoe UI", 11, "bold"), command=self.save_discord_id).pack(side="left")
        return frame

    def _discord_status_box(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent", width=250, height=36)
        connected = discord_rpc.connected
        self.discord_status = ctk.CTkLabel(
            frame, text="Connected" if connected else "Not connected",
            font=("Segoe UI", 12, "bold"), text_color=T["accent"] if connected else T["muted"])
        self.discord_status.pack(side="left")
        return frame

    def save_discord_id(self):
        cid = self.discord_id_entry.get().strip()
        settings["discord_client_id"] = cid
        save_settings()
        discord_rpc.disconnect()
        self._discord_retry_at = 0.0
        try:
            self.discord_status.configure(text="Not connected", text_color=T["muted"])
        except Exception:
            pass
        if settings.get("discord_enabled") and cid:
            self.notify("Discord: reconnecting with the new Application ID", 3000)

    def toggle_discord(self, on):
        settings["discord_enabled"] = on
        save_settings()
        self._discord_retry_at = 0.0
        if not on:
            discord_rpc.disconnect()
            try:
                self.discord_status.configure(text="Not connected", text_color=T["muted"])
            except Exception:
                pass

    def _build_spotify(self, parent):
        self._heading(parent, "Spotify", "Optional: exact song matching and the Like hotkey.", "WEB API")
        g = self._group(parent, 112, 5 * 68 + 4)

        def entry(value, hide):
            def make(p):
                kw = {"show": "•"} if hide else {}
                e = ctk.CTkEntry(p, width=300, height=34, corner_radius=12, fg_color=T["panel"],
                                 border_color=T["line"], border_width=1, text_color=T["text"],
                                 font=("Segoe UI", 12), **kw)
                if value:
                    e.insert(0, value)
                if hide:
                    self.api_secret = e
                else:
                    self.api_id = e
                return e
            return make

        def status_box(p):
            fr = ctk.CTkFrame(p, fg_color="transparent", width=250, height=36)
            self.api_status = ctk.CTkLabel(
                fr, text="Connected" if spotify_api.configured() else "Not set",
                font=("Segoe UI", 12, "bold"),
                text_color=T["accent"] if spotify_api.configured() else T["muted"])
            self.api_status.pack(side="left", padx=(0, 12))
            ctk.CTkButton(fr, text="Save & test", width=110, height=34, corner_radius=12,
                          fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["text"],
                          font=("Segoe UI", 12, "bold"), command=self.save_api).pack(side="left")
            return fr

        self._row(g, 0, "Client ID", "Open Spotify Developer Dashboard",
                  entry(settings.get("spotify_id", ""), False),
                  desc_command=lambda: webbrowser.open("https://developer.spotify.com/dashboard"),
                  row_height=68)
        self._row(g, 1, "Client secret", "Stored in settings.json next to this script.",
                  entry(settings.get("spotify_secret", ""), True), row_height=68)
        self._row(g, 2, "Connection", "Without it, matches come from iTunes / Deezer.",
                  status_box, row_height=68)

        def acct_box(p):
            fr = ctk.CTkFrame(p, fg_color="transparent", width=250, height=36)
            linked = spotify_user.linked()
            self.acct_status = ctk.CTkLabel(
                fr, text="Linked" if linked else "Not linked", font=("Segoe UI", 12, "bold"),
                text_color=T["accent"] if linked else T["muted"])
            self.acct_status.pack(side="left", padx=(0, 12))
            self.acct_btn = ctk.CTkButton(
                fr, text="Unlink" if linked else "Connect", width=110, height=34, corner_radius=12,
                fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["text"],
                font=("Segoe UI", 12, "bold"), command=self.toggle_account)
            self.acct_btn.pack(side="left")
            return fr

        self._row(g, 3, "Account (Like hotkey)",
                  "Connect your account to enable the Like hotkey.",
                  acct_box, row_height=68)
        self._row(g, 4, "Redirect URI", "Add this address to your Spotify app settings.",
                  self._redirect_uri_box, last=True, row_height=68)

    def _redirect_uri_box(self, parent):
        frame = ctk.CTkFrame(parent, fg_color="transparent", width=250, height=36)
        self.redirect_uri_label = ctk.CTkLabel(
            frame, text=SpotifyUser.REDIRECT, width=175, anchor="w",
            font=("Segoe UI", 10), text_color=T["muted"])
        self.redirect_uri_label.pack(side="left", padx=(0, 6))
        self.copy_redirect_btn = ctk.CTkButton(
            frame, text="Copy", width=62, height=34, corner_radius=12,
            fg_color=T["soft"], hover_color=T["soft_h"], text_color=T["text"],
            font=("Segoe UI", 11, "bold"), command=self.copy_redirect_uri)
        self.copy_redirect_btn.pack(side="left")
        return frame

    def copy_redirect_uri(self):
        try:
            self.root.clipboard_clear()
            self.root.clipboard_append(SpotifyUser.REDIRECT)
            self.root.update_idletasks()
        except tk.TclError as exc:
            messagebox.showerror("Copy failed", f"Couldn't copy the redirect URI:\n{exc}",
                                 parent=self.root)
            return
        self.copy_redirect_btn.configure(text="Copied!")

    def toggle_account(self):
        if spotify_user.linked():
            spotify_user.unlink()
            self.acct_status.configure(text="Not linked", text_color=T["muted"])
            self.acct_btn.configure(text="Connect")
            return
        settings["spotify_id"] = self.api_id.get().strip()
        save_settings()
        if not settings["spotify_id"]:
            self.acct_status.configure(text="Enter Client ID first", text_color="#F87171")
            return
        self.acct_status.configure(text="Waiting for login …", text_color=T["muted"])
        self.acct_btn.configure(state="disabled")

        def work():
            try:
                spotify_user.connect()
                ok = True
            except Exception:
                ok = False

            def done():
                try:
                    self.acct_btn.configure(state="normal", text="Unlink" if ok else "Connect")
                    self.acct_status.configure(
                        text="Linked" if ok else "Login failed",
                        text_color=T["accent"] if ok else "#F87171")
                except Exception:
                    pass
            self.post(done)

        threading.Thread(target=work, daemon=True).start()

    def save_api(self):
        new_id = self.api_id.get().strip()
        if new_id != settings.get("spotify_id", "") and settings.get("spotify_refresh"):
            spotify_user.unlink()
            try:
                self.acct_status.configure(text="Not linked", text_color=T["muted"])
                self.acct_btn.configure(text="Connect")
            except Exception:
                pass
        settings["spotify_id"] = new_id
        settings["spotify_secret"] = self.api_secret.get().strip()
        save_settings()
        spotify_api.reset()
        if not spotify_api.configured():
            self.api_status.configure(text="Not set", text_color=T["muted"])
            return
        self.api_status.configure(text="Testing …", text_color=T["muted"])

        def work():
            try:
                spotify_api.get_token()
                ok = True
            except Exception:
                ok = False
            self.post(lambda: self.api_status.configure(
                text="Connected" if ok else "Invalid keys",
                text_color=T["accent"] if ok else "#F87171"))

        threading.Thread(target=work, daemon=True).start()

    def _build_about(self, parent):
        self._heading(parent, "About", f"{APP_NAME} {APP_VERSION}", "INFO")
        g = self._group(parent, 112, 3 * 72 + 4)

        def txt(value):
            return lambda p: ctk.CTkLabel(p, text=value, font=("Segoe UI", 12, "bold"),
                                          text_color=T["accent"])

        self._row(g, 0, "Version", "You are running the build you installed.", txt(APP_VERSION))
        self._row(g, 1, "Now playing", "Where the current song comes from.",
                  txt("Media session" if HAS_MEDIA else "Window title"))
        self._row(g, 2, "Covers", "Where album art is looked up.",
                  txt("Spotify API" if spotify_api.configured() else "iTunes / Deezer"), last=True)

        credit = ctk.CTkFrame(parent, fg_color=T["panel"], bg_color=T["panel"],
                              corner_radius=0, width=656, height=24)
        credit.place(x=2, y=112 + 3 * 72 + 4 + 16)
        ctk.CTkLabel(credit, text="Developed by", font=("Segoe UI", 11),
                     text_color=T["muted"], fg_color=T["panel"]).pack(side="left")
        ctk.CTkLabel(credit, text="airangelic", font=("Segoe UI", 11, "bold"),
                     text_color=T["accent"], fg_color=T["panel"]).pack(side="left", padx=(5, 0))

    # ---------- actions ----------
    def do_action(self, action):
        """Klick auf einen Button im Fenster: Taste senden + UI sofort aktualisieren."""
        if action == "like":
            self.like_current()
            return
        press_key(ACTIONS[action])
        self.after_action(action)

    def like_current(self):
        """Aktuellen Song zu 'Lieblingssongs' hinzufuegen (Hotkey oder Aufruf)."""
        key = self.current
        if not key:
            self.notify("Nothing playing to like")
            return
        if not spotify_user.linked():
            self.notify("Connect your Spotify account first (Settings → Spotify)", 5000)
            return
        title = key[1]

        def work():
            ok = False
            try:
                kid = "\t".join(key)
                tid = self.ids.get(kid)
                if not tid:
                    tid = resolve_track_id(key)
                    if tid:
                        self.ids[kid] = tid
                        save_history(self.history, self.ids)
                if not tid:
                    msg = "Couldn't find an exact match to like"
                else:
                    spotify_user.save_track(tid)
                    msg, ok = f"♥  Liked “{short(title, 26)}”", True
            except urllib.error.HTTPError as e:
                if e.code in (400, 401):
                    msg = "Spotify login expired – reconnect in Settings"
                elif e.code == 403:
                    msg = "Spotify refused – add your account under User Management"
                else:
                    msg = f"Couldn't like song (HTTP {e.code})"
            except Exception:
                msg = "Couldn't like song"
            if ok and LIKE_SOUND:
                try:
                    winsound.MessageBeep(winsound.MB_OK)
                except Exception:
                    pass
            self.post(lambda: self.notify(msg, 4000))

        threading.Thread(target=work, daemon=True).start()

    def after_action(self, action):
        """Wird von Button UND Hotkey aufgerufen (die Taste wurde schon gesendet).
        Schaltet Play/Pause sofort um, ohne auf Spotify zu warten."""
        if action == "play_pause" and self.running:
            self.playing = not self.playing
            self._opt_until = time.time() + OPTIMISTIC_S
            self._last_playing = self.playing
            self.apply_playing()

    def apply_playing(self):
        """Nur Button, Pill und Glyph der aktuellen Zeile - kein Rebuild der Liste."""
        for h in (self.hero_main, self.hero_keys):
            try:
                h.set_status(self.playing, self.running)
            except Exception:
                pass
        try:
            if self.cur_glyph is not None:
                self.cur_glyph.configure(text=self._idle_glyph(True))
        except Exception:
            self.cur_glyph = None

    def minimize(self):
        try:
            _u.ShowWindow(self._hwnd(), 6)
        except Exception:
            self.hide()

    def close_window(self):
        if settings.get("close_action") == "quit":
            quit_app()
        else:
            self.hide()

    # ---------- spotify state ----------
    def _add_history(self, key):
        if key in self.history:
            self.history.remove(key)
        self.history.insert(0, key)
        del self.history[50:]
        self.hist_ver += 1
        save_history(self.history, self.ids)

    def tick(self):
        try:
            self._poll()
        except Exception:
            pass
        self.root.after(UI_TICK_MS, self.tick)

    def _poll(self):
        st = self.watcher.snapshot()
        self.running = st["running"]
        self.track_duration = st.get("duration")
        if time.time() >= self._opt_until:
            self.playing = st["playing"]
        media_position = st.get("position")
        now = time.monotonic()
        if media_position is None:
            self._media_position = None
            self._media_position_at = None
            self._last_media_position = None
        elif (self._last_media_position is None
              or abs(media_position - self._last_media_position) >= 0.25):
            self._media_position = media_position
            self._media_position_at = now
            self._last_media_position = media_position
        self._update_track_progress(now)

        if st["title"]:
            key = (st["artist"] or "Spotify", st["title"])
            if st["thumb"] and key not in self.smtc_done:
                try:
                    self.covers[key] = Image.open(io.BytesIO(st["thumb"])).convert("RGB")
                    self.smtc_done.add(key)
                    self.cover_ver += 1
                except Exception:
                    pass
            if key != self.current:
                self.current = key
                self._add_history(key)
                if key not in self.covers:
                    self.fetcher.request(key, 0)

        for key, data in self.fetcher.take().items():
            if key in self.smtc_done:
                continue
            try:
                self.covers[key] = Image.open(io.BytesIO(data)).convert("RGB")
                self.cover_ver += 1
            except Exception:
                pass

        # "playing" ist bewusst NICHT in der Signatur: Play/Pause loest keinen Voll-Rebuild aus
        sig = (self.current, self.running, self.hist_ver,
               id(self.covers.get(self.current)) if self.current else 0)
        if sig != self.last_state:
            self.last_state = sig
            self._last_playing = self.playing
            self.apply_state()
        else:
            if self.playing != self._last_playing:
                self._last_playing = self.playing
                self.apply_playing()
            if self.cover_ver != self._cover_seen and time.time() - self._last_list > 1.2:
                self.refresh_list()

        if settings.get("overlay_enabled"):
            key = self.current
            cover = self.covers.get(key) if key else None
            cover_bytes = None
            cid = id(cover) if cover is not None else 0
            if cid and cid != self._overlay_cover_id:
                self._overlay_cover_id = cid
                try:
                    buf = io.BytesIO()
                    cover.convert("RGB").save(buf, "JPEG", quality=88)
                    cover_bytes = buf.getvalue()
                except Exception:
                    cover_bytes = None
            artist, title = key if key else ("", "")
            update_overlay_state(artist, title, self.playing, self.running, cover_bytes)

        if settings.get("discord_enabled"):
            self._update_discord()
        elif discord_rpc.connected:
            discord_rpc.disconnect()

    def _update_discord(self):
        if not discord_rpc.connected:
            now = time.time()
            if not self._discord_connecting and now >= self._discord_retry_at:
                cid = settings.get("discord_client_id", "").strip()
                self._discord_retry_at = now + 10
                if not cid:
                    return
                self._discord_connecting = True

                def work():
                    ok, msg = discord_rpc.connect(cid)
                    self._discord_connecting = False
                    self.post(lambda: self._set_discord_status(ok, msg))

                threading.Thread(target=work, daemon=True).start()
            return
        key = self.current
        if not key or not self.running:
            discord_rpc.clear()
            return
        artist, title = key
        track_url = self._discord_track_url(key)
        discord_rpc.update(title, artist, self.playing, self.track_position,
                           self.track_duration, track_url)

    def _discord_track_url(self, key):
        kid = "\t".join(key)
        tid = self.ids.get(kid) or self._discord_track_ids.get(kid)
        if tid:
            return f"https://open.spotify.com/track/{tid}"
        if kid in self._discord_resolving:
            return None
        self._discord_resolving.add(kid)

        def work():
            try:
                found = resolve_track_id(key)
            except Exception:
                found = None
            if found:
                self._discord_track_ids[kid] = found
            self._discord_resolving.discard(kid)

        threading.Thread(target=work, daemon=True).start()
        return None

    def _set_discord_status(self, ok, msg):
        try:
            if ok:
                self.discord_status.configure(text="Connected", text_color=T["accent"])
            else:
                self.discord_status.configure(text=short(msg or "Not connected", 30),
                                              text_color="#F87171")
        except Exception:
            pass

    def apply_state(self):
        key = self.current
        cover = self.covers.get(key) if key else None
        for h in (self.hero_main, self.hero_keys):
            h.update(key, cover, self.playing, self.running)
        self.hero_main.set_progress(self.track_position, self.track_duration)
        self.refresh_list()

    def _update_track_progress(self, now=None):
        if self._media_position is None or self._media_position_at is None:
            self.track_position = None
        else:
            elapsed = max(0.0, (now or time.monotonic()) - self._media_position_at)
            self.track_position = self._media_position + (elapsed if self.playing else 0)
            if self.track_duration is not None:
                self.track_position = min(self.track_position, self.track_duration)
        self.hero_main.set_progress(self.track_position, self.track_duration)

    # ---------- window state ----------
    def show(self):
        load_config()
        self.refresh_keys()
        try:
            _u.ShowWindow(self._hwnd(), 9)
        except Exception:
            pass
        self.root.deiconify()
        self.root.lift()
        self.root.attributes("-topmost", True)
        self.root.after(200, lambda: self.root.attributes("-topmost", bool(settings["always_on_top"])))

    def hide(self):
        self.root.withdraw()

    def run(self):
        self.root.mainloop()


# =============================
# TRAY, SINGLE INSTANCE, MAIN
# =============================
hud = None
tray_icon = None
_instance_handles = []


def open_hud(icon=None, item=None):
    if hud:
        hud.root.after(0, hud.show)


def quit_app(icon=None, item=None):
    try:
        if tray_icon:
            tray_icon.stop()
    except Exception:
        pass
    try:
        overlay_server.stop()
    except Exception:
        pass
    try:
        discord_rpc.disconnect()
    except Exception:
        pass
    try:
        save_config()
    finally:
        os._exit(0)


def tray():
    global tray_icon
    menu = Menu(MenuItem("Open", open_hud, default=True), MenuItem("Quit", quit_app))
    tray_icon = Icon(APP_NAME, make_app_icon(64), APP_NAME, menu)
    tray_icon.run()


def ensure_single_instance():
    mutex = _k.CreateMutexW(None, False, "Local\\SpotifyControllerByAirangelic")
    already = ctypes.get_last_error() == 183
    evt = _k.CreateEventW(None, False, False, "Local\\SpotifyControllerShow")
    _instance_handles.extend([mutex, evt])
    if already:
        _k.SetEvent(evt)
        sys.exit(0)
    return evt


def watch_show_event(evt):
    while True:
        _k.WaitForSingleObject(evt, 0xFFFFFFFF)
        open_hud()


def main():
    global hud
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
    except Exception:
        pass
    load_settings()
    apply_theme(settings["look"])
    load_config()
    evt = ensure_single_instance()
    ensure_icon_file()
    if settings.get("overlay_enabled"):
        if not overlay_server.start(settings.get("overlay_port", OVERLAY_DEFAULT_PORT)):
            settings["overlay_enabled"] = False
            save_settings()
    hud = App(start_hidden="--tray" in sys.argv)
    threading.Thread(target=hotkey_loop, daemon=True).start()
    threading.Thread(target=tray, daemon=True).start()
    threading.Thread(target=watch_show_event, args=(evt,), daemon=True).start()
    hud.run()
    save_config()


if __name__ == "__main__":
    main()
