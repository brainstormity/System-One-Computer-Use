# System One Computer Use

> **Prototype / proof of concept.** This is a working prototype to learn from and build on.
> **Don't use it in production.** It controls your real mouse and keyboard, has no safety checks beyond a
> confidence threshold, and can click, type and post on your accounts. Watch it while it runs.
>
> It hasn't been extensively tested across different scenarios, sites or setups. Expect it to get stuck or
> make mistakes, and expect to adapt it to your own needs.
>
> **Tested on:** macOS with Brave, Python 3.14. Windows and Linux are untested; typing by paste, copying links
> and closing tabs only work on macOS.

Controls your computer, or an Android phone, with screenshots. In a loop:

1. Take a screenshot.
2. Ask JEV what to do next: click, type, press Enter, scroll, open a website, or stop because it's done.
3. Do it with `pyautogui`.

The agent is one file, [`jev_agent.py`](jev_agent.py). [`phone.py`](phone.py) adds Android phones (Mobile Use).
A small web dashboard, [`dashboard.py`](dashboard.py), runs tasks and shows reports.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then put your TYPESAFE_API_KEY in .env
```

On macOS, open **System Settings → Privacy & Security**. Under **Screen Recording** and
**Accessibility**, allow the app you run this from, such as Terminal.

## Run from the dashboard

```bash
python dashboard.py
```

This opens http://127.0.0.1:8000. Type a task and press **Run**, or press **Dry run** to open the website and see JEV's first decision without any clicking or typing.

**Experimental:** when a run succeeds, it tries to close the browser tabs it opened (only those, by tab ID, in
your default browser; Brave, Chrome, Edge and Arc, not Safari). This doesn't work reliably yet: if it can't
find its tabs, the run shows a red warning and leaves them open. Untick **Close the tabs it opened** to turn it
off. If a run fails or stops, its tabs always stay open so you can see where it got stuck.

When a run ends, the agent switches back to the System One Computer Use tab. The first time, macOS asks whether
Terminal may control your browser: click **OK**, or the dashboard opens in a new tab instead.

Every run gets a step-by-step report. Each step shows:

- the screenshot JEV saw, with a red box and circle on what it clicked
- the action it picked: click at (x, y), type "…", open website, and so on
- how sure JEV was, and the other options it considered
- roughly what it cost (JEV charges $0.042 per million input tokens; output is free)
- whether the action was carried out

If JEV is less than 50% sure of a click, typing, Enter or paste, the agent stops and does nothing, rather than
guessing. Harmless actions (copy link, open website, scroll, wait) only need 25%.

To remove a run, click its trash icon. It moves to the **Trash** tab, where you can restore it, or tick runs
(or **Select all**) and press **Delete forever**.

## Run from the terminal

```bash
python jev_agent.py 'Go to x.com and post "Hello from my JEV agent!"'
```

- **Put messages it should type in "quotes".** JEV picks options and points at things, but it can't write its own text. It can type words from your task, like a search term, and it can copy a page's link and paste it.
- Name websites like `x.com`, or common sites by name (`wikipedia`, `youtube`, `github`…). The first one opens in your default browser before JEV looks at the screen.
- `--step` asks you to press Enter before each action, which is useful for first tries.
- `--dry-run` opens the website, prints JEV's first decision, and doesn't click or type.
- **Emergency stop:** move the mouse into any screen corner, or press Ctrl+C.

Each run is saved in `runs/<time>/`: the screenshots plus `report.json`.

Make sure you're already logged in to sites like X. The agent can't log in for you.

## Mobile Use (Android)

The same agent can control an Android phone connected to your Mac. It sees the phone's screen and taps, types,
swipes and uses the Back and Home buttons, so it can move between apps like you would. For example:

> Open X and post a tweet with the text "Hello from my phone!"

It opens the X app, taps the compose button, types the text and taps Post.

**Setup (once):**

1. Install adb, Google's tool for controlling Android phones: `brew install --cask android-platform-tools`
2. On the phone: **Settings → About phone**, tap **Build number** 7 times. Then **Settings → System →
   Developer options**: turn on **USB debugging** (and **USB debugging (Security settings)** if your phone has it).
3. Plug the phone in by USB, unlock it and tap **Allow** on "Allow USB debugging?" (tick **Always allow**).

**No phone? Use the Android emulator.** Google's free emulator runs a virtual Android phone in a window on
your Mac, and the agent controls it exactly like a real one. About 3 GB of downloads (Apple Silicon Macs;
on Intel Macs use `x86_64` instead of `arm64-v8a`):

```bash
brew install openjdk@21
brew install --cask android-commandlinetools android-platform-tools
export JAVA_HOME=/opt/homebrew/opt/openjdk@21 ANDROID_HOME=/opt/homebrew/share/android-commandlinetools
sdkmanager --licenses   # read and accept Google's Android SDK license
sdkmanager "platform-tools" "emulator" "platforms;android-35" "system-images;android-35;google_apis_playstore;arm64-v8a"
avdmanager create avd -n SystemOnePhone -d pixel_7 -k "system-images;android-35;google_apis_playstore;arm64-v8a"
$ANDROID_HOME/emulator/emulator -avd SystemOnePhone
```

The last command opens the virtual phone (run it again whenever you want it). Inside it, open the Play
Store, sign in with a Google account and install the apps you want the agent to use (X, Instagram…).

**Run:** in the dashboard, choose **📱 Android phone** (it shows whether your phone is connected), or:

```bash
python jev_agent.py --android 'Open X and post a tweet with the text "Hello from my phone!"'
```

- **Apps named in your task open directly** if they're installed (X, Instagram, WhatsApp, YouTube, Chrome,
  Gmail, Spotify… see `KNOWN_APPS` in `phone.py`). Other apps it finds on the home screen like you would.
- **Typing is plain text only**: adb can't type emoji or accented letters.
- **Not yet on the phone:** copying a link and pasting it. **iPhone isn't supported**: iOS doesn't let
  one app see or tap other apps.
- **To stop it**, press **Stop** in the dashboard or unplug the phone. Be logged in to apps first.

## How it works (for building on it)

Everything happens in `run_task()` in [`jev_agent.py`](jev_agent.py):

1. **Screenshot** with `mss`, shrunk to fit JEV's image limits.
2. **One JEV request per step** (`ask_jev()`), with three questions about the same screenshot:
   - a `choice` question: which action from `ACTIONS` comes next
   - a `box` question: where on the screen to click
   - a `choice` question: which text to type
3. **Zoom in if needed.** When JEV is unsure where to click or tap (under 60%), or the last click at that spot
   did nothing, it asks again on an enlarged close-up of that area (`refine_target()`). Small targets like
   the numbers on a clock dial need this.
4. **Do it** with `pyautogui`, then wait until the screen has reacted and settled (`wait_for_screen()`).
5. **Save the step** to `runs/<time>/report.json` with its screenshot, and repeat until JEV picks `DONE`.

JEV picks from options; it never writes free text. So the agent offers it only:

- the actions in `ACTIONS`
- text from your task: quoted text, plus every 1–3 word phrase as a search term
- websites named in your task

A side effect: text on a web page can't make the agent type something that isn't in your task.

**Adding an action:** add a line to `ACTIONS` with a plain description (JEV reads it), then handle it in the
`# Do it.` block in `run_task()`.

**Tuning:** `MIN_CONFIDENCE` and `MIN_CONFIDENCE_HARMLESS` decide when it stops instead of guessing. `MAX_STEPS`
caps a run.

**Mobile Use** swaps only the "eyes and hands": `phone.py` takes the screenshot and taps, swipes and types
over adb, and `PHONE_ACTIONS` gives JEV the phone's actions (tap, swipe, Back, Home, open app…). The loop,
waiting logic and reports are shared.

**The dashboard** ([`dashboard.py`](dashboard.py) and [`dashboard.html`](dashboard.html)) uses only Python's
standard library. It runs `run_task()` in a background thread and reads the same `report.json` files.

## Security

- **Your API key** stays in `.env`, which git ignores. Screenshots of your screen are sent to TypeSafe.
- **The dashboard** only listens on this computer (`127.0.0.1`). It only accepts requests from its own page,
  so other websites open in your browser can't start tasks or delete runs.
- **The agent controls your real mouse and keyboard.** Watch it, and use the emergency stop (move the mouse
  into a screen corner) if it does something unexpected.
