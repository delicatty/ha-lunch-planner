# AGENTS.md

Project-specific decisions and pitfalls for AI coding agents. What the code
does is described in [README.md](README.md); keep it in sync with any change
in behaviour, options, entities, actions or blueprints.

## Design rules

- **The integration sends no notifications.** It exposes data (sensors, the
  plan calendar, the `lunch_planner_plan_updated` event with a `summary`
  field); notifications and to-do lists are handled by the blueprints in
  `blueprints/automation/lunch_planner/`. Keep it that way.
- **`planner.py` has no Home Assistant imports**, so the drawing logic is
  tested on its own. Keep HA code in `manager.py` and the platforms.
- **Every user-facing string lives in `translations/*.json`**, never in Python
  or JS. Texts that have no translation category in HA are stored as options
  of two selectors: `panel` (read by `panel.js`) and `notification` (read by
  `texts.py`). Add new strings there, in every language file.
  `strings.json` must be an exact copy of `translations/en.json`.
- **Don't depend on entity IDs.** HA generates them from the planner's name in
  the server language. The panel finds entities by unique ID; blueprints take
  entities as inputs.
- **The meal database is in the integration's store**, edited in the panel or
  with `add_meal` / `remove_meal`. The panel API
  (`lunch_planner/meals/subscribe|save|delete`) is subscription-only, so tools
  that read states or call services cannot list the meals. The panel's plan
  list comes from `lunch_planner/plan/subscribe` (lunches from today on); it
  replaced HA's calendar card, which always shows 7 days from today, past
  lunches included.
- **Only admins change the meal database or draw again.** HA has no
  per-action or per-entity permissions, so every entry point checks it: the
  panel's write commands use `websocket_api.require_admin`; actions and the
  button call `permissions.async_check_admin` (a call without a user, i.e. an
  automation, passes). The panel hides editing for other users, but that is
  only convenience. Any new write path needs the same check and a test.
- Internal option keys stay stable when labels change: rename the label in
  the translation files, not the key.
- A lunch is locked from the start of the day its shopping list goes out;
  redraws must never change it. A missing lunch whose list is due is drawn at
  midnight.
- Panel conventions: meal lists sorted with `Intl.Collator` in the user's
  language; disabled meals greyed out with a "not drawn" badge; Ctrl+Enter
  saves the edit dialog; the redraw tile asks for confirmation (hold and
  double-tap actions are off). The panel is plain JS with no build step.

## Versions and releases

- **Bump the version in `manifest.json` on every change to `panel.js`**: it is
  part of the script URL (`panel.js?v=<version>`) and forces browsers to load
  the new script.
- A release is a push to `main`; users update through HACS / Marketplace.
  Release commit messages start with the version, e.g.
  `0.6.1: first day of the week, clearer option names`.
- When a blueprint changes, say in the README (Upgrading) that it must be
  imported again with overwrite.

## Tests

- Home Assistant (and `pytest-homeassistant-custom-component`) does not run
  on native Windows. On Windows, run the tests and any development instance
  in WSL; don't try to make them work natively.
- Run plain `pytest`, not `python -m pytest`, as CI does: `pyproject.toml`
  sets `pythonpath = ["."]` for that. To catch files missing from git, run it
  on a clean export of the tracked files.
- The panel tests serve the HA frontend, so the `frontend` integration's
  requirements must be installed; `.github/workflows/ci.yml` shows how.
- In blueprint tests the `notify.mobile_app_*` action is checked by its schema
  only: importing `mobile_app` pulls in integrations with native dependencies.

## Checking in a development Home Assistant

- Without a C/C++ compiler the frontend may not load because of the native
  packages `pymicro_vad` and `pyspeex_noise`. Empty stub packages with those
  names in the venv are enough for a development instance.
- To see blueprint notifications, register a fake phone through the
  `mobile_app` registration API with a `push_url` pointing to a small local
  HTTP receiver.
