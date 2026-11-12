# Lunch Planner for Home Assistant

*[Polski opis niżej](#polski)*

Lunch Planner draws your lunches (on work days, weekends or every day) once a
week from a simple meal database and works out what to buy, and on which day, for each lunch.

It is made for people who don't cook from recipes: a lunch is either a
**soup** or a **main course**, and a main course is either one complete dish
(e.g. spaghetti) or is put together from a **main part** (pork chop), a
**starchy side** (potatoes) and a **salad or vegetables**.

The integration provides the plan, sensors and events. Notifications and
adding to a shopping list are done by automations; two ready
[blueprints](#blueprints) cover the usual setup.

## Features

- A **Lunch planner panel** in the sidebar, ready right after installation,
  has two tabs: **Plan** (the plan calendar, today's and tomorrow's lunch,
  what to buy next) and **Meal database** (the meal editor). **Draw upcoming lunches again** sits in an *Actions* section under the plan
  tiles and asks for confirmation. In the meal editor Ctrl+Enter saves.
- Only Home Assistant admins change the meal database and draw lunches again
  (in the panel, with the button or with the actions). Other users see the
  plan and the meal database read-only. Automations may always do both.
- The meal database has five categories: soups and one-part main courses
  (single dishes); main parts, starchy sides and salads/vegetables (composed
  main courses).
- Each meal has a name, what to buy (with nothing listed, its name goes on the
  shopping list), an optional season (e.g. May–July) and an **Include in the draw** switch:
  switched off, it stays in the database but is not drawn.
- A weekly draw plans the next week. Within a week nothing repeats as long as
  the database allows it, nothing repeats on two days in a row, and (optionally)
  last week's meals are avoided.
- What a lunch is: **one course** (soup or a main course; you choose the share
  of soup days), **two courses** (soup and a main course), soup only, or main
  course only.
- Lunches on your work days (Monday–Friday by default), on the other days
  (weekends), or every day.
- Days off: a day with an all-day event in a chosen calendar has no lunch, e.g.
  public holidays from the built-in **Holiday** integration, or a holiday trip
  in your own calendar. A day off added after the draw drops its lunch at
  midnight, unless its shopping list is already out.
- Each lunch is bought the day before. Days without shopping (e.g. Sunday, and
  public holidays from the Holiday integration) move it earlier, so Monday's
  lunch is bought on Saturday. When that would be 3 days or more before the
  lunch (e.g. after Easter), it is bought in the morning of the lunch day
  instead, and the shopping list goes out the evening before.
- From the start of the day its shopping list goes out a lunch is fixed:
  drawing again never changes a lunch whose shopping list may already be out.

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
| When to have lunch | On work days |
| Work days | Monday–Friday (weekends are the other days) |
| What each lunch is | One course, 50% soup days |
| Avoid last week's meals | on |
| First day of the week | From the country set in Home Assistant (Monday in most of Europe, Sunday e.g. in the US) |
| Weekly draw | Saturday 09:00 (plans the next week) |
| Days without shopping | Sunday |
| Days-off and holiday calendars | none (e.g. the Holiday integration's calendar for your country) |
| Shops closed on public holidays | on (only the Holiday integration's calendars; a holiday trip cancels lunches only) |
| Lunch time, lunch length | 13:00, 30 minutes (each lunch is an event in the plan calendar) |
| Sidebar panel | on (without it, manage meals with the actions below) |

Best set the weekly draw before the shopping for the first lunch of the week.
A lunch whose shopping comes before the draw (e.g. Monday's, bought on
Saturday) is drawn on its own at midnight before its shopping day.

## Blueprints

| Blueprint | What it does | Import |
|---|---|---|
| Shopping list | On a shopping day (or the evening before shopping in the morning), at a set time or as you leave work, sends what to buy to a phone and adds it to to-do lists | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdelicatty%2Fha-lunch-planner%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flunch_planner%2Fshopping_list.yaml) |
| Weekly plan | Sends the plan after the weekly draw, with a **Draw again** button | [![Import](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fdelicatty%2Fha-lunch-planner%2Fblob%2Fmain%2Fblueprints%2Fautomation%2Flunch_planner%2Fweekly_plan.yaml) |

Their texts (title, "To buy:", "To buy tomorrow morning:", button) are inputs,
so write them in your language.

The shopping list goes out once a day, at the set time (17:00 by default).
With a person and a work zone set under **Leaving work**, it can catch you on
the way home instead:

- If you are in the work zone at the set time, the list goes out as you leave
  it.
- Leaving work after the earliest time (15:00 by default) sends it right away,
  also before the set time; leaving earlier (e.g. for a lunch break) does not.
- If you are still at work at the latest time (20:00 by default), it goes out
  anyway.

## Entities

All entities belong to one device per planner, named after the planner
(`Lunch planner` by default). Find them under **Settings → Devices & services
→ Devices**.

| Entity | What it is |
|---|---|
| Lunch plan (calendar) | The drawn plan, one event per lunch, at the lunch time |
| Today's lunch, Tomorrow's lunch (sensors) | The lunch; parts and things to buy in attributes |
| Next shopping (sensor) | Date of the next shopping day (today or later) |
| To buy (sensor) | What to buy on that day, as text (cut at 255 characters); attributes `shopping_date`, `shopping_morning` (bought in the morning of the lunch day), `list_date` (when the list goes out), `shopping_items` (the whole list), `meals`, `summary` (one line per lunch) |
| Draw upcoming lunches again (button) | Draws again all upcoming lunches whose shopping list is not out yet |

Entity IDs are made by Home Assistant, not by the integration, from the
planner's name and the entity's name in the language of your Home Assistant
(English for languages not written in the Latin alphabet). So the "To buy"
sensor is `sensor.lunch_planner_to_buy` with the default name in English, and
`sensor.obiady_do_kupienia` in Polish. The blueprints and the panel do not
depend on entity IDs: blueprints let you pick the entities, the panel finds
them by their unique IDs.

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

- From 0.5: the list of lunch days becomes the list of work days, with lunches
  on work days, so nothing changes. Import the shopping list blueprint again
  (with overwrite) for the morning shopping list.
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

Planer obiadów raz w tygodniu losuje obiady (w dni robocze, w weekendy albo
codziennie) z prostej bazy posiłków
i wylicza, co i którego dnia kupić na każdy obiad.

Obiad to **zupa** albo **drugie danie**. Drugie danie ma ustalony skład
(np. spaghetti albo kurczak z ryżem i warzywami) albo składa się z losowanych
części: **składnika głównego** (kotlet), **dodatku skrobiowego** (ziemniaki)
i **surówki lub warzyw**.

- Po instalacji w pasku bocznym pojawia się panel z dwiema zakładkami:
  **Plan** (kalendarz planu, obiad na dziś i jutro, co kupić) i **Baza posiłków**
  (edytor bazy). Przycisk „Losuj ponownie nadchodzące
  obiady” jest w sekcji „Akcje” pod kafelkami planu i pyta o potwierdzenie. W oknie
  edycji pozycji Ctrl+Enter zapisuje.
- Bazę posiłków zmieniają i ponownie losują obiady tylko administratorzy Home
  Assistanta (w panelu, przyciskiem i akcjami). Pozostali użytkownicy widzą
  plan i bazę bez możliwości zmian. Automatyzacje mogą zawsze.
- Każdy obiad to w kalendarzu planu wydarzenie o godzinie obiadu (domyślnie
  13:00) i o ustawionej długości (domyślnie 30 minut).
- Bazę posiłków edytujesz w tym panelu. Ma dwie grupy: **Posiłki o ustalonym
  składzie** (zupa, drugie danie) i **Części posiłku składanego** (składnik
  główny, dodatek skrobiowy, surówka / warzywa). Każda pozycja ma nazwę, listę „Co kupić”
  (pusta: na listę zakupów trafia nazwa), opcjonalny sezon (np. maj–lipiec)
  i przełącznik **Uwzględniaj w losowaniu**: wyłączona pozycja zostaje w bazie, ale nie
  jest losowana.
- Obiad to jedno danie (zupa albo drugie danie), dwa dania (zupa i drugie
  danie), tylko zupa albo tylko drugie danie.
- Losowanie raz w tygodniu (domyślnie sobota 9:00) planuje następny tydzień
  (pierwszy dzień tygodnia ustawiasz, domyślnie wynika z kraju w ustawieniach
  Home Assistanta), bez powtórek w tygodniu i dzień po dniu, a jeśli
  się da, także bez dań z poprzedniego tygodnia.
- Dni robocze ustawiasz sama (domyślnie pn–pt); weekendy to pozostałe dni.
- Dni wolne: w dzień z wydarzeniem całodniowym w wybranym kalendarzu nie ma
  obiadu, np. święta z wbudowanej integracji **Holiday** albo urlop we własnym
  kalendarzu. Dzień wolny dodany po losowaniu usuwa obiad o północy, chyba że
  lista zakupów na niego już wyszła.
- Zakupy na obiad robi się dzień wcześniej. W dni bez zakupów (domyślnie
  niedziela, a przy opcji „Sklepy nieczynne w święta” także święta z integracji
  Holiday) przechodzą na wcześniejszy dzień: obiad na poniedziałek kupujesz
  w sobotę. Gdy wypadłoby to 3 dni lub więcej przed obiadem (np. po
  Wielkanocy), kupujesz go rano w dniu obiadu, a lista przychodzi wieczorem
  dzień wcześniej. Od początku dnia, w którym wychodzi lista, obiad jest ustalony.
- Powiadomienia i dopisywanie do listy zakupów robią automatyzacje: gotowe
  blueprinty „Shopping list” i „Weekly plan” zaimportujesz przyciskami
  w tabeli [Blueprints](#blueprints). Ich teksty wpisujesz po polsku.
  Lista zakupów przychodzi raz dziennie o ustawionej godzinie (domyślnie
  17:00). Gdy w sekcji „Leaving work” wybierzesz osobę i strefę pracy, a o tej
  godzinie jesteś w pracy, lista przyjdzie, kiedy z niej wyjdziesz. Wyjście
  po najwcześniejszej godzinie (domyślnie 15:00) wysyła ją od razu, także
  przed ustawioną godziną, a wcześniejsze (np. na obiad) nie. Jeśli o
  najpóźniejszej godzinie (domyślnie 20:00) wciąż jesteś w pracy, lista i tak
  przychodzi.
- Identyfikatory encji tworzy Home Assistant z nazwy planera i nazwy encji
  w języku serwera, np. `sensor.obiady_do_kupienia`. Wszystkie encje znajdziesz
  przy urządzeniu planera w **Ustawienia → Urządzenia i usługi → Urządzenia**.

Instalacja: **Ustawienia → Marketplace → Dodaj z linku**
`https://github.com/delicatty/ha-lunch-planner`, potem restart i **Dodaj
integrację → Lunch Planner**.

## License

MIT
