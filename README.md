# Lunch Planner for Home Assistant

*[Polski opis niżej](#polski)*

Lunch Planner draws your weekday lunches once a week from a simple meal
database and works out what to buy, and on which day, for each lunch.

It is made for people who don't cook from recipes: a lunch is either a
**soup** or a **main course**, and a main course is either one complete dish
(e.g. spaghetti) or is put together from a **main part** (pork chop), a
**starchy side** (potatoes) and a **salad or vegetables**.

The integration provides the plan, sensors and events. Notifications and
adding to a shopping list are done by automations; two ready
[blueprints](#blueprints) cover the usual setup.

## Features

- A **Lunch planner panel** in the sidebar shows today's and tomorrow's lunch,
  what to buy next, the plan and the meal database editor, ready right after
  installation.
- The meal database has five categories: soups and one-part main courses
  (single dishes); main parts, starchy sides and salads/vegetables (composed
  main courses).
- Each meal has a name, what to buy (with nothing listed, its name goes on the
  shopping list), an optional season (e.g. May–July) and a **Draw** switch:
  switched off, it stays in the database but is not drawn.
- A weekly draw plans the next week. Within a week nothing repeats as long as
  the database allows it, nothing repeats on two days in a row, and (optionally)
  last week's meals are avoided.
- What a lunch is: soup **or** main course (you choose the share of soup days),
  soup **and** main course, soup only, or main course only.
- Each lunch is bought the day before. Days without shopping (e.g. Sunday) move
  it earlier, so Monday's lunch is bought on Saturday.
- From the start of its shopping day a lunch is fixed: drawing again never
  changes a lunch whose shopping list may already be out.

## Installation

1. In Home Assistant open **Settings → Marketplace**, choose **Add from link**
   and add `https://github.com/delicatty/ha-lunch-planner` as an integration.
   (On Home Assistant 2026.10 and older: HACS → Custom repositories.)
2. Download **Lunch Planner** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Lunch Planner.**
4. Open the new panel in the sidebar and add your meals.
5. Import the [blueprints](#blueprints) for notifications.

## Settings

| Setting | Default |
|---|---|
| Lunch days | Monday–Friday |
| What each lunch is | Soup or main course, 50% soup days |
| Avoid last week's meals | on |
| Weekly draw | Saturday 09:00 (plans the week from the next Monday) |
| Days without shopping | Sunday |
| Sidebar panel | on (without it, manage meals with the actions below) |

A lunch whose shopping day comes before the weekly draw (Monday, bought on
Saturday) is drawn on its own at midnight before its shopping day.

## Blueprints

| Blueprint | What it does | Import |
|---|---|---|
| Shopping list | On a shopping day, at a set time (or once you are home), sends what to buy to a phone and adds it to to-do lists | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdelicatty%2Fha-lunch-planner%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flunch_planner%2Fshopping_list.yaml) |
| Weekly plan | Sends the plan after the weekly draw, with a **Draw again** button | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdelicatty%2Fha-lunch-planner%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flunch_planner%2Fweekly_plan.yaml) |

Their texts (title, "To buy:", button) are inputs, so write them in your language.

## Entities

| Entity | What it is |
|---|---|
| `calendar.*_lunch_plan` | The drawn plan, one all-day event per lunch |
| `sensor.*_today_s_lunch`, `sensor.*_tomorrow_s_lunch` | The lunch; parts and things to buy in attributes |
| `sensor.*_next_shopping` | Date of the next shopping day (today or later) |
| `sensor.*_to_buy` | What to buy on that day, as text (cut at 255 characters); attributes `shopping_date`, `shopping_items` (the whole list), `meals`, `summary` (one line per lunch) |
| `button.*_draw_upcoming_lunches_again` | Draws again all upcoming lunches whose shopping day has not come |

## Actions and events

- `lunch_planner.redraw` – draw again one `date`, or all upcoming lunches.
- `lunch_planner.add_meal` – add a meal (`category`, `name`, `ingredients`,
  `season_from`/`season_to`, `active`), or change the one with that name.
- `lunch_planner.remove_meal` – remove a meal by `category` and `name`.
- Event `lunch_planner_plan_updated` after every draw, with `entry_id`,
  `reason` (`weekly`, `redraw`, `missing`, `first`), `drawn` (dates),
  `meals` (every planned day from tomorrow to the end of that week: `date`,
  `label`, `meal`, `shopping_items`) and `summary` (one line per lunch).

## Upgrading

- From 0.3: notifications and adding to a shopping list moved to the
  blueprints; their settings and the "Send shopping list now" button are
  removed. Import the blueprints to keep getting them.
- From 0.2: the meals kept in to-do lists move into the meal database on their
  own, and the old to-do list entities are removed.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Home Assistant does not run on Windows, so run the tests on Linux, macOS or in
WSL. `planner.py` holds the drawing logic and has no Home Assistant imports;
`tests/test_planner.py` tests it on its own. All user-facing texts are in
`translations/*.json`; the panel reads the `panel` selector and the
integration the `notification` selector from there.

---

## Polski

Planer obiadów raz w tygodniu losuje obiady na dni robocze z prostej bazy dań
i wylicza, co i którego dnia kupić na każdy obiad.

Obiad to **zupa** albo **drugie danie**. Drugie danie jest jednoskładnikowe
(np. spaghetti) albo składa się ze **składnika głównego** (kotlet), **dodatku
skrobiowego** (ziemniaki) i **surówki lub warzyw**.

- Po instalacji w pasku bocznym pojawia się panel z obiadem na dziś i jutro,
  tym, co kupić, planem i bazą dań.
- Bazę dań edytujesz w tym panelu. Każde danie ma nazwę, listę „Co kupić”
  (pusta: na listę zakupów trafia nazwa), opcjonalny sezon (np. maj–lipiec)
  i przełącznik **Losuj**: wyłączone danie zostaje w bazie, ale nie jest
  losowane.
- Losowanie raz w tygodniu (domyślnie sobota 9:00) planuje tydzień od
  najbliższego poniedziałku, bez powtórek w tygodniu i dzień po dniu, a jeśli
  się da, także bez dań z poprzedniego tygodnia.
- Zakupy na obiad robi się dzień wcześniej. W dni bez zakupów (domyślnie
  niedziela) przechodzą na wcześniejszy dzień: obiad na poniedziałek kupujesz
  w sobotę. Od początku dnia zakupów obiad jest ustalony.
- Powiadomienia i dopisywanie do listy zakupów robią automatyzacje: gotowe
  blueprinty „Shopping list” i „Weekly plan” zaimportujesz przyciskami
  w tabeli [Blueprints](#blueprints). Ich teksty wpisujesz po polsku.

Instalacja: **Ustawienia → Marketplace → Dodaj z linku**
`https://github.com/delicatty/ha-lunch-planner`, potem restart i **Dodaj
integrację → Lunch Planner**.

## License

MIT
