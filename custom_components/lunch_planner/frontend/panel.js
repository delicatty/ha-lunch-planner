/**
 * Lunch Planner sidebar panel.
 *
 * Built from Home Assistant's own dashboard cards (tile, calendar, markdown,
 * to-do list), so it looks and behaves like the rest of the interface.
 * The Python side passes the entity IDs of every planner in panel.config.
 */

const TEXTS = {
  en: {
    plan: "Plan",
    database: "Meal database",
    single: "Single dishes",
    composed: "Composed main courses",
    lists: {
      soup: "Soup",
      dish: "Main course",
      protein: "Main part",
      starch: "Starchy side",
      salad: "Salad / vegetables",
    },
    redrawConfirm: "Draw all upcoming lunches again? Lunches already shopped for stay.",
    hint:
      "Add meals to the lists below. In an item's description write what to buy, " +
      "one thing per line or separated by commas; with no description its name goes " +
      "on the shopping list. A `season: 5-7` line limits an item to May–July. " +
      "A ticked-off item stays here but is not drawn.",
  },
  pl: {
    plan: "Plan",
    database: "Baza dań",
    single: "Jednoskładnikowe",
    composed: "Wieloskładnikowe",
    lists: {
      soup: "Zupa",
      dish: "Drugie danie",
      protein: "Składnik główny",
      starch: "Dodatek skrobiowy",
      salad: "Surówka / warzywa",
    },
    redrawConfirm:
      "Wylosować ponownie wszystkie nadchodzące obiady? Te, na które już zrobiono zakupy, zostaną.",
    hint:
      "Dodawaj dania do list poniżej. W opisie pozycji wpisz, co kupić: każdą rzecz " +
      "w osobnej linii albo po przecinku. Bez opisu na listę zakupów trafia nazwa. " +
      "Linia `sezon: 5-7` ogranicza pozycję do maja–lipca. Odhaczona pozycja zostaje " +
      "w bazie, ale nie jest losowana.",
  },
};

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
  }
  .toolbar {
    display: flex;
    align-items: center;
    height: var(--header-height, 56px);
    padding: 0 12px;
    gap: 12px;
    background: var(--app-header-background-color, var(--primary-color));
    color: var(--app-header-text-color, var(--text-primary-color));
    font-size: 20px;
    position: sticky;
    top: 0;
    z-index: 2;
  }
  .content {
    max-width: 1280px;
    margin: 0 auto;
    padding: 16px;
    box-sizing: border-box;
  }
  h1 {
    font-size: 22px;
    font-weight: 500;
    margin: 8px 4px 4px;
  }
  h2 {
    font-size: 18px;
    font-weight: 500;
    margin: 24px 4px 12px;
  }
  .plan {
    display: grid;
    grid-template-columns: minmax(280px, 1fr) minmax(320px, 2fr);
    gap: 16px;
    align-items: start;
  }
  .stack {
    display: grid;
    gap: 8px;
  }
  h3 {
    font-size: 16px;
    font-weight: 500;
    margin: 20px 4px 8px;
    color: var(--secondary-text-color);
  }
  .lists {
    display: grid;
    gap: 16px;
    align-items: start;
  }
  .lists.two {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .lists.three {
    grid-template-columns: repeat(3, minmax(0, 1fr));
  }
  @media (max-width: 760px) {
    .plan,
    .lists.two,
    .lists.three {
      grid-template-columns: 1fr;
    }
    .content {
      padding: 8px;
    }
  }
`;

/**
 * Home Assistant defines window.loadCardHelpers only once the dashboard
 * (Lovelace) code has been loaded, e.g. after a dashboard was opened. When
 * this panel is opened first, load that code ourselves through the panel
 * resolver, the same way the frontend loads a dashboard panel.
 */
async function loadCardHelpers() {
  if (!window.loadCardHelpers) {
    await customElements.whenDefined("partial-panel-resolver");
    const resolver = document.createElement("partial-panel-resolver");
    resolver.hass = { panels: [{ url_path: "tmp", component_name: "lovelace" }] };
    resolver._updateRoutes();
    await resolver.routerOptions.routes.tmp.load();
    for (let i = 0; i < 100 && !window.loadCardHelpers; i++) {
      await new Promise((resolve) => setTimeout(resolve, 50));
    }
  }
  if (!window.loadCardHelpers) {
    throw new Error("Lunch Planner: Home Assistant card helpers are not available");
  }
  return window.loadCardHelpers();
}

class LunchPlannerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._cards = [];
    this._menuButton = null;
    this._built = false;
    this._building = false;
  }

  set hass(hass) {
    this._hass = hass;
    for (const card of this._cards) card.hass = hass;
    if (this._menuButton) this._menuButton.hass = hass;
    this._maybeBuild();
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menuButton) this._menuButton.narrow = narrow;
  }

  set panel(panel) {
    const config = panel && panel.config;
    if (JSON.stringify(config) !== JSON.stringify(this._config)) {
      this._config = config;
      this._built = false;
      this._maybeBuild();
    }
  }

  _texts() {
    const lang = (this._hass && this._hass.language) || "en";
    return lang.toLowerCase().startsWith("pl") ? TEXTS.pl : TEXTS.en;
  }

  /** Entity name without the planner (device) name in front of it. */
  _name(entityId, plannerTitle) {
    const state = this._hass.states[entityId];
    const name = (state && state.attributes.friendly_name) || entityId;
    return name.startsWith(plannerTitle + " ") ? name.slice(plannerTitle.length + 1) : name;
  }

  async _maybeBuild() {
    if (this._built || this._building || !this._hass || !this._config) return;
    this._building = true;
    try {
      const helpers = await loadCardHelpers();
      this._render(helpers);
      this._built = true;
    } finally {
      this._building = false;
    }
  }

  _card(helpers, config, parent) {
    const card = helpers.createCardElement(config);
    card.hass = this._hass;
    this._cards.push(card);
    parent.appendChild(card);
    return card;
  }

  _render(helpers) {
    const texts = this._texts();
    const root = this.shadowRoot;
    root.innerHTML = "";
    this._cards = [];

    const style = document.createElement("style");
    style.textContent = STYLE;
    root.appendChild(style);

    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    this._menuButton = document.createElement("ha-menu-button");
    this._menuButton.hass = this._hass;
    this._menuButton.narrow = this._narrow;
    toolbar.appendChild(this._menuButton);
    const title = document.createElement("div");
    title.textContent = this._config.title;
    toolbar.appendChild(title);
    root.appendChild(toolbar);

    const content = document.createElement("div");
    content.className = "content";
    root.appendChild(content);

    const planners = this._config.planners || [];
    for (const planner of planners) {
      const e = planner.entities || {};

      if (planners.length > 1) {
        const heading = document.createElement("h1");
        heading.textContent = planner.title;
        content.appendChild(heading);
      }

      const planHeading = document.createElement("h2");
      planHeading.textContent = texts.plan;
      content.appendChild(planHeading);

      const plan = document.createElement("div");
      plan.className = "plan";
      content.appendChild(plan);

      const stack = document.createElement("div");
      stack.className = "stack";
      plan.appendChild(stack);
      for (const key of ["today", "tomorrow", "next_shopping"]) {
        if (e[key]) {
          this._card(
            helpers,
            { type: "tile", entity: e[key], name: this._name(e[key], planner.title) },
            stack,
          );
        }
      }
      if (e.redraw) {
        this._card(
          helpers,
          {
            type: "tile",
            entity: e.redraw,
            name: this._name(e.redraw, planner.title),
            show_entity_picture: false,
            hide_state: true,
            tap_action: {
              action: "perform-action",
              perform_action: "button.press",
              target: { entity_id: e.redraw },
              confirmation: { text: texts.redrawConfirm },
            },
          },
          stack,
        );
      }
      if (e.send_shopping) {
        this._card(
          helpers,
          {
            type: "tile",
            entity: e.send_shopping,
            name: this._name(e.send_shopping, planner.title),
            hide_state: true,
            tap_action: {
              action: "perform-action",
              perform_action: "button.press",
              target: { entity_id: e.send_shopping },
            },
          },
          stack,
        );
      }

      if (e.plan) {
        const calendarBox = document.createElement("div");
        plan.appendChild(calendarBox);
        this._card(
          helpers,
          { type: "calendar", entities: [e.plan], initial_view: "listWeek" },
          calendarBox,
        );
      }

      const dbHeading = document.createElement("h2");
      dbHeading.textContent = texts.database;
      content.appendChild(dbHeading);
      this._card(helpers, { type: "markdown", content: texts.hint }, content);

      const lists = planner.lists || {};
      const groups = [
        [texts.single, ["soup", "dish"], "two"],
        [texts.composed, ["protein", "starch", "salad"], "three"],
      ];
      for (const [label, categories, columns] of groups) {
        const present = categories.filter((c) => lists[c]);
        if (!present.length) continue;
        const subheading = document.createElement("h3");
        subheading.textContent = label;
        content.appendChild(subheading);
        const grid = document.createElement("div");
        grid.className = `lists ${columns}`;
        content.appendChild(grid);
        for (const category of present) {
          this._card(
            helpers,
            { type: "todo-list", entity: lists[category], title: texts.lists[category] },
            grid,
          );
        }
      }
    }
  }
}

if (!customElements.get("lunch-planner-panel")) {
  customElements.define("lunch-planner-panel", LunchPlannerPanel);
}
