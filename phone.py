"""
Mobile Use: the Android phone's "eyes and hands", over adb (USB or Wi-Fi).

    screenshot -> tap / swipe / type / back / home / open app

The agent loop in jev_agent.py is the same for the computer and the phone; only this part changes.
Setup: install adb (brew install --cask android-platform-tools), turn on USB debugging on the phone,
plug it in and tap "Allow" on the phone.
"""
from __future__ import annotations

import io
import re
import shlex
import shutil
import subprocess

from PIL import Image

# App names people write in tasks -> Android package names. The app must be installed to be offered.
KNOWN_APPS = {
    "x": "com.twitter.android", "twitter": "com.twitter.android", "instagram": "com.instagram.android",
    "whatsapp": "com.whatsapp", "youtube": "com.google.android.youtube", "chrome": "com.android.chrome",
    "gmail": "com.google.android.gm", "google maps": "com.google.android.apps.maps",
    "maps": "com.google.android.apps.maps", "spotify": "com.spotify.music", "facebook": "com.facebook.katana",
    "messenger": "com.facebook.orca", "telegram": "org.telegram.messenger", "tiktok": "com.zhiliaoapp.musically",
    "reddit": "com.reddit.frontpage", "linkedin": "com.linkedin.android", "snapchat": "com.snapchat.android",
    "discord": "com.discord", "slack": "com.Slack", "uber": "com.ubercab", "netflix": "com.netflix.mediaclient",
    "settings": "com.android.settings", "play store": "com.android.vending", "google": "com.google.android.googlequicksearchbox",
    "messages": "com.google.android.apps.messaging", "phone": "com.google.android.dialer",
    "camera": "com.android.camera", "calendar": "com.google.android.calendar", "photos": "com.google.android.apps.photos",
}
KEYS = {"BACK": "KEYCODE_BACK", "HOME": "KEYCODE_HOME", "ENTER": "KEYCODE_ENTER"}


def apps_in_task(task, installed):
    """Apps named in the task that are installed, in the order they appear: [(name, package)].
    "X" only counts in capitals (so the letter x in other words doesn't), other names in any case."""
    found = []
    for name, package in KNOWN_APPS.items():
        pattern = r"\bX\b" if name == "x" else r"\b" + re.escape(name) + r"\b"
        match = re.search(pattern, task, 0 if name == "x" else re.IGNORECASE)
        if match and package in installed:
            found.append((match.start(), name, package))
    seen, apps = set(), []
    for _, name, package in sorted(found):
        if package not in seen:
            seen.add(package)
            apps.append((name, package))
    return apps


class AndroidPhone:
    def __init__(self, serial=None):
        self.adb_path = shutil.which("adb")
        if not self.adb_path:
            raise RuntimeError("adb isn't installed. Run: brew install --cask android-platform-tools")
        devices = self.devices()
        ready = [d for d in devices if d["state"] == "device"]
        if serial:
            ready = [d for d in ready if d["serial"] == serial]
        if not ready:
            if any(d["state"] == "unauthorized" for d in devices):
                raise RuntimeError("The phone hasn't allowed this computer yet. Unlock it and tap Allow on the "
                                   "\"Allow USB debugging?\" prompt (tick Always allow).")
            raise RuntimeError("No Android phone connected. Plug one in by USB with Developer options → "
                               "USB debugging turned on, or start the Android emulator (see README), then try again.")
        self.serial = ready[0]["serial"]
        self.name = ready[0]["model"] or self.serial
        self.width = self.height = None  # real screen pixels, set by the first screenshot
        self._installed = None

    def devices(self):
        out = subprocess.run([self.adb_path, "devices", "-l"], capture_output=True, text=True, timeout=10).stdout
        found = []
        for line in out.splitlines()[1:]:
            parts = line.split()
            if len(parts) >= 2:
                model = next((p.split(":", 1)[1] for p in parts if p.startswith("model:")), "")
                found.append({"serial": parts[0], "state": parts[1], "model": model.replace("_", " ")})
        return found

    def adb(self, *args, timeout=15, binary=False):
        result = subprocess.run([self.adb_path, "-s", self.serial, *args], capture_output=True,
                                timeout=timeout, text=not binary)
        if result.returncode != 0:
            err = result.stderr if not binary else result.stderr.decode(errors="replace")
            raise RuntimeError(f"adb {' '.join(args[:2])} failed: {err.strip()[:200]} (is the phone still connected?)")
        return result.stdout

    def shell(self, command, timeout=15):
        return self.adb("shell", command, timeout=timeout)

    def screenshot(self):
        """The phone's screen, shrunk to fit JEV's image limits (max 1568px per side)."""
        img = Image.open(io.BytesIO(self.adb("exec-out", "screencap", "-p", binary=True))).convert("RGB")
        self.width, self.height = img.size
        img.thumbnail((1568, 1568))
        return img

    # The "hands". x and y are real screen pixels.
    def tap(self, x, y):
        self.shell(f"input tap {int(x)} {int(y)}")

    def long_press(self, x, y):
        self.shell(f"input swipe {int(x)} {int(y)} {int(x)} {int(y)} 700")

    def swipe(self, direction):
        """Swipe a finger across the middle of the screen: "up" scrolls content down, and so on."""
        w, h = self.width, self.height
        start, end = {"up": ((w / 2, h * 0.70), (w / 2, h * 0.30)), "down": ((w / 2, h * 0.30), (w / 2, h * 0.70)),
                      "left": ((w * 0.85, h / 2), (w * 0.15, h / 2)), "right": ((w * 0.15, h / 2), (w * 0.85, h / 2))}[direction]
        self.shell(f"input swipe {int(start[0])} {int(start[1])} {int(end[0])} {int(end[1])} 300")

    def all_apps(self):
        """Open the app drawer: go home, then swipe up from the bottom edge."""
        self.key("HOME")
        w, h = self.width, self.height
        self.shell(f"input swipe {int(w / 2)} {int(h * 0.92)} {int(w / 2)} {int(h * 0.25)} 300")

    def key(self, name):
        self.shell(f"input keyevent {KEYS[name]}")

    def type_text(self, text):
        """Type into the focused field. adb can only type plain ASCII (no emoji or accented letters)."""
        if not text.isascii():
            raise RuntimeError("Typing on Android over adb only supports plain text without emoji or accents: "
                               f"{text!r}")
        # `input text` reads %s as a space; quote the rest for the phone's shell.
        self.shell("input text " + shlex.quote(text.replace(" ", "%s")))

    def open_app(self, package):
        """Start the app's main screen, like tapping its icon."""
        out = self.shell("cmd package resolve-activity --brief -a android.intent.action.MAIN "
                         f"-c android.intent.category.LAUNCHER {shlex.quote(package)}")
        component = next((line.strip() for line in reversed(out.splitlines()) if "/" in line), None)
        if not component:
            raise RuntimeError(f"Couldn't find how to open {package} on the phone.")
        self.shell(f"am start -n {shlex.quote(component)}")

    def open_url(self, url):
        self.shell("am start -a android.intent.action.VIEW -d " + shlex.quote(url))

    def installed(self):
        if self._installed is None:
            out = self.shell("pm list packages")
            self._installed = {line.split(":", 1)[1].strip() for line in out.splitlines() if ":" in line}
        return self._installed
