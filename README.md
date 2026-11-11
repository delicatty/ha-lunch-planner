# Lunch Planner for Home Assistant

*[Polski opis niżej](#polski)*

Lunch Planner draws your weekday lunches once a week from a simple meal
database and sends you the shopping list the day before each lunch.

It is made for people who don't cook from recipes: a lunch is either a
**soup** or a **main course**, and a main course is either one complete dish
(e.g. spaghetti) or is put together from a **main part** (pork chop), a
**starchy side** (potatoes) and a **salad or vegetables**.

## Features

- A **Lunch planner panel** in the sidebar shows today's and tomorrow's lunch,
  the plan and the meal database, ready right after installation.
- The meal database is five to-do lists you edit in that panel: soups, one-part
  main courses, main parts, starchy sides, salads/vegetables. They are hidden
  from the To-do panel so they don't clutter it.
- In an item's description you list what to buy for it, one thing per line or
  separated by commas. With no description, the item's name goes on the list.
- Seasonal items: a `season: 5-7` line limits an item to May–July.
- Ticking an item off keeps it in the database but stops it from being drawn.
- A weekly draw plans the next week. Within a week nothing repeats as long as
  the database allows it, nothing repeats on two days in a row, and (optionally)
  last week's meals are avoided.
- What a lunch is: soup **or** main course (you choose the share of soup days),
  soup **and** main course, soup only, or main course only.
- The plan is a calendar ("Lunch: mushroom soup"), plus "today's lunch" and
  "tomorrow's lunch" sensors.
- The weekly plan is sent as a notification with a **Draw again** button.
- The shopping list is sent the day before each lunch, at a set time or when you
  get home. Days without shopping (e.g. Sunday) move it earlier, so Monday's
  lunch is bought on Saturday.
- The things to buy can also be added to any to-do list, e.g. your shopping list.
- A lunch whose shopping is done is never drawn again by accident.

## Installation

1. In Home Assistant open **Settings → Marketplace**, choose **Add from link**
   and add `https://github.com/delicatty/ha-lunch-planner` as an integration.
   (On Home Assistant 2026.10 and older: HACS → Custom repositories.)
2. Download **Lunch Planner** and restart Home Assistant.
3. **Settings → Devices & services → Add integration → Lunch Planner.**
4. Open the new panel in the sidebar and fill the meal database.

## Settings

| Setting | Default |
|---|---|
| Lunch days | Monday–Friday |
| What each lunch is | Soup or main course, 50% soup days |
| Avoid last week's meals | on |
| Weekly draw | Saturday 09:00 (plans the week from the next Monday) |
| Shopping list | at 17:00, or when you get home after 17:00 |
| Days without shopping | Sunday |
| Notifications | none: choose your phone's notify action |
| Shopping to-do list | none |
| Sidebar panel | on (turning it off: unhide the database lists in their entity settings) |

The weekly draw must come before the shopping for the first lunch of the week.
If it hasn't run yet when that shopping is due, the missing days are drawn then.

## Entities

| Entity | What it is |
|---|---|
| `todo.*` (5) | The meal database (hidden; edited in the panel or any to-do list card) |
| `calendar.*_lunch_plan` | The drawn plan, one all-day event per lunch |
| `sensor.*_today_s_lunch`, `sensor.*_tomorrow_s_lunch` | The lunch; ingredients in attributes |
| `sensor.*_next_shopping` | Date of the next shopping list; meals and items in attributes |
| `button.*_draw_upcoming_lunches_again` | Draws again all upcoming lunches not yet shopped for |
| `button.*_send_shopping_list_now` | Sends today's shopping list now |

## Actions

- `lunch_planner.redraw` – draw again one `date`, or all upcoming lunches.
- `lunch_planner.send_shopping_list` – send today's shopping list now.

The event `lunch_planner_plan_updated` fires after every draw.

## Development

```bash
python -m venv .venv
.venv/bin/pip install -r requirements_test.txt
.venv/bin/pytest
```

Home Assistant does not run on Windows, so run the tests on Linux, macOS or in
WSL. `planner.py` holds the drawing logic and has no Home Assistant imports;
`tests/test_planner.py` tests it on its own.

---

## Polski

Planer obiadów raz w tygodniu losuje obiady na dni robocze z prostej bazy dań
i dzień wcześniej przysyła listę zakupów.

Obiad to **zupa** albo **drugie danie**. Drugie danie jest jednoskładnikowe
(np. spaghetti) albo składa się ze **składnika głównego** (kotlet), **dodatku
skrobiowego** (ziemniaki) i **surówki lub warzyw**.

- Po instalacji w pasku bocznym pojawia się panel z obiadem na dziś i jutro,
  planem i bazą dań.
- Baza dań to pięć list zadań, które edytujesz w tym panelu (w panelu list zadań
  są ukryte). W opisie pozycji wpisz, co kupić (w osobnych liniach albo po
  przecinku). Bez opisu na listę trafia nazwa.
- Linia `sezon: 5-7` ogranicza pozycję do maja–lipca. Odhaczona pozycja nie
  jest losowana.
- Losowanie raz w tygodniu (domyślnie sobota 9:00) planuje tydzień od
  najbliższego poniedziałku, bez powtórek w tygodniu i dzień po dniu, a jeśli
  się da, także bez dań z poprzedniego tygodnia.
- Plan przychodzi powiadomieniem z przyciskiem **Losuj ponownie** i jest
  widoczny w kalendarzu.
- Lista zakupów przychodzi dzień przed obiadem o ustalonej godzinie albo po
  powrocie do domu. W dni bez zakupów (domyślnie niedziela) przechodzi na
  wcześniejszy dzień: obiad na poniedziałek kupujesz w sobotę.

Instalacja: **Ustawienia → Marketplace → Dodaj z linku**
`https://github.com/delicatty/ha-lunch-planner`, potem restart i **Dodaj
integrację → Lunch Planner**.

## License

MIT
