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

Controls your computer with screenshots. In a loop:

1. Take a screenshot.
2. Ask JEV what to do next: click, type, press Enter, scroll, open a website, or stop because it's done.
3. Do it with `pyautogui`.

The agent is one file, [`jev_agent.py`](jev_agent.py). A small web dashboard, [`dashboard.py`](dashboard.py), runs tasks and shows reports.

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

## How it works (for building on it)

Everything happens in `run_task()` in [`jev_agent.py`](jev_agent.py):

1. **Screenshot** with `mss`, shrunk to fit JEV's image limits.
2. **One JEV request per step** (`ask_jev()`), with three questions about the same screenshot:
   - a `choice` question: which action from `ACTIONS` comes next
   - a `box` question: where on the screen to click
   - a `choice` question: which text to type
3. **Do it** with `pyautogui`, then wait until the screen has reacted and settled (`wait_for_screen()`).
4. **Save the step** to `runs/<time>/report.json` with its screenshot, and repeat until JEV picks `DONE`.

JEV picks from options; it never writes free text. So the agent offers it only:

- the actions in `ACTIONS`
- text from your task: quoted text, plus every 1–3 word phrase as a search term
- websites named in your task

A side effect: text on a web page can't make the agent type something that isn't in your task.

**Adding an action:** add a line to `ACTIONS` with a plain description (JEV reads it), then handle it in the
`# Do it.` block in `run_task()`.

**Tuning:** `MIN_CONFIDENCE` and `MIN_CONFIDENCE_HARMLESS` decide when it stops instead of guessing. `MAX_STEPS`
caps a run.

**The dashboard** ([`dashboard.py`](dashboard.py) and [`dashboard.html`](dashboard.html)) uses only Python's
standard library. It runs `run_task()` in a background thread and reads the same `report.json` files.

## Security

- **Your API key** stays in `.env`, which git ignores. Screenshots of your screen are sent to TypeSafe.
- **The dashboard** only listens on this computer (`127.0.0.1`). It only accepts requests from its own page,
  so other websites open in your browser can't start tasks or delete runs.
- **The agent controls your real mouse and keyboard.** Watch it, and use the emergency stop (move the mouse
  into a screen corner) if it does something unexpected.
