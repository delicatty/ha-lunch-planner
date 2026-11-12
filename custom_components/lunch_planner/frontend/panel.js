/**
 * Lunch Planner sidebar panel.
 *
 * Two tabs, like a dashboard's views: the plan and the meal database. The tab
 * is part of the URL (/lunch-planner, /lunch-planner/meals).
 *
 * The plan part uses Home Assistant's own cards (tile, calendar). The meal
 * database is a small editor of its own, built from plain HTML styled with
 * Home Assistant's theme variables, talking to the integration over the
 * lunch_planner/meals/* WebSocket commands.
 */

// Texts come from translations/*.json (selector "panel"), loaded with
// hass.loadBackendTranslation. Property name -> translation key.
const TEXT_KEYS = {
  plan: "plan",
  actions: "actions",
  database: "database",
  single: "single",
  composed: "composed",
  add: "add",
  empty: "empty",
  toBuy: "to_buy",
  draw: "draw",
  notDrawn: "not_drawn",
  redrawConfirm: "redraw_confirm",
  addTitle: "add_title",
  editTitle: "edit_title",
  name: "name",
  ingredients: "ingredients",
  ingredientsHelp: "ingredients_help",
  season: "season",
  allYear: "all_year",
  months: "months",
  from: "from",
  to: "to",
  cancel: "cancel",
  save: "save",
  delete: "delete",
  deleteConfirm: "delete_confirm",
  error: "error",
};
// Tab -> path under the panel's URL.
const TABS = [
  ["plan", ""],
  ["database", "/meals"],
];
const CATEGORIES = ["soup", "dish", "protein", "starch", "salad"];

const GROUPS = [
  ["single", ["soup", "dish"], "two"],
  ["composed", ["protein", "starch", "salad"], "three"],
];

const STYLE = `
  :host {
    display: block;
    min-height: 100vh;
    background: var(--primary-background-color);
    color: var(--primary-text-color);
    font-family: var(--ha-font-family-body, Roboto, sans-serif);
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
  .tabs { display: flex; align-self: stretch; margin-left: 12px; overflow-x: auto; scrollbar-width: none; }
  .tab {
    background: none; color: inherit; border-radius: 0; padding: 0 16px;
    font-size: 14px; font-weight: 500; text-transform: uppercase; letter-spacing: 0.05em;
    opacity: 0.7; border-bottom: 2px solid transparent; white-space: nowrap;
  }
  .tab:hover { opacity: 1; }
  .tab[aria-selected="true"] { opacity: 1; border-bottom-color: currentColor; }
  .tab:focus-visible { outline: 2px solid currentColor; outline-offset: -4px; }
  .content { max-width: 1280px; margin: 0 auto; padding: 16px; box-sizing: border-box; container-type: inline-size; }
  h1 { font-size: 22px; font-weight: 500; margin: 8px 4px 4px; }
  h2 { font-size: 18px; font-weight: 500; margin: 24px 4px 12px; }
  h3 { font-size: 16px; font-weight: 500; margin: 20px 4px 8px; color: var(--secondary-text-color); }
  .plan { display: grid; grid-template-columns: minmax(320px, 2fr) minmax(280px, 1fr); gap: 16px; align-items: start; margin-top: 8px; }
  .stack { display: grid; gap: 8px; }
  .side h2 { margin-top: 16px; }
  .meals > div > h3:first-child { margin-top: 8px; }
  .lists { display: grid; gap: 16px; align-items: start; }
  .lists.two { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .lists.three { grid-template-columns: repeat(3, minmax(0, 1fr)); }
  .card {
    background: var(--card-background-color, var(--ha-card-background, #fff));
    border-radius: var(--ha-card-border-radius, 12px);
    border: var(--ha-card-border-width, 1px) solid var(--ha-card-border-color, var(--divider-color, #e0e0e0));
    box-shadow: var(--ha-card-box-shadow, none);
    overflow: hidden;
  }
  .card-header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 8px 8px 16px; font-size: 18px; font-weight: 500;
  }
  button {
    font: inherit; cursor: pointer; border-radius: 18px; border: none;
    padding: 6px 14px; font-size: 14px; font-weight: 500;
  }
  .text-button { background: none; color: var(--primary-color); }
  .text-button:hover { background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.1); }
  .primary { background: var(--primary-color); color: var(--text-primary-color, #fff); }
  .danger { background: none; color: var(--error-color, #db4437); margin-right: auto; }
  .meal {
    display: flex; align-items: center; gap: 12px; padding: 10px 12px 10px 16px;
    border-top: 1px solid var(--divider-color, #e0e0e0); cursor: pointer;
  }
  .meal:hover { background: var(--secondary-background-color, #f5f5f5); }
  .meal.off .name, .meal.off .details { opacity: 0.5; }
  .meal-text { flex: 1; min-width: 0; }
  .name { font-size: 15px; }
  .details { font-size: 12px; color: var(--secondary-text-color); margin-top: 2px; overflow-wrap: anywhere; }
  .chip {
    display: inline-block; font-size: 11px; padding: 1px 8px; margin-left: 6px; border-radius: 10px;
    background: rgba(var(--rgb-primary-color, 3, 169, 244), 0.15); color: var(--primary-color);
    vertical-align: middle;
  }
  .empty { padding: 12px 16px 16px; color: var(--secondary-text-color); font-size: 14px; border-top: 1px solid var(--divider-color, #e0e0e0); }
  /* A switch like Home Assistant's own, built from a checkbox. */
  input.toggle {
    appearance: none; -webkit-appearance: none; flex: none;
    position: relative; width: 36px; height: 20px; margin: 0; border-radius: 10px;
    background: var(--switch-unchecked-track-color, rgba(0, 0, 0, 0.26)); cursor: pointer;
    transition: background 0.15s;
  }
  input.toggle::before {
    content: ""; position: absolute; top: 2px; left: 2px; width: 16px; height: 16px; border-radius: 50%;
    background: var(--switch-unchecked-button-color, #fafafa); box-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
    transition: transform 0.15s;
  }
  input.toggle:checked { background: var(--switch-checked-track-color, var(--primary-color)); }
  input.toggle:checked::before { transform: translateX(16px); background: var(--switch-checked-button-color, #fff); }
  input.toggle:focus-visible { outline: 2px solid var(--primary-color); outline-offset: 2px; }
  .chip.off { background: var(--disabled-color, rgba(0, 0, 0, 0.12)); color: var(--secondary-text-color); }
  .toggle-row { display: flex; align-items: center; gap: 12px; font-size: 15px; color: var(--primary-text-color); cursor: pointer; }
  dialog {
    border: none; border-radius: var(--ha-dialog-border-radius, 24px); padding: 0;
    width: min(480px, calc(100vw - 32px));
    background: var(--card-background-color, #fff); color: var(--primary-text-color);
    box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
  }
  dialog::backdrop { background: rgba(0, 0, 0, 0.4); }
  form { padding: 24px; display: grid; gap: 16px; }
  .dialog-title { font-size: 22px; margin: 0; }
  label.field { display: grid; gap: 4px; font-size: 13px; color: var(--secondary-text-color); }
  input[type="text"], textarea, select {
    font: inherit; font-size: 15px; color: var(--primary-text-color);
    background: var(--input-fill-color, var(--secondary-background-color, #f5f5f5));
    border: none; border-bottom: 1px solid var(--input-idle-line-color, var(--divider-color, #999));
    border-radius: 4px 4px 0 0; padding: 10px 12px; box-sizing: border-box; width: 100%;
  }
  input[type="text"]:focus, textarea:focus, select:focus { outline: none; border-bottom: 2px solid var(--primary-color); }
  textarea { min-height: 96px; resize: vertical; }
  .hint { font-size: 12px; color: var(--secondary-text-color); }
  .row { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
  .row select { width: auto; flex: 1; min-width: 120px; }
  .radio { display: flex; align-items: center; gap: 8px; font-size: 15px; color: var(--primary-text-color); cursor: pointer; }
  .radio input { accent-color: var(--primary-color); margin: 0; }
  .actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 4px; }
  .error { color: var(--error-color, #db4437); font-size: 13px; }
  /* One column when the panel itself is narrow, also with the sidebar open. */
  @container (max-width: 720px) {
    .plan, .lists.two, .lists.three { grid-template-columns: 1fr; }
  }
  @media (max-width: 760px) {
    .content { padding: 8px; }
    .tabs { margin-left: 0; }
    .tab { padding: 0 12px; }
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

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attrs)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else if (value === true) node.setAttribute(key, "");
    else if (value !== false && value != null) node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child == null || child === false) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

class LunchPlannerPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._cards = [];
    this._menuButton = null;
    this._built = false;
    this._building = false;
    this._meals = {}; // entry_id -> {category: [meal]}
    this._mealBoxes = {}; // entry_id -> element holding the meal lists
    this._unsubs = [];
    this._tab = "plan";
    this._tabButtons = {};
    this._tabPages = {};
  }

  set hass(hass) {
    const first = !this._hass;
    const languageChanged = this._built && hass.language !== this._language;
    this._hass = hass;
    for (const card of this._cards) card.hass = hass;
    if (this._menuButton) this._menuButton.hass = hass;
    if (languageChanged) {
      this._built = false;
      this._maybeBuild();
    } else if (first) {
      this._maybeBuild();
    }
  }

  get hass() {
    return this._hass;
  }

  set narrow(narrow) {
    this._narrow = narrow;
    if (this._menuButton) this._menuButton.narrow = narrow;
  }

  /** Home Assistant sets the route ({prefix, path}) when the URL changes. */
  set route(route) {
    this._route = route;
    const path = (route && route.path) || "";
    const tab = TABS.find(([, tabPath]) => tabPath && path.startsWith(tabPath));
    this._tab = tab ? tab[0] : "plan";
    this._showTab();
  }

  _openTab(tab) {
    if (tab === this._tab) return;
    const prefix = (this._route && this._route.prefix) || "/lunch-planner";
    const path = TABS.find(([name]) => name === tab)[1];
    // The same as Home Assistant's navigate(): it then sets the new route.
    history.pushState(null, "", prefix + path);
    window.dispatchEvent(new CustomEvent("location-changed", { detail: { replace: false } }));
  }

  _showTab() {
    for (const [name] of TABS) {
      const selected = name === this._tab;
      if (this._tabButtons[name]) this._tabButtons[name].setAttribute("aria-selected", String(selected));
      if (this._tabPages[name]) this._tabPages[name].hidden = !selected;
    }
  }

  set panel(panel) {
    const config = panel && panel.config;
    if (JSON.stringify(config) !== JSON.stringify(this._config)) {
      this._config = config;
      this._built = false;
      this._maybeBuild();
    }
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  connectedCallback() {
    if (this._built) this._subscribe();
  }

  _t(key) {
    const text = this._localize
      ? this._localize(`component.lunch_planner.selector.panel.options.${key}`)
      : "";
    return text || key;
  }

  _texts() {
    const texts = {};
    for (const [prop, key] of Object.entries(TEXT_KEYS)) texts[prop] = this._t(key);
    texts.categories = Object.fromEntries(CATEGORIES.map((c) => [c, this._t(`category_${c}`)]));
    return texts;
  }

  _monthName(month) {
    const lang = (this._hass && this._hass.language) || "en";
    return new Intl.DateTimeFormat(lang, { month: "long" }).format(new Date(2026, month - 1, 1));
  }

  _monthShort(month) {
    const lang = (this._hass && this._hass.language) || "en";
    return new Intl.DateTimeFormat(lang, { month: "short" })
      .format(new Date(2026, month - 1, 1))
      .replace(".", "");
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
      this._language = this._hass.language;
      this._localize = await this._hass.loadBackendTranslation("selector", "lunch_planner");
      this._render(helpers);
      this._built = true;
      this._subscribe();
    } finally {
      this._building = false;
    }
  }

  async _subscribe() {
    this._unsubscribe();
    for (const planner of this._config.planners || []) {
      const unsub = await this._hass.connection.subscribeMessage(
        (message) => {
          this._meals[planner.entry_id] = message.meals;
          this._renderMeals(planner.entry_id);
        },
        { type: "lunch_planner/meals/subscribe", entry_id: planner.entry_id },
      );
      this._unsubs.push(unsub);
    }
  }

  _unsubscribe() {
    for (const unsub of this._unsubs) {
      try {
        unsub();
      } catch (err) {
        /* connection already closed */
      }
    }
    this._unsubs = [];
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
    this._mealBoxes = {};

    root.appendChild(el("style", {}, STYLE));

    this._menuButton = document.createElement("ha-menu-button");
    this._menuButton.hass = this._hass;
    this._menuButton.narrow = this._narrow;
    const tabs = el("div", { class: "tabs", role: "tablist" });
    this._tabButtons = {};
    this._tabPages = {};
    for (const [name] of TABS) {
      this._tabButtons[name] = el(
        "button",
        { class: "tab", role: "tab", onclick: () => this._openTab(name) },
        texts[name],
      );
      tabs.appendChild(this._tabButtons[name]);
    }
    root.appendChild(el("div", { class: "toolbar" }, this._menuButton, el("div", {}, this._config.title), tabs));

    const content = el("div", { class: "content" });
    root.appendChild(content);
    for (const [name] of TABS) {
      this._tabPages[name] = el("div", { role: "tabpanel", class: name === "database" ? "meals" : "" });
      content.appendChild(this._tabPages[name]);
    }
    const planPage = this._tabPages.plan;
    const mealsPage = this._tabPages.database;

    this._dialog = el("dialog");
    root.appendChild(this._dialog);

    const planners = this._config.planners || [];
    for (const planner of planners) {
      const e = planner.entities || {};
      if (planners.length > 1) {
        planPage.appendChild(el("h1", {}, planner.title));
        mealsPage.appendChild(el("h1", {}, planner.title));
      }

      // The calendar, and next to it (under it on a phone) the plan tiles
      // with the actions right under them.
      const stack = el("div", { class: "stack" });
      const side = el("div", { class: "side" }, stack);
      const calendarBox = el("div");
      planPage.appendChild(el("div", { class: "plan" }, calendarBox, side));

      for (const key of ["today", "tomorrow", "next_shopping", "to_buy"]) {
        if (e[key]) {
          this._card(helpers, { type: "tile", entity: e[key], name: this._name(e[key], planner.title) }, stack);
        }
      }
      if (e.plan) {
        // As a sections-dashboard card with automatic height: the calendar is
        // as tall as its content, not a fixed 400px with empty space under a
        // short week, which would push the tiles down on a phone.
        const calendar = this._card(
          helpers,
          { type: "calendar", entities: [e.plan], initial_view: "listWeek", grid_options: { rows: "auto" } },
          calendarBox,
        );
        calendar.layout = "grid";
      }

      if (e.redraw) {
        const actions = el("div", { class: "stack" });
        side.append(el("h2", {}, texts.actions), actions);
        // Tapping the tile or its icon asks first; holding does nothing.
        const press = {
          action: "perform-action",
          perform_action: "button.press",
          target: { entity_id: e.redraw },
          confirmation: { text: texts.redrawConfirm },
        };
        this._card(
          helpers,
          {
            type: "tile",
            entity: e.redraw,
            name: this._name(e.redraw, planner.title),
            hide_state: true,
            tap_action: press,
            icon_tap_action: press,
            hold_action: { action: "none" },
            double_tap_action: { action: "none" },
          },
          actions,
        );
      }

      const box = el("div");
      mealsPage.appendChild(box);
      this._mealBoxes[planner.entry_id] = box;
      this._renderMeals(planner.entry_id);
    }
    this._showTab();
  }

  _renderMeals(entryId) {
    const box = this._mealBoxes[entryId];
    if (!box) return;
    const texts = this._texts();
    const meals = this._meals[entryId] || {};
    box.replaceChildren();
    for (const [groupKey, categories, columns] of GROUPS) {
      box.appendChild(el("h3", {}, texts[groupKey]));
      const grid = el("div", { class: `lists ${columns}` });
      box.appendChild(grid);
      for (const category of categories) {
        grid.appendChild(this._categoryCard(entryId, category, meals[category] || []));
      }
    }
  }

  _seasonLabel(season) {
    if (!season) return null;
    const [start, end] = season;
    return start === end ? this._monthShort(start) : `${this._monthShort(start)}–${this._monthShort(end)}`;
  }

  _categoryCard(entryId, category, meals) {
    const texts = this._texts();
    const card = el(
      "div",
      { class: "card" },
      el(
        "div",
        { class: "card-header" },
        el("span", {}, texts.categories[category]),
        el("button", { class: "text-button", onclick: () => this._openDialog(entryId, category, null) }, `+ ${texts.add}`),
      ),
    );
    if (!meals.length) {
      card.appendChild(el("div", { class: "empty" }, texts.empty));
      return card;
    }
    // Alphabetical in the user's language (ą after a, ż last in Polish).
    const collator = new Intl.Collator(this._hass.locale?.language || this._hass.language, { sensitivity: "base", numeric: true });
    const sorted = [...meals].sort((a, b) => collator.compare(a.name, b.name));
    for (const meal of sorted) {
      const season = this._seasonLabel(meal.season);
      const toggle = el("input", {
        type: "checkbox",
        role: "switch",
        class: "toggle",
        checked: meal.active,
        title: texts.draw,
        "aria-label": `${texts.draw}: ${meal.name}`,
        onclick: (ev) => ev.stopPropagation(),
        onchange: (ev) => this._save(entryId, category, { ...meal, active: ev.target.checked }),
      });
      card.appendChild(
        el(
          "div",
          { class: `meal${meal.active ? "" : " off"}`, onclick: () => this._openDialog(entryId, category, meal) },
          el(
            "div",
            { class: "meal-text" },
            el(
              "div",
              { class: "name" },
              meal.name,
              season ? el("span", { class: "chip" }, season) : null,
              meal.active ? null : el("span", { class: "chip off" }, texts.notDrawn),
            ),
            meal.ingredients.length
              ? el("div", { class: "details" }, `${texts.toBuy}: ${meal.ingredients.join(", ")}`)
              : null,
          ),
          toggle,
        ),
      );
    }
    return card;
  }

  async _save(entryId, category, meal) {
    const message = {
      type: "lunch_planner/meals/save",
      entry_id: entryId,
      category,
      name: meal.name,
      ingredients: meal.ingredients,
      season: meal.season,
      active: meal.active,
    };
    if (meal.uid) message.uid = meal.uid;
    return this._hass.callWS(message);
  }

  _openDialog(entryId, category, meal) {
    const texts = this._texts();
    const dialog = this._dialog;
    const season = (meal && meal.season) || null;

    const name = el("input", { type: "text", required: true, value: meal ? meal.name : "" });
    name.value = meal ? meal.name : "";
    const ingredients = el("textarea", { rows: 4 });
    ingredients.value = meal ? meal.ingredients.join("\n") : "";

    const monthSelect = (selected) =>
      el(
        "select",
        {},
        Array.from({ length: 12 }, (_, i) =>
          el("option", { value: i + 1, selected: i + 1 === selected }, this._monthName(i + 1)),
        ),
      );
    const from = monthSelect(season ? season[0] : 5);
    const to = monthSelect(season ? season[1] : 9);
    const radioName = `season-${Date.now()}`;
    const allYear = el("input", { type: "radio", name: radioName, checked: !season });
    const someMonths = el("input", { type: "radio", name: radioName, checked: !!season });
    const monthsRow = el("div", { class: "row" }, texts.from, from, texts.to, to);
    const syncMonths = () => {
      monthsRow.style.display = someMonths.checked ? "" : "none";
    };
    allYear.addEventListener("change", syncMonths);
    someMonths.addEventListener("change", syncMonths);
    syncMonths();

    const active = el("input", {
      type: "checkbox",
      role: "switch",
      class: "toggle",
      checked: meal ? meal.active : true,
    });
    const error = el("div", { class: "error" });
    const saveButton = el("button", { class: "primary", type: "submit" }, texts.save);
    const syncSave = () => {
      saveButton.disabled = !name.value.trim();
      saveButton.style.opacity = saveButton.disabled ? "0.5" : "";
    };
    name.addEventListener("input", syncSave);
    syncSave();

    const close = () => dialog.close();
    const form = el(
      "form",
      {
        method: "dialog",
        onsubmit: async (ev) => {
          ev.preventDefault();
          if (!name.value.trim()) return;
          try {
            await this._save(entryId, category, {
              uid: meal ? meal.uid : undefined,
              name: name.value,
              ingredients: ingredients.value.split("\n").map((s) => s.trim()).filter(Boolean),
              season: someMonths.checked ? [Number(from.value), Number(to.value)] : null,
              active: active.checked,
            });
            close();
          } catch (err) {
            error.textContent = `${texts.error}: ${err.message || err.code || err}`;
          }
        },
      },
      el("h2", { class: "dialog-title" }, `${meal ? texts.editTitle : texts.addTitle} · ${texts.categories[category]}`),
      el("label", { class: "field" }, texts.name, name),
      el("label", { class: "field" }, texts.ingredients, ingredients, el("span", { class: "hint" }, texts.ingredientsHelp)),
      el(
        "div",
        { class: "field" },
        el("div", { class: "hint" }, texts.season),
        el("label", { class: "radio" }, allYear, texts.allYear),
        el("label", { class: "radio" }, someMonths, texts.months),
        monthsRow,
      ),
      el("label", { class: "toggle-row" }, active, texts.draw),
      error,
      el(
        "div",
        { class: "actions" },
        meal
          ? el(
              "button",
              {
                class: "danger",
                type: "button",
                onclick: async () => {
                  if (!confirm(texts.deleteConfirm)) return;
                  try {
                    await this._hass.callWS({ type: "lunch_planner/meals/delete", entry_id: entryId, uid: meal.uid });
                    close();
                  } catch (err) {
                    error.textContent = `${texts.error}: ${err.message || err.code || err}`;
                  }
                },
              },
              texts.delete,
            )
          : null,
        el("button", { class: "text-button", type: "button", onclick: close }, texts.cancel),
        saveButton,
      ),
    );
    // Enter in the name field submits the form; Ctrl+Enter (Cmd+Enter on a
    // Mac) does it from anywhere, including the multi-line "what to buy" field.
    form.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter" && (ev.ctrlKey || ev.metaKey)) {
        ev.preventDefault();
        form.requestSubmit();
      }
    });
    dialog.replaceChildren(form);
    dialog.showModal();
    name.focus();
  }
}

if (!customElements.get("lunch-planner-panel")) {
  customElements.define("lunch-planner-panel", LunchPlannerPanel);
}
