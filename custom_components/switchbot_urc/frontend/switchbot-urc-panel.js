const DOMAIN = "switchbot_urc";
const SCENE_ICONS = [
  "Default", "Morning", "Night", "Lights on", "Lights off", "Arrive home",
  "Leave home", "Dance", "Treadmill", "Strength training", "Music", "Shield",
  "Airplane", "Gaming", "Dumbbell", "Leaf", "Growing plants", "Leisure",
  "Movie", "Book", "Home", "Sleep", "Sofa", "Walk the dog", "Shower",
];
const SCENE_COLORS = ["Pink", "Orange", "Yellow", "Green", "Turquoise", "Blue", "Purple", "Gray"];
// Pause has no default Quick bind action. Home Assistant identifies a press
// by its page and position, so new Native buttons can share this function.
const NATIVE_CUSTOM_FUNCTION = 22;
const APP_ICON_ASSETS = {
  light: "light", desklamp: "desklamp", floorlamp: "floorlamp",
  ceilinglamp: "ceilinglamp", strip: "lightstrip", switch: "switch",
  bathtub: "bathtub", coffeemachine: "coffeemachine", socket: "socket",
  tv: "television", boiler: "boiler", heater: "heater", cooler: "cooler",
  washer: "washer", fridge: "fridge", cookware: "cookware",
  pool: "pool", ventilator: "ventilator",
};
const APP_ICON_LABELS = {
  light: "Light", desklamp: "Desk lamp", floorlamp: "Floor lamp",
  ceilinglamp: "Ceiling light", strip: "Light strip", switch: "Switch",
  bathtub: "Bathtub", coffeemachine: "Coffee machine", socket: "Outlet",
  tv: "TV", boiler: "Boiler", heater: "Heater", cooler: "Cooling",
  washer: "Washing machine", fridge: "Fridge", cookware: "Cooker",
  pool: "Pool", ventilator: "Fan", blinds: "Roller blind", garage: "Garage",
};
// A caption written as a Home Assistant template is rendered by Home Assistant and kept up to date.
const isTemplate = (text) => /\{\{|\{%/.test(text || "");
// Firmware default artwork for device type 0x27 (docs/native-default-artwork-map.csv).
const MATTER_ARTWORK = "/switchbot_urc_static/artwork/profile-1b.png";
const HID_PROFILE_ARTWORK = {
  APPLE_TV: "1d", FIRE_TV: "1e", UNIVERSAL_BLE: "20", GOOGLE_TV: "1f",
};
const IR_PROFILE_ARTWORK = {
  1: "1a", 2: "18", 3: "19", 4: "0f", 5: "05", 6: "09", 7: "0e",
  8: "08", 9: "00", 10: "06", 11: "01", 12: "0a", 13: "10", 14: "0c",
};
// The catalog numbers its IR types like the SwitchBot hub; the remote and the app use their own
// ids (the keys above). Light is 3 in the catalog and 14 on the remote, and so on.
const CATALOG_TO_REMOTE_IR_TYPE = {
  1: 1, 2: 2, 3: 14, 4: 3, 5: 4, 6: 5, 7: 6, 8: 7, 10: 8, 11: 10, 12: 11, 13: 12, 14: 13,
};
// English captions from docs/native-glyph-resource-index.csv (WoRWS V48).
const NATIVE_GLYPH_LABELS = {
  "0": null,
  "1": null,
  "2": null,
  "3": null,
  "4": null,
  "5": "ON",
  "6": "OFF",
  "12": "Back",
  "13": "Menu",
  "15": "Vol+",
  "16": "Vol-",
  "17": "Ch+",
  "18": "Ch-",
  "19": "Mute",
  "20": "Play",
  "21": "Play",
  "22": "Pause",
  "23": "OFF",
  "24": "Record",
  "25": "Rewind",
  "26": "Forward",
  "27": "Play Last Track",
  "28": "Play Next Track",
  "30": null,
  "31": null,
  "32": null,
  "33": null,
  "39": "More Buttons",
  "40": "0",
  "41": "1",
  "42": "2",
  "43": "3",
  "44": "4",
  "45": "5",
  "46": "6",
  "47": "7",
  "48": "8",
  "49": "9",
  "50": "Auto",
  "51": "Cool",
  "52": "Dry",
  "53": "Fan",
  "54": "Heat",
  "55": "Humidify",
  "56": "Mode",
  "57": "Sleep",
  "58": "Comfort",
  "59": "Mode",
  "60": "Temp+",
  "61": "Temp-",
  "62": "Warm",
  "70": null,
  "71": "Auto",
  "72": "Fan Speed 1",
  "73": "Fan Speed 2",
  "74": "Fan Speed 3",
  "75": "Fan Speed 4",
  "76": "Fan Speed 5",
  "77": null,
  "78": null,
  "80": "Auto",
  "81": "Auto",
  "82": "Swing 1",
  "83": "Swing 2",
  "84": "Swing 3",
  "85": "Swing 4",
  "89": "Swing",
  "90": "Timer",
  "91": "30 Min",
  "92": "Schedules",
  "94": "Timer",
  "100": "More Buttons",
  "101": "Blue",
  "102": "Red",
  "103": "Green",
  "104": "Yellow",
  "105": "Power",
  "106": "Rec List",
  "107": "Zoom In",
  "108": "Zoom Out",
  "109": "Preference",
  "110": "Settings",
  "111": "Eject",
  "112": "Child Lock",
  "113": "Ion",
  "114": "Source",
  "115": null,
  "116": "Menu",
  "117": "Auto",
  "118": "Home",
  "119": "Normal",
  "120": "Natural",
  "121": "Sleep",
  "122": "Baby",
  "123": null,
  "124": null,
  "125": null,
  "126": null,
  "127": null,
  "128": null,
  "129": "Level 4",
  "130": "Level 3",
  "131": "Level 2",
  "132": "Level 1",
  "133": "Nightlight ON",
  "134": "Nightlight Dim",
  "135": "Nightlight OFF",
  "136": "V. Swing 30°",
  "137": "V. Swing 60°",
  "138": "V. Swing 90°",
  "139": "Turn off",
  "140": "H. Swing 30°",
  "141": "H. Swing 60°",
  "142": "H. Swing 90°",
  "143": "Turn off",
  "144": "Normal-Level 1",
  "145": "Normal-Level 2",
  "146": "Normal-Level 3",
  "147": "Normal-Level 4",
  "148": "Normal-Level 5",
  "149": "Normal-Level 6",
  "150": "Normal-Level 7",
  "151": "Normal-Level 8",
  "152": "Normal-Level 9",
  "153": "Shutter",
  "154": "Heat",
  "200": "10",
  "201": "11",
  "202": "12",
  "203": "3-Digit Input",
  "210": "Source",
  "211": "BS",
  "212": "CS",
  "213": "DTTV",
  "214": "Stream",
  "220": "Program Info",
  "221": "Data",
  "222": "CC",
  "223": "Display",
  "224": "Audio",
  "300": "Brighter",
  "301": "Darker",
  "302": "Warmer",
  "303": "Whiter",
  "311": "Night",
  "312": "All",
  "313": "Midnight",
  "314": "Sleep",
  "315": "Reading",
  "316": "Leisure",
  "317": "Dining",
  "318": "+/- is valid only in Cool/Heat mode.",
  "320": "White",
  "321": "White",
  "322": "Warmer",
  "323": "Cooler",
  "330": "Color Bulb",
  "331": "Color 1",
  "332": "Color 2",
  "333": "Color 3",
  "334": "Color 4",
  "335": "Color 5",
  "336": "Color 6",
  "337": "Color 7",
  "338": "Color 8",
  "339": "Color 9",
  "340": "Color 10",
  "341": "Color 11",
  "342": "Color 12",
  "343": "Color 13",
  "344": "Color 14",
  "345": "Color 15",
  "700": "Screen",
  "800": "TV ON",
  "801": "TV OFF",
  "802": "TV Power",
  "900": "Recharge",
  "901": "Clean",
  "903": "Vac & Mop",
  "904": "Auto",
  "905": "Quiet",
  "906": "Standard",
  "907": "Strong",
  "908": "Max",
  "909": "Moist",
  "910": "Wet",
  "911": null,
  "912": null,
  "913": null,
  "914": null,
  "915": null,
  "916": null,
  "917": "Manual Control",
  "918": "Spot Clean",
  "1500": "Fully open",
  "1600": "Close Up",
  "1700": "Close Down",
  "2000": "Mute",
  "2001": "Mute",
  "2002": "Back",
  "2003": null,
  "2100": "Mute",
  "2101": "Play",
  "2102": "Forward",
  "2103": "Rewind",
  "2104": "Home",
  "2105": "Menu"
};

const escapeHtml = (value) =>
  String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");

class SwitchBotUrcPanel extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._entryId = null;
    this._remoteId = null;
    this._pageIndex = 0;
    this._buttonId = null;
    this._pageEditing = true;
    this._mode = "preset";
    this._draftActions = [];
    this._mappingDraftsByRemote = new Map();
    this._layoutDraftsByRemote = new Map();
    this._appearanceDraftsByRemote = new Map();
    this._hidPairingByRemote = new Map();
    this._presetDraftsByRemote = new Map();
    this._activeButton = null;
    this._activeEntryId = null;
    this._activeRemoteId = null;
    this._loading = false;
    this._error = null;
    this._notice = null;
    this._dirty = false;
    this._jsonValid = true;
    this._physical = null;
    this._nativeProfiles = [];
    this._nativeMenuGlyphs = [];
    this._physicalOrigins = {};
    this._physicalSources = [];
    // Catalog picker state. `available` stays null until the first lookup answers, so the
    // picker can say "loading" once instead of asking on every render.
    this._catalog = { available: null, types: [], remoteType: 2, brands: [], brand: "", search: "",
                      models: [], hxd: "", buttons: [], busy: "", error: "" };
    // Add-remote dialog: null when closed, otherwise the half-filled form.
    this._add = null;
    this._scenePanel = null;
    this._scenePanels = new Map();
    this._deviceSettings = null;
    this._sources = null;
    // Which remote's appearance editor is open.
    this._iconPickerFor = null;
    this._physicalStatus = "";
    this._physicalBusy = false;
  }

  set hass(value) {
    this._hass = value;
    if (this._actionSelectorEl) this._actionSelectorEl.hass = value;
    this._updateSelectOptionWarning();
    if (this.isConnected && !this._data && !this._loading) this._load();
  }

  set narrow(value) {
    this._narrow = value;
  }

  set route(value) {
    this._route = value;
  }

  set panel(value) {
    this._panel = value;
  }

  connectedCallback() {
    this._render();
    if (this._hass && !this._data) this._load();
    this._subscribe();
  }

  disconnectedCallback() {
    if (this._unsubscribe) this._unsubscribe();
    this._unsubscribe = null;
    clearTimeout(this._activeTimer);
  }

  async _refresh() {
    // One button: adopt whatever is installed on the remote, then reload. The import is
    // read-only towards the device, so it is safe to run on every refresh; a failure there
    // must still leave the reload to happen.
    if (!this._entryId) return this._load();
    this._stashLayout();
    this._physicalBusy = true;
    this._render();
    let adopted = 0;
    let dropped = 0;
    let importError = null;
    let readback = null;
    try {
      const result = await this._hass.callWS({
        type: `${DOMAIN}/studio/physical/import`, entry_id: this._entryId,
        ...(this._remoteId && this._remote()?.kind !== "scene" ? { remote_id: this._remoteId } : {}) });
      adopted = result?.imported || 0;
      dropped = result?.dropped || 0;
      importError = result?.appearance_error;
      readback = result?.native_readback;
    } catch (error) { importError = error?.message || String(error); }
    this._physical = null;
    this._physicalFor = null;
    this._physicalBusy = false;
    this._sources = null;
    await this._load(true);
    if (importError && !this._error) this._error = importError;
    if (!importError && (adopted || dropped || readback)) {
      const parts = [];
      if (adopted) parts.push(`${adopted} picked up from the device`);
      if (dropped) parts.push(`${dropped} no longer on the device, forgotten`);
      if (readback) {
        const hex = (value) => `0x${value.toString(16).padStart(2, "0")}`;
        parts.push(`Slot ${readback.slot}: ${this._nativeProfile(this._remote()?.native_type)?.title || this._remote()?.name || "Native remote"} · type ${hex(readback.device_type)}, screen mode ${hex(readback.mode)}, icon ${hex(readback.icon)}`);
      }
      this._notify(parts.join("; "));
    }
    this._render();
  }

  async _load(refresh = false) {
    this._loading = true;
    this._error = null;
    this._render();
    try {
      this._data = await this._hass.callWS({ type: `${DOMAIN}/studio/get`, ...(refresh ? {refresh: true} : {}) });
      this._normalizeSelection();
    } catch (error) {
      this._error = error?.message || String(error);
    } finally {
      this._loading = false;
      this._render();
      this._subscribe();
    }
  }

  async _subscribe() {
    if (!this._hass || this._unsubscribe) return;
    try {
      this._unsubscribe = await this._hass.connection.subscribeMessage(
        (event) => this._handleLiveEvent(event),
        { type: `${DOMAIN}/studio/subscribe` },
      );
    } catch (error) {
      this._error = `Live events unavailable: ${error?.message || error}`;
      this._render();
    }
  }

  _entries() {
    return this._data?.entries || [];
  }

  _entry() {
    return this._entries().find((item) => item.entry_id === this._entryId) || null;
  }

  _remote() {
    return this._entry()?.remotes.find((item) => item.remote_id === this._remoteId) || null;
  }

  _freeIndexOnPage(index) {
    // Which row a new button would take on this page, or null when there is no room.
    //
    // Only a submenu has rows to add: the Main page is the physical face, where every key
    // already exists on the device whether or not it carries a command. "Adding" one there
    // meant nothing — the key is already in your hand; what it needs is a command, which is
    // what selecting it offers.
    const page = this._physical?.pages?.find((item) => item.index === index);
    if (!page || !page.index) return null;
    const limit = this._physical.kind === "hid" ? 15 : 18;
    const taken = new Set(page.buttons.map((item) => item.index));
    for (let candidate = 0; candidate < limit; candidate += 1) {
      if (!taken.has(candidate)) return candidate;
    }
    return null;
  }

  _addKeyToCurrentPage() {
    const index = this._page()?.index;
    const page = this._physical?.pages?.find((item) => item.index === index);
    if (!page) return;
    const kind = this._physical.kind;
    const free = this._freeIndexOnPage(index);
    if (free === null) {
      this._notify("This page has no room for another row.", "warning");
      this._render();
      return;
    }
    page.buttons.push({
      index: free,
      transport: kind === "native" ? "native" : kind === "hid" ? "hid" : "ir",
      function: kind === "native" ? NATIVE_CUSTOM_FUNCTION : 115,
      code_hex: "",
    });
    this._buttonId = `p${page.index}_k${free}`;
    this._pageEditing = false;
    this._selectButton(this._button(), false);
    this._render();
  }

  _draftScope() {
    return JSON.stringify([this._entryId, this._remoteId]);
  }

  _mappingDrafts() {
    const scopes = this._mappingDraftsByRemote ??= new Map();
    const scope = this._draftScope();
    if (!scopes.has(scope)) scopes.set(scope, new Map());
    return scopes.get(scope);
  }

  _mappingKey(button) {
    return this._physical ? `p${button.button_page}_k${button.button_index}` : button.button_id;
  }

  _rememberMapping(button) {
    if (this._scenePanel?.draft) {
      this._scenePanel.draft.actions = structuredClone(this._draftActions);
      this._scenePanel.draft.actionsJson = this._actionJsonDraft;
      this._scenePanel.draft.actionsValid = this._jsonValid;
      return;
    }
    button ??= this._button();
    if (!button || !this._dirty) return;
    this._mappingDrafts().set(this._mappingKey(button), {
      mode: this._mode,
      actions: structuredClone(this._draftActions),
      valid: this._jsonValid,
      raw: this._actionJsonDraft,
    });
  }

  _stashLayout() {
    if (!this._physical) return;
    const scope = this._draftScope();
    if (this._physicalChanges()) {
      this._layoutDraftsByRemote.set(scope, {
        layout: this._physical, baseline: this._physicalBaseline, origins: this._physicalOrigins,
      });
    } else {
      this._layoutDraftsByRemote.delete(scope);
    }
  }

  _pageKeyEntries(page) {
    return [...(page?.buttons || [])].sort((a, b) => a.index - b.index).map((key) => ({
      key,
      origin: this._physicalOrigins[`p${page.index}_k${key.index}`],
      mapping: this._mappingDrafts().get(`p${page.index}_k${key.index}`),
    }));
  }

  _replacePageKeyOrder(page, entries) {
    const mappings = this._mappingDrafts();
    for (const key of page.buttons) {
      const id = `p${page.index}_k${key.index}`;
      delete this._physicalOrigins[id];
      mappings.delete(id);
    }
    page.buttons = entries.map(({ key, origin, mapping }, index) => {
      key.index = index;
      const id = `p${page.index}_k${index}`;
      if (origin) this._physicalOrigins[id] = origin;
      if (mapping) mappings.set(id, mapping);
      return key;
    });
  }

  _movePageKey(pageIndex, keyIndex, direction) {
    const page = this._physical?.pages?.find((item) => item.index === pageIndex);
    const entries = this._pageKeyEntries(page);
    const index = entries.findIndex(({ key }) => key.index === keyIndex);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= entries.length) return;
    [entries[index], entries[target]] = [entries[target], entries[index]];
    const movedKey = entries[target].key;
    this._replacePageKeyOrder(page, entries);
    this._selectButton(this._page()?.buttons.find((item) => item.button_index === movedKey.index), false);
    this._physicalStatus = "";
    this._render();
  }

  _removeMenu(page) {
    for (const key of page.buttons) {
      const id = `p${page.index}_k${key.index}`;
      delete this._physicalOrigins[id];
      this._mappingDrafts().delete(id);
    }
    this._physical.pages = this._physical.pages.filter((item) => item !== page);
    this._pageIndex = 0;
    this._pageEditing = false;
    this._selectButton(null, false);
    this._physicalStatus = "";
    this._render();
  }

  _removeMenuRow(page, key) {
    if (page.buttons.length === 1) return this._removeMenu(page);
    const entries = this._pageKeyEntries(page).filter((item) => item.key !== key);
    const index = key.index;
    this._replacePageKeyOrder(page, entries);
    const buttons = this._page()?.buttons || [];
    this._selectButton(buttons[Math.min(index, buttons.length - 1)], false);
    this._physicalStatus = "";
    this._render();
  }

  _availablePageIndexes() {
    const current = new Set((this._physical?.pages || []).map((page) => page.index));
    const profile = this._nativeProfile(this._physical?.native_type || this._physical?.template);
    const mainButtons = this._physical?.pages?.find((page) => page.index === 0)?.buttons || [];
    const supported = this._physical?.kind === "native"
      ? (profile?.subpages || []).filter((page) => page.link_index != null)
        .map((page) => ({ index: page.index, link: page.link_index }))
      : [1, 2, 3, 4].map((index) => ({ index, link: index - 1 }));
    return supported.filter(({ index, link }) => !current.has(index)
      && !mainButtons.some((key) => key.index === link)).map(({ index }) => index);
  }

  _identityRemovals() {
    const baseline = new Set((this._physicalBaseline?.pages || []).flatMap((page) =>
      (page.buttons || []).map((key) => `p${page.index}_k${key.index}`)));
    const present = new Set((this._physical?.pages || []).flatMap((page) =>
      (page.buttons || []).map((key) => `p${page.index}_k${key.index}`)));
    const survivingOrigins = new Set(Object.entries(this._physicalOrigins || {})
      .filter(([current]) => present.has(current)).map(([, origin]) => origin));
    return [...baseline].filter((identity) => !survivingOrigins.has(identity));
  }

  _layoutState(key) {
    const current = `p${key.button_page}_k${key.button_index}`;
    const original = this._physicalOrigins[current];
    const existed = (this._physicalBaseline?.pages || []).some((page) => page.buttons
      .some((item) => `p${page.index}_k${item.index}` === original));
    if (!existed) return "new";
    if (current !== original) return "moved";
    const before = (this._physicalBaseline?.pages || []).flatMap((page) => page.buttons
      .map((item) => ({ id: `p${page.index}_k${item.index}`, item })))
      .find((item) => item.id === original)?.item;
    const now = this._physical.pages.find((page) => page.index === key.button_page)
      ?.buttons.find((item) => item.index === key.button_index);
    if (before && now && (before.transport !== now.transport || before.function !== now.function
        || before.code_hex !== now.code_hex || before.glyph !== now.glyph)) return "edited";
    return "unchanged";
  }

  _pages() {
    if (this._remote()?.kind === "scene") return [];
    if (this._physical) {
      const remotePages = this._remote()?.pages || [];
      const nativeProfile = this._nativeProfile(this._physical.native_type || this._physical.template);
      const positions = ["A", "B", "C", "D", "ON", "OFF", "LEFT", "RIGHT", "UP",
        "DOWN", "OK", "BACK", "HOME", "KATA", "SOUNDOFF", "VOLADD", "VOLDEL", "CHUP", "CHDOWN"];
      return this._physical.pages.map((page) => {
        const linkedPositions = new Set(this._physical.pages.filter((item) => item.index)
          .map((item) => item.index - 1));
        const visibleMainPositions = page.index === 0
          ? Array.from({ length: 19 }, (_, index) => index).filter((index) => {
            if (positions[index] === "KATA" || linkedPositions.has(index)) return false;
            if (this._physical.kind !== "native") return true;
            return nativeProfile?.main_positions?.includes(index);
          }) : [];
        const physicalKeys = page.index === 0
          ? visibleMainPositions.map((index) => page.buttons.find((item) => item.index === index)
            || { index }) : page.buttons;
        const buttons = physicalKeys.map((key) => {
          const currentId = `p${page.index}_k${key.index}`;
          const origin = this._physicalOrigins[currentId];
          const identity = origin || currentId;
          const source = (!this._physicalBaseline || origin || !page.buttons.includes(key))
            ? remotePages.flatMap((item) => item.buttons || []).find((item) => item.button_id === identity)
            : null;
          const profileKey = page.index === 0
            ? nativeProfile?.main_keys?.find((item) => item.index === key.index) : null;
          const functionLabel = this._profileFunctionLabel(key.function);
          return {
            ...source,
            draft_only: !source,
            button_id: currentId,
            button_page: page.index,
            button_index: key.index,
            button_function: key.function ?? source?.button_function ?? profileKey?.function ?? 0,
            button_glyph: key.glyph,
            default_function: source?.default_function ?? profileKey?.function,
            layout_state: page.buttons.includes(key)
              ? this._layoutState({ button_page: page.index, button_index: key.index }) : "unchanged",
            position: page.index === 0 ? positions[key.index] || "" : "",
            label: page.index === 0 ? positions[key.index] || functionLabel
              : key.title || source?.label || functionLabel,
            actions: source?.actions || [],
            mode: source?.mode || "preset",
            has_override: source?.has_override || false,
          };
        });
        return { index: page.index, name: page.title || (page.index === 0 ? "Main" : `Page ${"ABCD"[page.index - 1]}`), buttons };
      });
    }
    const pages = [...(this._remote()?.pages || [])];
    for (const page of this._physical?.pages || []) {
      if (pages.some((item) => item.index === page.index)) continue;
      // Draft-only page: it has no server record until Save writes it to the remote.
      pages.push({
        index: page.index,
        name: page.index === 0 ? "Main" : `Page ${"ABCD"[page.index - 1] || page.index}`,
        draft_only: true,
        buttons: page.buttons.map((key) => ({
          button_id: `draft:${page.index}:${key.index}`,
          label: `Position ${key.index}`,
          position: "",
          button_page: page.index,
          button_index: key.index,
          button_function: key.function ?? 0,
          actions: [],
          mode: "preset",
          preset_action: null,
          draft_only: true,
        })),
      });
    }
    return pages.sort((a, b) => a.index - b.index);
  }

  _page() {
    const pages = this._pages();
    return pages.find((item) => item.index === this._pageIndex) || pages[0] || null;
  }

  _button() {
    return this._page()?.buttons.find((item) => item.button_id === this._buttonId) || null;
  }

  _ensureLayout() {
    if (!this._entryId || !this._remoteId) return;
    if (this._remote()?.kind === "scene") return;
    if (!this._remote()?.layout_editable) return;
    // Track the attempt, not its result. Keying this on `_physical` meant that a remote whose
    // layout cannot be loaded was retried from inside every render, and since the request ends
    // in another render that was an endless loop that took the whole panel down.
    const token = this._draftScope();
    if (this._physicalFor === token) return;
    this._physicalFor = token;
    this._physicalRequest = null;
    this._physical = null;
    this._physicalBaseline = null;
    this._openPhysical();
  }

  _normalizeSelection() {
    const entries = this._entries();
    if (!entries.some((item) => item.entry_id === this._entryId)) {
      this._entryId = entries[0]?.entry_id || null;
    }
    const remotes = this._entry()?.remotes || [];
    if (!remotes.some((item) => item.remote_id === this._remoteId)) {
      this._remoteId = remotes[0]?.remote_id || null;
    }
    if (this._remote()?.kind === "scene") {
      this._physical = null;
      this._openScenes(false, this._remote().scene_index);
      return;
    }
    this._scenePanel = null;
    const pages = this._pages();
    if (!pages.some((item) => item.index === this._pageIndex)) {
      this._pageIndex = pages[0]?.index ?? 0;
    }
    const buttons = this._page()?.buttons || [];
    if (!buttons.some((item) => item.button_id === this._buttonId)) {
      this._selectButton(buttons[0] || null, false);
    } else {
      this._selectButton(this._button(), false);
    }
  }

  _selectButton(button, rerender = true) {
    this._buttonId = button?.button_id || null;
    if (button && rerender) {
      this._pageEditing = false;
      this._iconPickerFor = null;
    }
    // A position with no function yet becomes one as soon as it is picked, using the meaning the
    // position already carries. No dialogue: the choice was made by clicking it.
    const draft = button ? this._draftKey(button) : null;
    if (rerender && draft && !draft.key.function && button.default_function) {
      draft.key.function = button.default_function;
    }
    const draftMapping = button && this._mappingDrafts().get(this._mappingKey(button));
    this._draftActions = structuredClone(draftMapping?.actions || button?.actions || []);
    this._dirty = Boolean(draftMapping);
    this._jsonValid = draftMapping?.valid ?? true;
    this._actionJsonDraft = draftMapping?.raw;
    const customNativeButton = this._physical?.kind === "native"
      && button?.button_function === NATIVE_CUSTOM_FUNCTION && !button.preset_action;
    this._mode = draftMapping?.mode ?? (button?.has_override
      ? button.actions.length ? "actions" : "disabled"
      : customNativeButton ? "actions" : "preset");
    if (rerender) this._render();
  }

  _handleLiveEvent(event) {
    if (this._scenePanel || this._physical || this._saving) return;
    if (!event?.remote_id || !event?.button_id) return;
    const sourceAddress = String(event.worws_address || event.address || "")
      .replaceAll(":", "")
      .replaceAll("-", "")
      .toLowerCase();
    for (const entry of this._entries()) {
      const entryAddress = String(entry.address || "")
        .replaceAll(":", "")
        .replaceAll("-", "")
        .toLowerCase();
      if (sourceAddress && sourceAddress !== entryAddress) continue;
      const remote = entry.remotes.find((item) => item.remote_id === event.remote_id);
      if (!remote) continue;
      const page = remote.pages.find((item) =>
        item.buttons.some((button) => button.button_id === event.button_id),
      );
      if (!page) continue;
      this._activeEntryId = entry.entry_id;
      this._activeRemoteId = remote.remote_id;
      this._activeButton = event.button_id;
      if (this._mappingDrafts().size || this._hasAppearanceChanges() || this._presetDraftsByRemote.has(this._draftScope())) {
        this._render();
        this._scheduleActiveClear();
        return;
      }
      this._entryId = entry.entry_id;
      this._remoteId = remote.remote_id;
      this._pageIndex = page.index;
      this._buttonId = event.button_id;
      this._normalizeSelection();
      this._render();
      this._scheduleActiveClear();
      break;
    }
  }

  _scheduleActiveClear() {
    clearTimeout(this._activeTimer);
    this._activeTimer = setTimeout(() => {
      this._activeButton = null;
      this._activeEntryId = null;
      this._activeRemoteId = null;
      this._render();
    }, 900);
  }

  _isActiveButton(item) {
    return this._activeEntryId === this._entryId
      && this._activeRemoteId === this._remoteId
      && this._activeButton === item.button_id;
  }

  _status(button) {
    if (button.has_override && button.actions.length) return ["custom", "Custom action"];
    if (button.has_override) return ["disabled", "Disabled"];
    if (button.preset_action) return ["preset", button.preset_action.replaceAll("_", " ")];
    return ["none", "No action"];
  }

  _draftLabel(button) {
    return { new: "Added", moved: "Moved", edited: "Edited" }[button.layout_state] || "";
  }

  _nativeGlyphSrc(button) {
    const functionCode = button?.button_glyph ?? button?.button_function;
    if (!Number.isInteger(functionCode) || !Object.hasOwn(NATIVE_GLYPH_LABELS, functionCode)) return "";
    return `/switchbot_urc_static/native-glyphs/keyfun-${functionCode.toString(16).padStart(4, "0")}.png`;
  }

  _nativeGlyph(button, className = "") {
    const src = this._nativeGlyphSrc(button);
    return src ? `<img class="native-glyph ${className}" src="${src}" alt="" aria-hidden="true">` : "";
  }

  _renderGlyphPicker(owner, field, label, defaultFunction, allowedCodes = null) {
    const selected = owner[field];
    const current = selected ?? defaultFunction;
    const caption = NATIVE_GLYPH_LABELS[current];
    const preview = this._nativeGlyph({ button_glyph: selected, button_function: defaultFunction });
    const unsupported = selected !== undefined && allowedCodes && !allowedCodes.includes(selected);
    return `<details class="glyph-picker">
      <summary>${preview}<b>${label}</b>${caption ? ` <span>· ${escapeHtml(caption)}</span>` : ""}</summary>
      ${unsupported ? '<p class="small" role="status">Choose a menu icon or reset to the default before saving.</p>' : ""}
      <button class="secondary compact" data-glyph-field="${field}" data-glyph-code=""
        ${selected === undefined ? "disabled" : ""}>Reset to default</button>
      <div class="glyph-grid" role="group" aria-label="${label}">
        ${Object.entries(NATIVE_GLYPH_LABELS).map(([value, caption]) => {
          const code = Number(value);
          if (allowedCodes && !allowedCodes.includes(code)) return "";
          const iconId = `0x${code.toString(16).padStart(4, "0")}`;
          const name = caption || "No caption";
          return `<button type="button" data-glyph-field="${field}" data-glyph-code="${code}"
            aria-label="${escapeHtml(name)} (${iconId})" aria-pressed="${code === current}">
            ${this._nativeGlyph({ button_function: code })}<span>${escapeHtml(name)}</span></button>`;
        }).join("")}
      </div>
    </details>`;
  }

  _renderMenuIcon(page) {
    if (!page?.index || this._physical?.kind !== "native") return "";
    const owner = this._physical.pages.find((item) => item.index === page.index);
    if (!owner) return "";
    const profile = this._nativeProfile(this._physical.native_type || this._physical.template);
    const defaultFunction = profile?.main_keys?.find((key) =>
      key.index === page.index - 1 && !key.actionable)?.function
      ?? profile?.subpages?.find((item) => item.index === page.index)?.link_function;
    return this._renderGlyphPicker(owner, "link_glyph", "Menu icon", defaultFunction, this._nativeMenuGlyphs);
  }

  _renderPageEditor(page, button, remote) {
    const editingMenu = this._pageEditing || !button;
    const freePages = this._availablePageIndexes();
    const row = page.buttons.findIndex((item) => item.button_id === button?.button_id);
    return `<section class="page-editor">
      <div>
        <span class="page-kicker">Menu · key ${"ABCD"[page.index - 1]}</span>
        <div class="page-heading">
          <h2>${escapeHtml(page.name)}</h2>
          <button class="secondary compact destructive" id="removeThisPage" ${this._physicalBusy ? "disabled" : ""}>Delete menu</button>
        </div>
        <p class="small">${page.buttons.length} row${page.buttons.length === 1 ? "" : "s"}</p>
      </div>
      <div class="page-tools">
        <button class="primary compact" id="addKeyToPage" ${this._freeIndexOnPage(page.index) === null || this._physicalBusy ? "disabled" : ""}>＋ Add row</button>
        ${freePages.length ? `<label class="page-move">Move to<select id="moveCurrentPage"><option value="">Choose key…</option>${freePages.map((index) => `<option value="${index}">Key ${"ABCD"[index - 1]}</option>`).join("")}</select></label>` : ""}
      </div>
      <div class="mode-tabs page-editor-tabs">
        <button data-page-editor="menu" class="${editingMenu ? "selected" : ""}">Menu settings</button>
        <button data-page-editor="row" class="${!editingMenu ? "selected" : ""}" ${button ? "" : "disabled"}>${button ? `Row ${page.buttons.findIndex((item) => item.button_id === button.button_id) + 1}` : "Select a row"}</button>
      </div>
      ${!editingMenu && row >= 0 ? `<div class="page-tools row-tools">
        <button class="secondary compact" id="moveRowUp" ${row === 0 ? "disabled" : ""}>↑ Move up</button>
        <button class="secondary compact" id="moveRowDown" ${row === page.buttons.length - 1 ? "disabled" : ""}>↓ Move down</button>
        <button class="secondary compact destructive" id="removeKey">${page.buttons.length === 1 ? "Delete last row and menu" : "Delete row"}</button>
      </div>` : ""}
      ${editingMenu ? this._renderMenuIcon(page)
        + (page.buttons.length ? '<p class="small">Select a row on the remote to edit its command and Home Assistant actions.</p>'
          : '<div class="explanation"><b>This menu is empty.</b><span>Add a row, configure it, then save the page to the remote.</span></div>')
        : this._editor(button, remote)}
    </section>`;
  }

  _iconImage(name) {
    const asset = APP_ICON_ASSETS[name] || APP_ICON_ASSETS.light;
    return `<img class="ic-img" src="/switchbot_urc_static/app-icons/${asset}.webp"
      alt="" aria-hidden="true">`;
  }

  // Firmware picture a nonzero wire icon selects on native and text-remote tiles.
  _firmwareIconSrc(name) {
    const id = (this._entry()?.icon_artwork || {})[name];
    return id == null ? "" : `/switchbot_urc_static/artwork/profile-${Number(id).toString(16).padStart(2, "0")}.png`;
  }

  _nativeArtworkSrc(profile, artworkId = profile?.artwork_id) {
    if (artworkId == null) return "";
    // Catalog previews use the normal illustration. Variant state is a separate DSP runtime byte.
    return `/switchbot_urc_static/artwork/profile-${artworkId.toString(16).padStart(2, "0")}.png`;
  }

  _nativeProfile(type) {
    return [...this._nativeProfiles, ...(this._sources?.native_options?.screen_profiles || [])].find((item) =>
      item.value === type || item.equivalent_types?.includes(type));
  }

  _nativeTypeChoices(profiles, selected, dataAttribute) {
    return `<div class="native-type-grid">${profiles.map((item) => {
      const artwork = this._nativeArtworkSrc(item);
      const name = escapeHtml(item.title || item.value);
      const active = item.value === selected || item.equivalent_types?.includes(selected);
      return `<button class="native-type-choice${active ? " selected" : ""}"
        type="button" data-${dataAttribute}="${escapeHtml(item.value)}"
        aria-label="${name}" title="${name}" aria-pressed="${!!active}">
        <span class="native-type-art" aria-hidden="true">${artwork
          ? `<img src="${artwork}" alt="">` : "—"}</span>
      </button>`;
    }).join("")}</div>`;
  }

  _hidArtworkSrc(deviceType, artworkId) {
    if (!(deviceType in HID_PROFILE_ARTWORK)) return "";
    const id = artworkId == null ? HID_PROFILE_ARTWORK[deviceType]
      : Number(artworkId).toString(16).padStart(2, "0");
    return id ? `/switchbot_urc_static/artwork/profile-${id}.png` : "";
  }

  _irArtworkSrc(remote) {
    const type = /^IR_(\d+)$/.exec(remote.device_type || "");
    const id = type ? IR_PROFILE_ARTWORK[Number(type[1])]
      : remote.device_type === "IR_TV" ? "18" : null;
    if (!id && remote.artwork_id == null) return "";
    const profile = remote.artwork_id == null ? id
      : Number(remote.artwork_id).toString(16).padStart(2, "0");
    return `/switchbot_urc_static/artwork/profile-${profile}.png`;
  }

  // Each key the WoRWS actually has, by its firmware position name.
  _key(byPos, tag, body, label) {
    if (tag === "KATA") {
      return `<g class="k ghost" tabindex="-1"><title>KATA · Reserved for the Universal Remote</title>${body}</g>`;
    }
    const button = byPos[tag];
    if (!button) {
      return `<g class="k ghost" tabindex="-1"><title>${tag} — not used by this remote</title>${body}</g>`;
    }
    const [status, statusLabel] = this._status(button);
    const selected = button.button_id === this._buttonId ? " selected" : "";
    const pressed = this._isActiveButton(button) ? " pressed" : "";
    const draft = this._draftLabel(button);
    return `<g class="k ${status}${selected}${pressed}${draft ? " unsaved" : ""}" role="button" tabindex="0"
      data-button="${escapeHtml(button.button_id)}"><title>${escapeHtml(label || tag)} · ${
      escapeHtml(statusLabel)} · ${escapeHtml(button.label)}${draft
        ? ` · ${draft} in draft` : ""}</title>${body}</g>`;
  }

  // Compare the chosen icon with the byte the remote carries, not with a name: a name can be the
  // app's placeholder, and "Type default" must count as a change from any nonzero icon.
  _iconChanged(remote, draft) {
    if (!remote || draft?.icon == null) return false;
    const codes = this._entry()?.icon_codes || {};
    const chosen = codes[draft.icon];
    if (Number.isInteger(remote.icon_code) && Number.isInteger(chosen)) return chosen !== remote.icon_code;
    return draft.icon !== remote.icon;
  }

  _hasAppearanceChanges() {
    const remote = this._remote();
    const draft = this._appearanceDraftsByRemote?.get(this._draftScope());
    return Boolean(remote && draft && (draft.name.trim() !== remote.name || this._iconChanged(remote, draft)
      || this._captionsChanged(remote, draft) || this._intervalChanged(remote, draft)));
  }

  _intervalChanged(remote, draft) {
    return Boolean(remote?.matter && draft?.interval != null && draft.interval !== ""
      && Number(draft.interval) !== remote.matter.min_interval);
  }

  _captionsChanged(remote, draft) {
    return Boolean(remote?.matter && draft?.captions
      && draft.captions.some((text, index) =>
        text.trim() !== (remote.matter.fields || remote.matter.captions)[index]));
  }

  _captionsProblem(remote, draft) {
    if (!remote?.matter) return "";
    const [low, high] = remote.matter.interval_range || [0, 3600];
    if (draft?.interval != null && draft.interval !== "") {
      const seconds = Number(draft.interval);
      if (!Number.isInteger(seconds) || seconds < low || seconds > high) {
        return `The update interval is between ${low} and ${high} seconds.`;
      }
    }
    if (!draft?.captions) return "";
    const encoder = new TextEncoder();
    for (const [index, text] of draft.captions.entries()) {
      const bytes = encoder.encode(text.trim()).length;
      if (!bytes) return `Give button ${"ABCD"[index]} a caption.`;
      // A template is cut to fit when it is rendered, so only a plain caption has a limit here.
      if (!isTemplate(text) && bytes > remote.matter.max_bytes) {
        return `Caption ${"ABCD"[index]} is longer than ${remote.matter.max_bytes} bytes.`;
      }
    }
    return "";
  }

  async _saveAppearance() {
    if (!this._hasAppearanceChanges()) return;
    const remote = this._remote();
    const scope = this._draftScope();
    const draft = this._appearanceDraftsByRemote.get(scope);
    const name = draft.name.trim();
    const icon = draft.icon;
    const request = { entry_id: this._entryId, remote_id: this._remoteId };
    let result;
    if (remote.matter) {
      // The text remote's screen draws no picture, but its list tile reads the same wire icon
      // byte as every other tile, and a caption rewrite resends the whole record, so both
      // travel in one save.
      const iconChanged = this._iconChanged(remote, draft);
      const intervalChanged = this._intervalChanged(remote, draft);
      if (this._captionsChanged(remote, draft) || iconChanged || intervalChanged) {
        const captions = (draft.captions || remote.matter.fields || remote.matter.captions)
          .map((text) => text.trim());
        await this._hass.callWS({
          ...request, type: `${DOMAIN}/studio/matter/save`, captions,
          ...(iconChanged ? { icon } : {}),
          ...(draft.interval != null && draft.interval !== "" ? { min_interval: Number(draft.interval) } : {}) });
        // What is on the remote now is known for a plain caption; a template shows after a reload.
        remote.matter.captions = captions.map((text, index) =>
          isTemplate(text) ? remote.matter.captions[index] : text);
        remote.matter.fields = captions;
        if (draft.interval != null && draft.interval !== "") remote.matter.min_interval = Number(draft.interval);
        if (iconChanged) {
          remote.icon = icon;
          remote.artwork_id = (this._entry()?.icon_artwork || {})[icon] ?? null;
        }
      }
      if (name !== remote.name) {
        const renamed = await this._hass.callWS({ ...request, type: `${DOMAIN}/studio/remote/rename`, name });
        if (renamed?.warning) result = renamed;
        remote.name = name;
      }
      this._appearanceDraftsByRemote.delete(scope);
      return result?.warning;
    }
    if (this._iconChanged(remote, draft)) {
      const isPageRemote = remote.device_type in HID_PROFILE_ARTWORK
        || String(remote.device_type).startsWith("IR_");
      if (isPageRemote) {
        // HID and IR pages are resent from the saved Main-page data with only the icon changed.
        result = await this._hass.callWS({ ...request, type: `${DOMAIN}/studio/remote/update_page_icon`, icon });
        // "Original" gives back the icon the remote had; the answer says which one that was.
        remote.icon = result?.icon ?? icon;
        remote.icon_code = result?.icon_code ?? remote.icon_code;
        // null lets the HID/IR artwork helpers fall back to the type's own picture (icon 0).
        remote.artwork_id = (this._entry()?.icon_artwork || {})[remote.icon] ?? null;
        this._appearanceDraftsByRemote.delete(scope);
        return result?.warning;
      }
      if (!remote.can_test_native_icon) {
        result = await this._hass.callWS({ ...request, type: `${DOMAIN}/studio/remote/recreate`, icon, name });
        this._appearanceDraftsByRemote.delete(scope);
        this._physicalFor = null;
        return result?.warning;
      }
      result = await this._hass.callWS({ ...request, type: `${DOMAIN}/studio/remote/update_native_icon`, icon });
      remote.icon = icon;
      // Icon 0 hands the picture back to the device type; any other icon picks its own.
      remote.artwork_id = (this._entry()?.icon_artwork || {})[icon]
        ?? this._nativeProfile(remote.native_type || remote.device_type)?.artwork_id ?? remote.artwork_id;
    }
    if (name !== remote.name) {
      const renamed = await this._hass.callWS({ ...request, type: `${DOMAIN}/studio/remote/rename`, name });
      if (renamed?.warning) result = renamed;
      remote.name = name;
    }
    this._appearanceDraftsByRemote.delete(scope);
    return result?.warning;
  }

  _renderScreen(page) {
    // Real HTML inside the SVG screen, so the list scrolls like the device's own does instead
    // of silently cutting off whatever does not fit.
    if ((page?.index ?? 0) !== 0) {
      const keys = page?.buttons || [];
      if (!keys.length) {
        return `<p class="scr-empty">This page has no buttons yet</p>`;
      }
      const catalogGlyphs = this._remote()?.ir_screen_preview?.catalog_glyphs;
      return keys.map((item) => {
        const [status] = this._status(item);
        const on = item.button_id === this._buttonId;
        const draft = this._draftLabel(item);
        const glyph = this._nativeGlyph(catalogGlyphs
          ? { button_glyph: catalogGlyphs[item.button_function] } : item, "scr-icon");
        return `<div class="scr-row k ${status}${on ? " on" : ""}${draft ? " unsaved" : ""}" role="button" tabindex="0"
          data-button="${escapeHtml(item.button_id)}" title="${escapeHtml(item.label)}${draft ? ` · ${draft} in draft` : ""}">
          ${glyph}
          <span class="pos">${escapeHtml(item.position || `#${item.button_index + 1}`)}</span>
          <span class="nm">${escapeHtml(item.label)}</span></div>`;
      }).join("");
    }
    const remotes = this._entry()?.remotes || [];
    if (!remotes.length && !this._scenePanel?.draft) return `<p class="scr-empty">No remotes yet</p>`;
    return remotes.map((item) => {
      const current = item.remote_id === this._remoteId;
      if (item.kind === "scene") {
        const preview = current && this._scenePanel?.draft ? this._scenePanel.draft : item;
        return `<div class="scr-row${current ? " on" : ""}"><button class="k pick-remote" type="button" data-remote="${escapeHtml(item.remote_id)}" title="${escapeHtml(item.name)} · Scene">
          <span class="scene-tile" style="background-image:url(/switchbot_urc_static/artwork/scene-background-${preview.color}.png)">${this._sceneIcon(preview.icon)}</span>
          <span class="nm">${escapeHtml(preview.name)}</span></button>
          ${current ? '<button class="k ic-btn" data-scene-appearance title="Edit name and appearance">✎</button>' : ""}</div>`;
      }
      const nativeProfile = item.can_test_native_icon
        ? this._nativeProfile(item.native_type || item.device_type) : null;
      const artwork = item.can_test_native_icon
        ? this._nativeArtworkSrc(nativeProfile, item.artwork_id)
        : item.matter ? (this._firmwareIconSrc(item.icon) || MATTER_ARTWORK)
          : this._hidArtworkSrc(item.device_type, item.artwork_id) || this._irArtworkSrc(item);
      return `<div class="scr-row${current ? " on" : ""}">
        <button class="k pick-remote" type="button"
          data-remote="${escapeHtml(item.remote_id)}"
          title="${escapeHtml(item.name)} · ${escapeHtml(item.device_type)}">
          ${artwork ? `<img class="ic-img" src="${artwork}" alt="">`
            : item.can_test_native_icon ? `<span class="ic-fallback" aria-hidden="true">▣</span>`
              : this._iconImage(item.icon)}<span class="nm">${escapeHtml(item.name)}</span></button>
        ${current && item.layout_editable ? `<button class="k ic-btn" data-icon-for="${escapeHtml(item.remote_id)}"
          title="Edit this remote's name and appearance">✎</button>` : ""}
      </div>`;
    }).join("") + (this._scenePanel?.draft && this._scenePanel.draft.index == null
      ? `<div class="scr-row on"><button class="k pick-remote" type="button" data-scene-appearance>
          <span class="scene-tile" style="background-image:url(/switchbot_urc_static/artwork/scene-background-${this._scenePanel.draft.color}.png)">${this._sceneIcon(this._scenePanel.draft.icon)}</span>
          <span class="nm">${escapeHtml(this._scenePanel.draft.name || "New scene")}</span></button></div>` : "");
  }

  _renderAppearance(remote) {
    const isNative = !!remote.can_test_native_icon;
    const native = this._physical?.kind === "native";
    const isHid = remote.device_type in HID_PROFILE_ARTWORK;
    const isIr = String(remote.device_type).startsWith("IR_");
    const profile = native
      ? this._nativeProfile(this._physical.native_type || this._physical.template) : null;
    const editing = this._iconPickerFor === remote.remote_id;
    const draft = this._appearanceDraftsByRemote.get(this._draftScope());
    const pickedIcon = draft?.icon ?? remote.icon;
    const choices = this._entry()?.icons || [];
    const installedArtwork = this._physical?.native_type === remote.native_type ? remote.artwork_id : undefined;
    const artwork = native ? this._nativeArtworkSrc(profile, installedArtwork)
      : this._hidArtworkSrc(remote.device_type, remote.artwork_id) || this._irArtworkSrc(remote);
    const isMatter = !!remote.matter;
    // Every tile takes any wire icon: the firmware turns a nonzero icon into its own picture
    // whatever the device type is, and icon 0 gives the picture back to the type.
    const firmwareIcons = isNative || isMatter || isHid || isIr;
    const canChooseIcon = true;
    const iconChoices = firmwareIcons ? ["device", ...choices] : choices;
    const pageRemote = isHid || isIr;
    const iconEditable = remote.icon_editable !== false;
    const iconLabel = (name) => name === "device" ? (pageRemote ? "Original" : "Type default")
      : (APP_ICON_LABELS[name] || name);
    // "Type default" / "Original" shows the picture it gives back, not a placeholder.
    const defaultSrc = remote.default_artwork_id == null ? ""
      : `/switchbot_urc_static/artwork/profile-${Number(remote.default_artwork_id).toString(16).padStart(2, "0")}.png`;
    const iconTile = (name) => {
      if (!firmwareIcons) return this._iconImage(name);
      const src = name === "device" ? defaultSrc : this._firmwareIconSrc(name);
      return src ? `<img class="ic-art" src="${src}" alt="" aria-hidden="true">`
        : `<span class="ic-art ic-art-default" aria-hidden="true">↺</span>`;
    };
    const matterArt = this._firmwareIconSrc(pickedIcon) || MATTER_ARTWORK;
    const matterCaptions = draft?.captions ?? remote.matter?.fields ?? remote.matter?.captions ?? [];
    const hidPairing = isHid ? this._hidPairingByRemote?.get(this._draftScope()) : null;
    return `<section class="appearance">
      <div class="appearance-head"><div><b>Appearance</b><span>How this remote is shown and arranged</span></div></div>
      <div class="appearance-grid">
        ${native ? `<section class="native-type-panel"><div class="native-type-heading"><b>Type</b>
          <span>Choose the built-in screen and button layout.</span></div>
          ${this._nativeTypeChoices(this._nativeProfiles, this._physical.native_type || this._physical.template, "native-profile")}
        </section>` : isMatter ? `<div class="appearance-part">
          <div class="artwork-preview"><img src="${matterArt}" alt="Firmware illustration for a text remote"></div>
          <div class="appearance-part-body"><b>Text remote</b>
            <p>Four buttons A–D with the captions below. The list picture follows the icon you pick; Type default keeps the firmware's own text-remote picture.</p>
          </div>
        </div>` : isHid || isIr ? `<div class="appearance-part">
          <div class="artwork-preview">${artwork ? `<img src="${artwork}" alt="Firmware illustration for ${escapeHtml(native ? profile?.title : remote.device_type)}">` : "—"}</div>
          <div class="appearance-part-body">
            ${isHid ? `<b>HID screen</b><p>This illustration comes from the selected HID type. An icon chosen below replaces it.</p>`
              : `<b>IR screen</b><p>${artwork ? "The IR type and saved icon select this built-in illustration. An icon chosen below replaces it." : "No decoded firmware illustration is available for this IR type."}</p>`}
          </div>
        </div>` : ""}
        ${canChooseIcon && !firmwareIcons ? `<div class="appearance-part">
          <div class="app-icon-preview">${this._iconImage(pickedIcon)}</div>
          <div class="appearance-part-body"><b>Remote list icon</b>
            <p>${escapeHtml(APP_ICON_LABELS[pickedIcon] || pickedIcon)} · ${native
              ? "shown beside this remote in the selector; separate from its screen profile."
              : "shown beside this remote in the selector."}</p>
          </div>
        </div>` : ""}
      </div>
      ${editing ? `<div class="appearance-editor">
        <label>Name on the remote<input data-rename-input="1" maxlength="30" spellcheck="false"
          value="${escapeHtml(draft?.name ?? remote.name)}"></label>
        ${isMatter ? this._renderMatterCaptionFields(matterCaptions, remote.matter.max_bytes, remote.matter.captions) : ""}
        ${isMatter ? this._renderMatterInterval(draft?.interval ?? remote.matter.min_interval, remote.matter.interval_range) : ""}
        ${canChooseIcon && !iconEditable ? `<span class="appearance-field-label">Illustration</span>
        <p class="appearance-note">This remote was imported from the SwitchBot account, so Studio does not hold
          the pages that are on it and will not rewrite them. To choose its icon, install it again with
          <b>Add a remote</b> and <b>Replace an existing copy</b>.</p>` : ""}
        ${canChooseIcon && iconEditable ? `<span class="appearance-field-label">${firmwareIcons ? "Illustration" : "Device icon"}</span>
        ${firmwareIcons ? `<p class="appearance-note">${isMatter
          ? "The remote list shows the picture this icon selects."
          : isIr ? "A chosen icon overrides the picture that the IR type selects. Confirmed on real HID and IR remotes."
          : "A chosen icon overrides the picture that Type selects, on the list and on the remote's own screen."}</p>` : ""}
        <div class="appearance-icon-grid">${iconChoices.map((name) => `<button
          class="appearance-icon-choice${name === pickedIcon ? " selected" : ""}"
          data-pick-icon="${escapeHtml(name)}" type="button" aria-label="${escapeHtml(iconLabel(name))}"
          aria-pressed="${name === pickedIcon}">${iconTile(name)}<span>${escapeHtml(iconLabel(name))}</span></button>`).join("")}</div>` : ""}
        ${isHid ? `<div class="action-box">
          <div class="key-actions"><button class="secondary compact" id="enterHidPairMode"
            ${hidPairing?.busy || this._physicalBusy ? "disabled" : ""}>Enter pairing mode</button></div>
          ${this._feedback(hidPairing?.message, "info", "Bluetooth pairing")}
        </div>`
          : ""}
      </div>` : ""}
      ${native ? this._renderNativeProfileWarnings() : ""}
    </section>`;
  }

  _renderFace(page, screenContent) {
    const byPos = {};
    (page?.buttons || []).forEach((item) => {
      byPos[String(item.position || "").toUpperCase()] = item;
    });
    const key = (tag, body, label) => this._scenePanel
      ? `<g class="k inactive">${body}</g>` : this._key(byPos, tag, body, label);
    const pages = this._scenePanel ? [] : this._pages();
    const mainButtons = pages.find((item) => item.index === 0)?.buttons || [];
    const softkeys = Object.fromEntries(mainButtons.map((item) => [
      String(item.position || "").toUpperCase(), item,
    ]));
    const profile = this._scenePanel ? null : this._nativeProfile(this._physical?.native_type || this._physical?.template);
    const isIr = this._physical?.kind === "ir"
      || String(this._remote()?.device_type || "").startsWith("IR_");
    const irPreview = this._remote()?.ir_screen_preview;
    // Glyphs are drawn around their own origin and moved onto the key's centre, so a key and
    // its mark cannot drift apart the way hand-placed coordinates did.
    const mark = (cx, cy, d) => `<path d="${d}" transform="translate(${cx} ${cy})" class="mark"/>`;
    const cap = (cx, cy, r) => `<circle cx="${cx}" cy="${cy}" r="${r}" class="cap"/>`;
    // Rotate one annular sector for all four keys. Leave space between the sectors and OK
    // for the widest selection outline.
    const direction = (angle) => `<g transform="translate(150 427) rotate(${angle})">
      <path d="M-32.8-37.7 A50 50 0 0 1 32.8-37.7 L19.7-22.6 A30 30 0 0 0-19.7-22.6 Z" class="cap seg"/>
      ${mark(0, -39, "M-6 3l6-6 6 6")}
    </g>`;
    // A rocker half, given the centre of that half so it lines up with its own glyph. `up`
    // rounds the top end, `down` the bottom; both are 36 across and 36 tall.
    const rocker = (cx, cy, up) => up
      ? `<path d="M${cx - 18} ${cy}a18 18 0 0 1 36 0v18h-36z" class="cap"/>`
      : `<path d="M${cx - 18} ${cy}a18 18 0 0 0 36 0v-18h-36z" class="cap"/>`;
    const svg = `
      <svg class="device" viewBox="0 0 300 657" role="group" aria-label="Universal Remote">
        <defs>
          <linearGradient id="body" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stop-color="#f0f0f2"/><stop offset="30%" stop-color="#fff"/>
            <stop offset="70%" stop-color="#fff"/><stop offset="100%" stop-color="#e2e2e6"/>
          </linearGradient>
          <radialGradient id="logo" cx="35%" cy="35%" r="65%">
            <stop offset="0%" stop-color="#ff4d4d"/><stop offset="70%" stop-color="#c00"/>
            <stop offset="100%" stop-color="#800"/>
          </radialGradient>
        </defs>
        <rect x="35" y="20" width="230" height="617" rx="45" fill="url(#body)" class="shell"/>
        <path d="M35 65 C35 40 55 20 80 20 H220 C245 20 265 40 265 65 V296 H35 Z" class="glass"/>
        <path d="M48 58 C50 43 63 32 80 32 H220 C237 32 250 43 252 58" class="glass-edge"/>
        <foreignObject x="35" y="64" width="230" height="198">
          <div xmlns="http://www.w3.org/1999/xhtml" class="scr-scroll" tabindex="0"
            data-screen-key="${escapeHtml(`${this._entryId}:${page?.index ?? 0}:${page?.index ? this._remoteId : "home"}`)}">
            ${screenContent ?? this._renderScreen(page)}
          </div>
        </foreignObject>
        <g class="scr-sep"><path d="M35 262h230"/></g>
        <g class="screen-softkeys">
        ${Array.from("ABCD", (tag, index) => {
          const linked = pages.find((item) => item.index === index + 1);
          const linkFunction = profile?.main_keys?.find((item) =>
            item.index === index && !item.actionable)?.function
            ?? profile?.subpages?.find((item) => item.index === index + 1)?.link_function;
          const linkDraft = this._physical?.pages.find((item) => item.index === linked?.index);
          const linkGlyph = linkDraft?.link_glyph;
          const glyphButton = linked
            ? { button_function: linkFunction, button_glyph: linkGlyph }
            : softkeys[tag];
          // The IR A–D widget reads keyFun from the Main-page record, including for menu links.
          // WoRWS leaves positions with no record or keyFun zero empty.
          const disabledFunction = irPreview?.disabled_softkeys?.[index];
          const recordedFunction = linked
            ? Number.parseInt(linkDraft?.link_record?.slice(2, 6), 16)
            : glyphButton?.button_function;
          const irFunction = irPreview?.softkeys
            ? irPreview.softkeys[index] : recordedFunction || disabledFunction;
          const glyphSrc = isIr
            ? (irFunction ? this._nativeGlyphSrc({ button_function: irFunction }) : "")
            : this._nativeGlyphSrc(glyphButton);
          const dim = isIr && disabledFunction && !recordedFunction;
          const x = 52 + index * 52;
          const shape = `<rect x="${x}" y="265" width="44" height="27" rx="5" class="cap"/>
            ${glyphSrc ? `<image href="${glyphSrc}" x="${x + 6}" y="269" width="19" height="19"${dim ? ' opacity="0.5"' : ""}/>` : ""}
            <text x="${x + (glyphSrc ? 33 : 22)}" y="282" class="cap-t">${tag}</text>`;
          // A key that opens a page has no command of its own: that is what the firmware does
          // with it, and it is why it cannot carry a Home Assistant action.
          if (linked) {
            const previousLink = this._physicalBaseline?.pages.find((item) => item.index === linked.index);
            const changed = this._physical && (!previousLink || previousLink.link_glyph !== linkGlyph
              || previousLink.link_record !== linkDraft?.link_record);
            return `<g class="k link${page?.index === linked.index ? " current-page" : ""}${changed ? " unsaved" : ""}"
              role="button" tabindex="0" data-page-link="${linked.index}">
              <title>${escapeHtml(tag)} opens ${escapeHtml(linked.name)}</title>${shape}</g>`;
          }
          return this._scenePanel ? `<g class="k inactive">${shape}</g>` : this._key(softkeys, tag, shape, tag);
        }).join("")}
        </g>

        <g transform="translate(0 -23)">
        ${key("ON", `${cap(88, 362, 18)}<text x="88" y="366" class="cap-t">ON</text>`, "On")}
        ${key("OFF", `${cap(212, 362, 18)}<text x="212" y="366" class="cap-t">OFF</text>`, "Off")}

        <circle cx="150" cy="427" r="58" class="cap ring"/>
        ${key("UP", direction(0), "Up")}
        ${key("DOWN", direction(180), "Down")}
        ${key("LEFT", direction(-90), "Left")}
        ${key("RIGHT", direction(90), "Right")}
        ${key("OK", `${cap(150, 427, 26)}<text x="150" y="431" class="cap-t">OK</text>`, "OK")}

        ${key("BACK", `${cap(88, 510, 18)}${mark(88, 510, "M-2-6l-4 4 4 4M-6-2H2a4 4 0 0 1 0 8H-2")}`, "Back")}
        ${key("KATA", `<circle cx="150" cy="510" r="16" fill="url(#logo)" class="logo"/><path d="M-2-7h5l-3 6h4l-7 9 2-7h-4z" transform="translate(150 510)" class="logo-mark"/>`, "SwitchBot")}
        ${key("HOME", `${cap(212, 510, 18)}${mark(212, 510, "M-6 1l6-6 6 6v5h-4v-4h-4v4h-4z")}`, "Home")}

        ${key("VOLADD", `${rocker(88, 572, true)}${mark(88, 572, "M0-6v12M-6 0h12")}`, "Volume up")}
        ${key("VOLDEL", `${rocker(88, 612, false)}${mark(88, 612, "M-6 0h12")}`, "Volume down")}
        ${key("SOUNDOFF", `${cap(150, 560, 18)}${mark(150, 560, "M-8-3h3l3-3v12l-3-3h-3z")}${mark(150, 560, "M3-3l5 5m0-5l-5 5")}`, "Mute")}
        ${key("CHUP", `${rocker(212, 572, true)}${mark(212, 572, "M-5 3l5-5 5 5")}`, "Channel up")}
        ${key("CHDOWN", `${rocker(212, 612, false)}${mark(212, 612, "M-5-3l5 5 5-5")}`, "Channel down")}
        </g>
      </svg>`;
    return svg;
  }

  _render() {
    if (!this.shadowRoot) return;
    // A throw while building the markup used to leave an empty shadow root and a blank page,
    // which hides the very message that would explain it. Render failures are shown instead.
    try {
      this._renderUnsafe();
    } catch (error) {
      console.error("SwitchBot URC panel failed to render", error);
      this.shadowRoot.innerHTML = `<style>${this._styles()}</style><main><div class="error">
        <b>The panel could not be drawn.</b><br>${escapeHtml(error?.message || String(error))}
        <br><br><button class="secondary" id="renderRetry">Reload</button></div></main>`;
      this.shadowRoot.getElementById("renderRetry")?.addEventListener("click", () => {
        this._physical = null;
        this._physicalFor = null;
        this._load();
      });
    }
  }

  _renderUnsafe() {
    const settingsFocus = this.shadowRoot.activeElement?.dataset?.remoteSetting;
    // Re-rendering rebuilds every <details>; remember which ones the user had opened so
    // switching between a remote and a scene does not collapse them and shift the page.
    const openPanels = new Set(Array.from(
      this.shadowRoot.querySelectorAll("details.device-table[open]") || [],
    ).map((item) => item.className));
    const entry = this._entry();
    const remote = this._remote();
    const page = this._page();
    const button = this._button();
    const entries = this._entries();
    const screenKey = `${this._entryId}:${page?.index ?? 0}:${page?.index ? this._remoteId : "home"}`;
    const previousScreen = this.shadowRoot.querySelector(".scr-scroll");
    const previousScroll = previousScreen?.dataset.screenKey === screenKey
      ? previousScreen.scrollTop : 0;
    const lights = Object.values(this._hass?.states || {})
      .filter((state) => state.entity_id.startsWith("light."))
      .sort((a, b) => (a.attributes.friendly_name || a.entity_id).localeCompare(b.attributes.friendly_name || b.entity_id));
    const boundLight = remote?.binding?.entity_id || "";
    const battery = entry?.battery;
    const charge = battery != null && String(battery).trim() ? Number(battery) : NaN;

    this.shadowRoot.innerHTML = `
      <style>${this._styles()}</style>
      <main>
        <header>
          <div>
            <div class="eyebrow">SWITCHBOT UNIVERSAL REMOTE</div>
            <h1>Remote Studio</h1>
            <p>Design, map and test every physical button from one place.</p>
          </div>
          <div class="header-actions">
            ${Number.isFinite(charge) ? `<div class="battery" title="Battery level">
              <span class="battery-icon" aria-hidden="true">
                <span class="battery-fill" style="width:${Math.max(0, Math.min(100, charge))}%"></span>
              </span><span>${escapeHtml(battery)}%</span>
            </div>` : ""}
            <div class="live"><i></i> Live</div>
            ${entry ? `<button class="secondary" id="remoteSettings" ${this._physicalBusy || this._saving || this._scenePanel?.busy ? "disabled" : ""}>Remote settings</button>` : ""}
            <button class="secondary" id="refresh" ${this._scenePanel?.busy ? "disabled" : ""} title="Re-read the remote and pick up anything created in the SwitchBot app">${this._physicalBusy || this._scenePanel?.busy === "read" ? "Refreshing…" : "Refresh"}</button>
          </div>
        </header>
        <div id="studioFeedback">${this._renderStudioFeedback()}</div>
        ${this._loading ? `<div class="loading"><span></span>Loading remotes…</div>` : ""}
        ${!this._loading && !entries.length ? `<div class="empty"><b>No configured Universal Remote found.</b><br>Set up the integration first.</div>` : ""}
        ${entries.length ? `
          <section class="selectors">
            <label>Universal Remote
              <select id="entrySelect" ${this._scenePanel?.busy ? "disabled" : ""}>${entries.map((item) => `<option value="${escapeHtml(item.entry_id)}" ${item.entry_id === this._entryId ? "selected" : ""}>${escapeHtml(item.title)} · ${escapeHtml(item.address)}</option>`).join("")}</select>
            </label>
            <label>Remote<select id="remoteSelect">${(entry?.remotes || []).map((item) => `<option value="${escapeHtml(item.remote_id)}" ${item.remote_id === this._remoteId ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.device_type)}</option>`).join("")}${this._scenePanel?.draft?.index == null && this._scenePanel ? '<option value="scene:new" selected>New scene</option>' : ""}</select></label>
            ${remote?.kind === "scene" ? "" : `<div class="identity"><span>Stable ID</span><code>${escapeHtml(remote?.remote_id || "—")}</code><small>Slot ${escapeHtml(remote?.remote_slot ?? "unknown")}</small></div>`}
          </section>
          <div class="toolbar">
            ${this._action("addRemote", "＋", "Add a remote", "Install a new remote on the Universal Remote", "accent")}
            ${remote?.layout_editable && remote.kind !== "scene" && !remote.matter ? this._action("recreateRemote", "↻", "Write again", "Remove this remote from the device and write it back, unchanged") : ""}
            ${remote?.can_move ? this._action("moveRemote", "⇄", "Move to another bridge", "Bind this remote to a different Bluetooth address") : ""}
            ${remote ? this._action("deleteRemote", "🗑", "Delete", `Remove "${remote.name}" from the Universal Remote for good`, "danger") : ""}
          </div>
          ${this._renderRemoteCapacity()}
          ${this._renderAddRemote()}
          ${entry?.scene_error ? this._feedback(entry.scene_error, "warning", "Scene remotes") : ""}
          ${this._renderCloud()}
          ${this._renderDeviceTable()}
          ${this._renderDiagnostics()}
          ${this._scenePanel ? this._renderScenes() : `
          ${remote?.reachability ? `<p class="reachability ${escapeHtml(remote.reachability.level)}">${escapeHtml(remote.reachability.text)}</p>` : ""}
          ${this._renderApplyBar()}
          ${this._iconPickerFor ? "" : this._renderNativeProfileWarnings()}
          ${remote ? `
            ${remote.matter ? "" : `<section class="quick-bind" ${this._saving ? "inert" : ""}>
              <div><b>Quick bind</b><span>Apply a complete light preset; individual buttons can override it.</span></div>
              <select id="lightSelect"><option value="">Choose a light…</option>${lights.map((state) => `<option value="${escapeHtml(state.entity_id)}" ${state.entity_id === (this._presetDraftsByRemote.get(this._draftScope()) || boundLight) ? "selected" : ""}>${escapeHtml(state.attributes.friendly_name || state.entity_id)}</option>`).join("")}</select>
            </section>`}
            <nav class="pages" ${this._saving ? "inert" : ""}>${this._pages().map((item) => `<button data-page="${item.index}" class="${item.index === page?.index ? "selected" : ""}">${escapeHtml(item.name)}${item.draft_only ? " •" : ""}</button>`).join("")}</nav>
            <div class="workspace">
              <section class="remote-stage" ${this._saving ? "inert" : ""}>
                <div class="device-wrap">${this._renderFace(page)}</div>
                <div class="legend"><span><i class="preset"></i>Quick bind</span><span><i class="custom"></i>Custom</span><span><i class="disabled"></i>Disabled</span>${this._physical ? '<span><i class="unsaved"></i>Unsaved change</span>' : ""}</div>
              </section>
              <aside class="editor appearance-editor">
                <div ${this._saving ? "inert" : ""}>${!remote.layout_editable
                  ? '<div class="empty small">This IR remote is installed. Refresh can load its buttons if the profile is saved in your SwitchBot account.</div>'
                  : this._iconPickerFor === remote.remote_id
                  ? this._renderAppearance(remote)
                  : page?.index && this._physical ? this._renderPageEditor(page, button, remote)
                  : (button ? this._editor(button, remote)
                    : `<div class="empty small">Choose a button, or use the pencil on a remote to edit its appearance.</div>`)}</div>
                <footer class="studio-save">
                  <span role="status" id="saveStatus">${escapeHtml(this._saveStatus() || this._saveLabel())}</span>
                  ${this._renderSaveButton()}
                </footer>
              </aside>
            </div>
          ` : `<div class="empty"><b>No locally managed remotes.</b><br>Press Refresh to pick up remotes created in the SwitchBot app, or add one in the integration settings.</div>`}
          `}
        ` : ""}
      </main>${this._renderDeviceSettings()}`;
    const screen = this.shadowRoot.querySelector(".scr-scroll");
    if (screen) screen.scrollTop = previousScroll;
    // With many remotes the selection can sit outside the display's window; bring it in, but only
    // when the selection itself changed so the user's own scrolling is never undone.
    const shownKey = `${this._entryId}:${page?.index ?? 0}:${this._scenePanel?.draft?.index ?? this._remoteId}`;
    if (screen && this._shownSelection !== shownKey) {
      this._shownSelection = shownKey;
      const row = screen.querySelector(".scr-row.on");
      if (row) {
        const top = row.offsetTop - screen.offsetTop;
        if (top < screen.scrollTop + 8) screen.scrollTop = Math.max(0, top - 8);
        else if (top + row.offsetHeight > screen.scrollTop + screen.clientHeight - 14) {
          screen.scrollTop = top + row.offsetHeight - screen.clientHeight + 14;
        }
      }
    }
    Array.from(this.shadowRoot.querySelectorAll("details.device-table") || []).forEach((item) => {
      if (openPanels.has(item.className)) item.open = true;
    });
    this._wireEvents();
    this._wireScenes();
    this._wireDeviceSettings();
    if (settingsFocus) this.shadowRoot.querySelector(`[data-remote-setting="${settingsFocus}"]`)?.focus();
    this._wireAddRemote();
    if (this._scenePanel) {
      this._mountActionSelector();
      if (this._add) { this._ensureCatalog(); this._ensureSources(); }
      return;
    }
    this._wireDiagnostics();
    this._wireCloud();
    this._mountActionSelector();
    this._ensureLayout();
    this._ensureCatalog();
    this._ensureCloud();
    // The diagnostics table reports each controller's capacity, which comes from here.
    if (!this._sourcesError) this._ensureSources();
  }

  async _openDeviceSettings() {
    if (!this._entryId || this._physicalBusy || this._saving || this._scenePanel?.busy) return;
    const state = { entryId: this._entryId, busy: "read", values: null, draft: null, error: "", status: "" };
    this._deviceSettings = state;
    this._render();
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/device_settings`, entry_id: state.entryId });
      state.values = result.settings;
      state.draft = structuredClone(result.settings);
    } catch (error) { state.error = error?.message || String(error); }
    finally {
      state.busy = "";
      if (this._deviceSettings === state) this._render();
    }
  }

  _deviceSettingsChanges() {
    const state = this._deviceSettings;
    if (!state?.values || !state.draft) return {};
    return Object.fromEntries(Object.entries(state.draft).filter(
      ([field, value]) => field !== "japan_model" && value !== state.values[field]));
  }

  _renderDeviceSettings() {
    const state = this._deviceSettings;
    if (!state) return "";
    const values = state.draft;
    const toggle = (field, label, hint = "") => `<label class="remote-setting-toggle"><span>${label}${hint ? `<small>${hint}</small>` : ""}</span>
      <input type="checkbox" data-remote-setting="${field}" ${values[field] ? "checked" : ""}></label>`;
    const brightness = (field, label) => `<label class="remote-setting-range"><span>${label}<output data-settings-value="${field}">${values[field]}%</output></span>
      <input type="range" data-remote-setting="${field}" min="0" max="100" step="1" value="${values[field]}" ${values.auto_brightness ? "disabled" : ""}></label>`;
    const select = (field, label, choices) => {
      const current = String(values[field]);
      if (!choices.some(([value]) => value === current)) choices.push([current, `Current setting (${current})`]);
      return `<label>${label}<select data-remote-setting="${field}">${choices.map(([value, caption]) =>
        `<option value="${escapeHtml(value)}" ${value === current ? "selected" : ""}>${escapeHtml(caption)}</option>`).join("")}</select></label>`;
    };
    return `<dialog id="deviceSettingsDialog" class="device-settings-dialog" aria-labelledby="deviceSettingsTitle">
      <div class="editor-head"><div><h2 id="deviceSettingsTitle">Remote settings</h2><p class="small">Applies to this Universal Remote and all its device remotes and scenes.</p></div>
        <button type="button" class="secondary compact" id="closeDeviceSettings" ${state.busy === "save" ? "disabled" : ""} aria-label="Close remote settings">Close</button></div>
      ${state.busy === "read" ? '<p role="status">Reading settings from the remote…</p>' : ""}
      ${values ? `<form id="deviceSettingsForm"><fieldset ${state.busy ? "disabled" : ""}>
        ${toggle("touch_wheel", "Touch wheel scrolling", "Scroll through device and menu lists using the touch wheel.")}
        ${toggle("lift_to_wake", "Wake when picked up")}
        ${toggle("key_sounds", "Button sounds")}
        ${toggle("auto_brightness", "Automatic brightness", "Adjust screen and button brightness to the ambient light.")}
        ${brightness("screen_brightness", "Screen brightness")}
        ${brightness("key_brightness", "Button backlight brightness")}
        <div class="remote-setting-selects">
        ${select("screen_timeout", "Turn off the screen after", [["15", "15 seconds"], ["30", "30 seconds"], ["60", "1 minute"], ["120", "2 minutes"]])}
        ${values.japan_model ? "" : select("temperature_unit", "Temperature unit", [["0", "°C"], ["1", "°F"]])}
        ${select("language", "Screen language", [["0", "简体中文"], ["1", "English"], ["2", "日本語"]])}
        </div><p class="small">Changing the language may restart the remote.</p>
        </fieldset>${this._feedback(state.error || state.status, state.error ? "error" : "success", "Remote settings")}
        <footer class="studio-save"><span></span>
          <button type="submit" class="primary compact" id="saveDeviceSettings" ${state.busy || !Object.keys(this._deviceSettingsChanges()).length ? "disabled" : ""}>${state.busy === "save" ? "Saving…" : "Save"}</button></footer></form>` : ""}
      ${!values ? this._feedback(state.error, "error", "Remote settings") : ""}
      ${!state.busy && (!values || state.error) ? '<button class="secondary" id="retryDeviceSettings">Read settings again</button>' : ""}
    </dialog>`;
  }

  _wireDeviceSettings() {
    const root = this.shadowRoot;
    root.getElementById("remoteSettings")?.addEventListener("click", () => this._openDeviceSettings());
    const dialog = root.getElementById("deviceSettingsDialog");
    if (!dialog) return;
    dialog.showModal?.();
    const close = () => {
      if (this._deviceSettings?.busy === "save") return;
      this._deviceSettings = null;
      this._render();
      root.getElementById("remoteSettings")?.focus();
    };
    root.getElementById("closeDeviceSettings")?.addEventListener("click", close);
    dialog.addEventListener("cancel", (event) => { event.preventDefault(); close(); });
    root.getElementById("retryDeviceSettings")?.addEventListener("click", () => this._openDeviceSettings());
    root.querySelectorAll("[data-remote-setting]").forEach((input) => input.addEventListener("input", () => {
      const state = this._deviceSettings;
      const field = input.dataset.remoteSetting;
      state.draft[field] = input.type === "checkbox" ? input.checked : Number(input.value);
      state.status = "";
      const status = root.querySelector("#deviceSettingsForm .studio-feedback.success");
      if (status) status.remove();
      const output = root.querySelector(`[data-settings-value="${field}"]`);
      if (output) output.textContent = `${input.value}%`;
      if (field === "auto_brightness") {
        for (const name of ["screen_brightness", "key_brightness"]) {
          root.querySelector(`[data-remote-setting="${name}"]`).disabled = input.checked;
          if (input.checked) {
            state.draft[name] = state.values[name];
            root.querySelector(`[data-remote-setting="${name}"]`).value = state.values[name];
            root.querySelector(`[data-settings-value="${name}"]`).textContent = `${state.values[name]}%`;
          }
        }
      }
      root.getElementById("saveDeviceSettings").disabled = !Object.keys(this._deviceSettingsChanges()).length;
    }));
    root.getElementById("deviceSettingsForm")?.addEventListener("submit", (event) => {
      event.preventDefault();
      this._saveDeviceSettings();
    });
  }

  async _saveDeviceSettings() {
    const state = this._deviceSettings;
    if (!state || state.busy || state.entryId !== this._entryId) return;
    const changes = this._deviceSettingsChanges();
    if (!Object.keys(changes).length) return;
    state.busy = "save";
    state.error = "";
    state.status = "";
    this._render();
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/device_settings`, entry_id: state.entryId, changes });
      state.values = result.settings;
      state.draft = structuredClone(result.settings);
      state.status = "Settings saved and verified.";
    } catch (error) { state.error = error?.message || String(error); }
    finally {
      state.busy = "";
      if (this._deviceSettings === state) this._render();
    }
  }

  async _openPhysical() {
    clearTimeout(this._activeTimer);
    const scope = this._draftScope();
    const request = Symbol();
    this._physicalRequest = request;
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/get`,
        entry_id: this._entryId, remote_id: this._remoteId });
      if (request !== this._physicalRequest || scope !== this._draftScope()) return;
      this._physical = result.layout;
      this._physicalSources = result.ir_sources;
      this._physicalFunctions = result.functions || [];
      this._nativeProfiles = result.native_profiles || [];
      this._nativeMenuGlyphs = result.native_menu_glyphs || [];
      this._physicalBaseline = structuredClone(result.layout);
      this._resetPhysicalOrigins(result.layout);
      const draft = this._layoutDraftsByRemote.get(this._draftScope());
      if (draft) {
        this._physical = draft.layout;
        this._physicalBaseline = draft.baseline;
        this._physicalOrigins = draft.origins;
      }
      this._normalizeSelection();
      this._physicalStatus = draft ? "" : result.status || "";
    } catch (error) {
      if (request !== this._physicalRequest || scope !== this._draftScope()) return;
      // No editable layout for this remote: the Home Assistant mapping still works.
      this._physical = null;
      this._physicalBaseline = null;
    }
    // The remote's own table is NOT read here. Reading it talks to the WoRWS, which only
    // answers on the controller it is bound to — the bridge's — so the add-on has to stop
    // serving presses for several seconds while it happens. Doing that every time the panel
    // opened a remote made the bridge go deaf for no reason anyone asked for. It is fetched
    // on request instead.
    this._render();
  }

  _renderCloud() {
    const cloud = this._cloud;
    if (!cloud) return "";
    if (!cloud.connected) {
      return `<details class="device-table cloud"><summary>SwitchBot account</summary>
        <p class="small">Not connected. Sign in from the integration's settings — it needs your
        password, which belongs in Home Assistant's own configuration dialog, not here. Once
        signed in, the catalog and your saved remotes become available in Add remote.</p>
      </details>`;
    }
    return `<details class="device-table cloud">
      <summary>SwitchBot account${cloud.username ? ` · ${escapeHtml(cloud.username)}` : ""}</summary>
      <p class="small">${cloud.cached_remotes} saved remote${cloud.cached_remotes === 1 ? "" : "s"}
        cached${cloud.key_id ? `, communication key ${escapeHtml(cloud.key_id)}` : ""}.</p>
      <div class="key-actions">
        <button class="secondary compact" id="cloudRefresh" title="Fetch the remote list from your SwitchBot account again">Re-read my remotes</button>
        <button class="secondary compact" id="cloudRefreshKey" title="The remote rotates this key; fetch the current one from the account">Fetch a fresh key</button>
      </div>
      <p class="small">Fetch the key when the remote starts answering with undecodable
        responses: it rotates on its own, and the account holds the current one.</p>
      ${cloud.busy ? `<p class="small">Talking to the account…</p>` : ""}
      ${this._feedback(cloud.error, "error", "SwitchBot account")}
      ${!cloud.error ? this._feedback(cloud.note, "success", "SwitchBot account") : ""}
    </details>`;
  }

  async _ensureCloud() {
    if (this._cloud || this._cloudLoading || !this._entryId) return;
    this._cloudLoading = true;
    try {
      this._cloud = await this._hass.callWS({
        type: `${DOMAIN}/studio/cloud/status`, entry_id: this._entryId });
    } catch (error) { this._cloud = { connected: false }; }
    this._cloudLoading = false;
    this._render();
  }

  _wireCloud() {
    const root = this.shadowRoot;
    const run = async (type, done) => {
      this._cloud = { ...this._cloud, busy: true, error: "", note: "" };
      this._render();
      try {
        this._cloud = { ...this._cloud, busy: false, note: done(
          await this._hass.callWS({ type, entry_id: this._entryId })) };
      } catch (error) {
        this._cloud = { ...this._cloud, busy: false, error: error?.message || String(error) };
      }
      this._render();
    };

    root.getElementById("cloudRefresh")?.addEventListener("click", () => run(
      `${DOMAIN}/studio/cloud/refresh`,
      (result) => {
        // The Add remote dialog reads this list, so make it fetch the new one.
        this._sources = null;
        this._cloud.cached_remotes = result.remotes;
        return `${result.remotes} remote${result.remotes === 1 ? "" : "s"} read from the account.`;
      }));

    root.getElementById("cloudRefreshKey")?.addEventListener("click", () => run(
      `${DOMAIN}/studio/cloud/refresh_key`,
      (result) => {
        this._cloud.key_id = result.key_id;
        return result.changed
          ? `New key ${result.key_id} stored; the integration is reloading.`
          : `The stored key ${result.key_id} is already the current one.`;
      }));
  }

  _renderDiagnostics() {
    const diag = this._diagnostics;
    return `<details class="device-table diagnostics">
      <summary>Diagnostics</summary>
      <div class="key-actions">
        <button class="secondary compact" data-diagnostic="queries" title="Read every 0F63 query the remote answers; changes nothing">Read the remote's state</button>
        <button class="secondary compact" data-diagnostic="bridge" title="Look for each bridge address on the air">Check the bridges</button>
        <button class="secondary compact" data-diagnostic="bindings" title="Which remote each saved action belongs to; reads nothing from the device">Why did that action run?</button>
      </div>
      ${diag?.busy ? `<p class="small">Running…</p>` : ""}
      ${this._feedback(diag?.error, "error", "Diagnostics")}
      ${diag?.rows ? `<table><thead><tr><th>Query</th><th>Answer</th></tr></thead><tbody>${
        diag.rows.map((row) => `<tr><td><code>${escapeHtml(row.query)}</code></td>
          <td><code>${escapeHtml(row.value)}</code></td></tr>`).join("")
      }</tbody></table>` : ""}
      ${(this._sources?.native_options?.controllers || []).length ? `
        <table><thead><tr><th>Controller</th><th>Tiles</th><th>Advertising now</th></tr></thead>
        <tbody>${this._sources.native_options.controllers.map((item) => `<tr>
          <td>${escapeHtml(item.adapter)}<br><code>${escapeHtml(item.address)}</code></td>
          <td>${item.used} of ${item.capacity}${
            item.extended_advertising ? "" : "<br><span class=\"small\">single-address mode</span>"}</td>
          <td>${(item.serving || []).map((a) => `<code>${escapeHtml(a)}</code>`).join("<br>")
            || "<span class=\"small\">not reported</span>"}</td></tr>`).join("")}
        </tbody></table>` : ""}
      ${diag?.bridges ? `<table><thead><tr><th>Bridge</th><th>Address</th><th>Advertising</th></tr></thead>
        <tbody>${diag.bridges.map((row) => `<tr><td>${escapeHtml(row.name)}</td>
          <td><code>${escapeHtml(row.address)}</code></td>
          <td class="${row.found ? "" : "warning"}">${row.found ? "yes" : "not seen"}</td></tr>`).join("")}
        </tbody></table>` : ""}
      ${diag?.detail ? `<p class="small">${escapeHtml(diag.detail)}</p>` : ""}
      ${diag?.problems?.length ? `<div class="explanation danger"><b>Found a reason actions
        can run for the wrong remote.</b>${diag.problems.map(
          (text) => `<span>${escapeHtml(text)}</span>`).join("")}</div>` : ""}
      ${diag?.remotes ? `<table><thead><tr><th>Remote</th><th>Matched on</th><th>Bound to</th>
        </tr></thead><tbody>${diag.remotes.map((item) => {
          const own = diag.bindings.filter((b) => b.remote_id === item.identity);
          return `<tr><td>${escapeHtml(item.name)}<br><span class="small">${
            escapeHtml(item.device_type)}</span></td>
          <td><code>${escapeHtml(item.identity)}</code>${item.has_remote_id ? ""
            : `<br><span class="small warning">no remote_id of its own, so its address is
               used</span>`}</td>
          <td>${own.length ? own.map((b) => `${escapeHtml(b.entity_id || "custom actions")}${
            b.buttons.length ? ` <span class="small">(${b.buttons.length} button${
              b.buttons.length === 1 ? "" : "s"})</span>` : ""}`).join("<br>")
            : `<span class="small">nothing</span>`}</td></tr>`;
        }).join("")}</tbody></table>
        ${diag.bindings.filter((b) => b.orphan).length ? `
          <p class="small warning">${diag.bindings.filter((b) => b.orphan).length} saved action
            set(s) belong to no remote listed here. A leftover like this answers for whichever
            remote shares its identity — which is one remote's button driving another's light.</p>
          <ul class="small">${diag.bindings.filter((b) => b.orphan).map((b) => `<li>
            <code>${escapeHtml(b.remote_id || "(no id)")}</code>
            ${escapeHtml(b.remote_name || "")} ${escapeHtml(b.entity_id || "custom actions")}
            </li>`).join("")}</ul>
          <button class="secondary compact destructive" id="cleanupBindings"
            title="Delete these; nothing that still has a remote is touched">Remove them</button>`
          : ""}
        ${!diag.problems.length
          ? `<p class="small">Each remote is matched on its own identity; nothing here explains
             one remote driving another's target.</p>` : ""}` : ""}
    </details>`;
  }

  _wireDiagnostics() {
    this.shadowRoot.querySelectorAll("[data-diagnostic]").forEach((button) => {
      button.addEventListener("click", async () => {
        const what = button.dataset.diagnostic;
        this._diagnostics = { busy: true };
        this._render();
        try {
          this._diagnostics = { ...(await this._hass.callWS({
            type: `${DOMAIN}/studio/diagnostics`, entry_id: this._entryId, what })), busy: false };
        } catch (error) {
          this._diagnostics = { busy: false, error: error?.message || String(error) };
        }
        this._render();
      });
    });
  }

  _renderRemoteCapacity() {
    const sources = this._sources;
    const counters = [["ir", "IR"], ["native", "Bridge"], ["hid", "HID"]];
    const entry = this._entry();
    const sceneTotal = entry?.scene_limit ?? 10;
    const sceneAvailable = entry && !entry.scene_error
      ? Math.max(0, sceneTotal - entry.remotes.filter(remote => remote.kind === "scene").length) : "—";
    // The firmware draws one Matter text remote per Universal Remote.
    const textTotal = 1;
    const textUsed = entry?.remotes?.some(remote => remote.matter) || sources?.matter?.installed;
    const textAvailable = entry ? (textUsed ? 0 : textTotal) : "—";
    const checking = this._sourcesRequest?.refreshCapacity;
    const unknown = counters.some(([kind]) => sources?.remote_capacity?.[kind]?.available == null);
    return `<div class="remote-capacity" role="status">
      ${counters.map(([kind, label]) => {
        const { available, total } = sources?.remote_capacity?.[kind] || {};
        return `<span>${label} remotes available <b>${available ?? "—"}/${total ?? "—"}</b></span>`;
      }).join("")}
      <span>Scenes available <b>${sceneAvailable}/${sceneTotal}</b></span>
      <span>Text remotes available <b>${textAvailable}/${textTotal}</b></span>
      ${sources?.capacity_read_failed ? '<span>Could not check availability.</span>' : ""}
      ${unknown ? `<button id="checkRemoteCapacity" class="secondary compact" ${checking ? "disabled" : ""}>${
        checking ? "Checking…" : "Check availability"}</button>` : ""}
    </div>`;
  }

  _installCapacityError(add, sources = this._sources) {
    if (add.kind === "scene") {
      const entry = this._entry();
      const used = (entry?.remotes || []).filter((item) => item.kind === "scene").length;
      return used >= (entry?.scene_limit || 10) ? "The remote already has ten scenes." : "";
    }
    const ir = add.kind === "catalog" || add.kind === "cloud";
    const kind = ir ? "ir" : add.kind;
    if (sources?.remote_capacity?.[kind]?.available !== 0) return "";
    if (ir) return "No more IR remotes can be added. Delete one first.";
    if (kind === "native") return "No more Bridge remotes can be added.";
    return "No more HID remotes can be added.";
  }

  async _readDeviceTable() {
    this._deviceTable = { loading: true };
    this._render();
    try {
      const table = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/table`,
        entry_id: this._entryId });
      // `order` is the order the list is being arranged into; it starts as the remote's own.
      this._deviceTable = { ...table, open: true, order: (table.rows || []).map((row) => row.slot) };
      this._sources = null;
    } catch (error) { this._deviceTable = { error: error?.message || String(error) }; }
    this._render();
  }

  _orderChanged(table = this._deviceTable) {
    const rows = table?.rows || [];
    return Boolean(table?.order && rows.some((row, index) => table.order[index] !== row.slot));
  }

  // New order after `slot` is dropped next to `targetSlot` (after it when `placeAfter`).
  _reorderSlots(order, slot, targetSlot, placeAfter) {
    if (slot === targetSlot || !order.includes(slot) || !order.includes(targetSlot)) return order;
    const rest = order.filter((item) => item !== slot);
    rest.splice(rest.indexOf(targetSlot) + (placeAfter ? 1 : 0), 0, slot);
    return rest;
  }

  // Drag a row by its handle. Pointer events, so it works with a mouse and with touch. The rows are
  // moved in the DOM while dragging (re-rendering would drop the pointer) and the list is drawn
  // again once the handle is released.
  _startRowDrag(event, slot) {
    const table = this._deviceTable;
    const handle = event.currentTarget;
    const body = handle.closest("tbody");
    const row = handle.closest("tr");
    if (!table?.order || this._physicalBusy || !body || !row) return;
    event.preventDefault();
    handle.setPointerCapture?.(event.pointerId);
    row.classList.add("dragging");
    const move = (moveEvent) => {
      const under = this.shadowRoot.elementFromPoint(moveEvent.clientX, moveEvent.clientY)
        ?.closest?.("tr[data-row-slot]");
      if (!under || under === row || under.parentElement !== body) return;
      const box = under.getBoundingClientRect();
      const after = moveEvent.clientY > box.top + box.height / 2;
      body.insertBefore(row, after ? under.nextSibling : under);
      table.order = this._reorderSlots(table.order, slot, Number(under.dataset.rowSlot), after);
    };
    const finish = () => {
      handle.removeEventListener("pointermove", move);
      handle.removeEventListener("pointerup", finish);
      handle.removeEventListener("pointercancel", finish);
      row.classList.remove("dragging");
      this._render();
    };
    handle.addEventListener("pointermove", move);
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  }

  _moveTableRow(slot, direction) {
    const table = this._deviceTable;
    if (!table?.order || this._physicalBusy) return;
    const index = table.order.indexOf(slot);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= table.order.length) return;
    [table.order[index], table.order[target]] = [table.order[target], table.order[index]];
    this._render();
  }

  async _applyTableOrder() {
    const table = this._deviceTable;
    if (!this._orderChanged(table) || this._physicalBusy) return;
    if (!confirm("Change the order of the tiles in the Universal Remote's list? The remote applies it "
      + "as a whole; the tiles themselves are not touched.")) return;
    this._physicalBusy = true;
    this._render();
    try {
      await this._hass.callWS({ type: `${DOMAIN}/studio/physical/reorder`, entry_id: this._entryId,
        order: table.order,
        expected: table.rows.map((row) => ({ slot: row.slot, device_type: parseInt(row.device_type, 16),
          control_type: row.control_type, device_id: row.device_id })) });
      this._notify("The order of the tiles was changed on the remote", "success");
    } catch (error) {
      this._notify(error?.message || String(error), "error");
    } finally {
      this._physicalBusy = false;
      this._sources = null;
      await this._load();
      await this._readDeviceTable();
    }
  }

  async _deleteTableRow(data) {
    const slot = Number(data.deleteRow);
    const row = (this._deviceTable?.rows || []).find((item) => item.slot === slot);
    if (!row || this._physicalBusy) return;
    // The remote's own row, named by slot, type and target, cannot be brought back from here.
    if (!confirm(`Delete slot ${slot} (${row.kind}, type ${row.device_type}, target ${row.target_mac}) `
      + "from the Universal Remote? This cannot be undone and the slots after it move up.")) return;
    this._physicalBusy = true;
    this._render();
    try {
      await this._hass.callWS({ type: `${DOMAIN}/studio/physical/delete_row`, entry_id: this._entryId,
        slot, device_type: parseInt(row.device_type, 16), control_type: row.control_type,
        device_id: row.device_id });
      this._notify(`Slot ${slot} deleted from the remote`, "success");
    } catch (error) {
      this._notify(error?.message || String(error), "error");
    } finally {
      this._physicalBusy = false;
      this._sources = null;
      await this._load();
      await this._readDeviceTable();
    }
  }

  _renderDeviceTable() {
    const table = this._deviceTable;
    if (!table) {
      return `<details class="device-table"><summary>Installed on the remote</summary>
        <p class="small">Reading this asks the Universal Remote itself, and it only answers on
          the controller the bridge owns — so the bridge stops serving presses for a few
          seconds while it happens. That is why it is not read on its own.</p>
        <button class="secondary compact" id="readDeviceTable">Read the device table</button>
        </details>`;
    }
    if (table.loading) {
      return `<details class="device-table" open><summary>Installed on the remote</summary>
        <div class="loading"><span></span>Asking the remote…</div></details>`;
    }
    if (table.error) {
      return `<details class="device-table" open><summary>Installed on the remote</summary>
        ${this._feedback(table.error, "error", "Device table")}</details>`;
    }
    const bySlot = new Map((table.rows || []).map((row) => [row.slot, row]));
    const order = (table.order || (table.rows || []).map((row) => row.slot)).filter((slot) => bySlot.has(slot));
    const dirty = this._orderChanged(table);
    const busy = this._physicalBusy ? "disabled" : "";
    const rows = order.map((slot, position) => {
      const row = bySlot.get(slot);
      return `<tr data-row-slot="${row.slot}">
        <td class="drag-handle" data-drag-handle="${row.slot}" title="Drag to move" aria-hidden="true">⠿</td>
        <td>${position + 1}</td><td>${row.slot}</td>
        <td>${escapeHtml(row.name || "")}</td><td>${escapeHtml(row.kind)}</td>
        <td>${escapeHtml(row.device_type)}</td><td>${escapeHtml(row.target_mac)}</td>
        <td class="row-actions">
          <button class="secondary compact" type="button" data-move-row="${row.slot}" data-move-dir="-1"
            ${busy || position === 0 ? "disabled" : ""} aria-label="Move up" title="Move up in the remote's list">▲</button>
          <button class="secondary compact" type="button" data-move-row="${row.slot}" data-move-dir="1"
            ${busy || position === order.length - 1 ? "disabled" : ""} aria-label="Move down" title="Move down in the remote's list">▼</button>
          <button class="secondary compact destructive" type="button" data-delete-row="${row.slot}"
            data-row-type="${escapeHtml(row.device_type)}" data-row-control="${row.control_type}"
            data-row-id="${escapeHtml(row.device_id)}" ${busy || dirty ? "disabled" : ""}
            title="Delete this row from the remote, even if Studio has no record of it">Delete</button></td>
      </tr>`;
    }).join("");
    const warnings = (table.warnings || []).map(
      (text) => this._feedback(text, "warning", "Device table")).join("");
    return `<details class="device-table" ${table.open ? "open" : ""}>
      <summary>Installed on the remote (${(table.rows || []).length}, next free slot ${table.next_free_slot ?? "none"})</summary>
      <table><thead><tr><th></th><th>List</th><th>Slot</th><th>Name</th><th>Kind</th><th>Type</th><th>Target</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table>
      ${dirty ? `<div class="key-actions">
        <button class="primary compact" id="applyOrder" ${busy}>Apply order</button>
        <button class="secondary compact" id="resetOrder" ${busy}>Reset</button>
        <span class="small">The tiles change places in the remote's own list; nothing else about them changes.</span>
      </div>` : ""}
      ${warnings}
      <p class="small">A row is identified by its slot, not by its target address. ▲ and ▼ arrange the
        remote's list and <b>Apply order</b> sends it. Delete removes the row from the remote itself, also
        when Studio has no record of it; the slots after it move up.</p>
    </details>`;
  }

  _action(id, glyph, label, hint, tone = "") {
    // One shape for every top-level action: a glyph to find it by, a short label, and the
    // consequence on hover. The tone carries the weight, so nothing is only a word.
    return `<button class="action ${tone}" id="${id}" title="${escapeHtml(hint)}">
      <span class="g">${glyph}</span><span>${escapeHtml(label)}</span></button>`;
  }

  _openScenes(addNew = false, index = null) {
    const entry = this._entry();
    if (!entry || this._scenePanel?.busy) return;
    if (addNew && entry.scene_error) { this._notify(entry.scene_error, "error"); return; }
    if (addNew && entry.remotes.filter(item => item.kind === "scene").length >= (entry.scene_limit || 10)) {
      this._notify("The remote already has ten scenes.", "warning");
      return;
    }
    if (!this._scenePanel) {
      this._rememberMapping();
      this._stashLayout();
    }
    this._scenePanels ??= new Map();
    const panel = this._scenePanels.get(this._entryId) || {
      entryId: this._entryId, busy: "", rows: [], drafts: new Map(), draft: null,
      limit: entry.scene_limit || 10, loaded: true, error: "", status: "",
    };
    const rows = (entry.remotes || []).filter(item => item.kind === "scene").map(
      ({scene_index, name, icon, color, actions}) => ({index: scene_index, name, icon, color, actions: actions || []}));
    if (panel.draft) panel.drafts.set(panel.draft.index ?? "new", structuredClone(panel.draft));
    const savedContent = row => row && [row.name, row.icon, row.color, row.actions || []];
    for (const key of panel.drafts.keys()) {
      const before = panel.rows.find(row => row.index === key);
      const after = rows.find(row => row.index === key);
      if (key !== "new" && JSON.stringify(savedContent(before)) !== JSON.stringify(savedContent(after))) {
        panel.drafts.delete(key);
        if (panel.draft?.index === key) panel.draft = null;
      }
    }
    panel.rows = rows;
    panel.limit = entry.scene_limit || 10;
    this._scenePanels.set(this._entryId, panel);
    this._scenePanel = panel;
    this._physical = null;
    this._pageIndex = 0;
    this._buttonId = null;
    this._add = null;
    clearTimeout(this._activeTimer);
    if (addNew) {
      this._remoteId = "scene:new";
      panel.appearance = true;
      this._selectSceneDraft({name: "New scene", icon: 0, color: 5, actions: []});
    } else {
      const selected = rows.find(row => row.index === index) || rows[0];
      if (selected) {
        this._remoteId = `scene:${selected.index}`;
        this._selectSceneDraft(structuredClone(selected));
      }
    }
  }

  _pickRemote(remoteId) {
    if (this._saving || this._physicalBusy || this._scenePanel?.busy || remoteId === this._remoteId) return;
    this._rememberMapping();
    this._stashLayout();
    this._notice = null;
    this._error = null;
    this._remoteId = remoteId;
    this._iconPickerFor = null;
    this._physical = null;
    this._physicalFor = null;
    this._pageIndex = 0;
    this._buttonId = null;
    if (this._remote()?.kind === "scene") {
      if (this._scenePanel) this._scenePanel.appearance = false;
      this._openScenes(false, this._remote().scene_index);
    } else {
      this._scenePanel = null;
      this._normalizeSelection();
      this._render();
    }
  }

  _selectSceneDraft(draft) {
    const panel = this._scenePanel;
    panel.drafts ??= new Map();
    if (panel.draft) panel.drafts.set(panel.draft.index ?? "new", structuredClone(panel.draft));
    if (draft) draft = panel.drafts.get(draft.index ?? "new") || draft;
    panel.draft = draft;
    this._draftActions = structuredClone(draft?.actions || []);
    this._actionJsonDraft = draft?.actionsJson;
    this._jsonValid = draft?.actionsValid ?? true;
    this._mode = "actions";
    this._render();
  }

  _sceneIcon(icon) {
    return `<img class="scene-icon" src="/switchbot_urc_static/artwork/scene-${String(icon).padStart(2, "0")}.png" alt="">`;
  }

  _sceneIconGrid(selected, attr) {
    return `<div class="scene-icon-grid">${SCENE_ICONS.map((label, icon) =>
      `<button type="button" ${attr}="${icon}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"
        aria-pressed="${selected === icon}" class="${selected === icon ? "selected" : ""}">
        ${this._sceneIcon(icon)}</button>`).join("")}</div>`;
  }

  _sceneColorGrid(selected, attr) {
    return `<div class="scene-colors">${SCENE_COLORS.map((color, index) =>
      `<button type="button" ${attr}="${index}" style="background-image:url(/switchbot_urc_static/artwork/scene-background-${index}.png)" title="${color}"
        aria-label="${color}" aria-pressed="${selected === index}" class="${selected === index ? "selected" : ""}"></button>`).join("")}</div>`;
  }

  _renderScenes() {
    const { busy, draft, error, status } = this._scenePanel;

    const sceneFace = this._renderFace({ index: 0, buttons: [] }, this._renderScreen({index: 0}));
    const appearance = draft ? `<div class="editor-head"><h2>${draft.index == null ? "New scene" : "Appearance"}</h2></div>
      <div class="form-stack">
      <label class="field">Name on the remote<input id="sceneName" maxlength="63" value="${escapeHtml(draft.name)}" autocomplete="off"></label>
      <div class="field" role="group" aria-label="Icon"><span class="field-label">Icon</span>${this._sceneIconGrid(draft.icon, "data-scene-icon")}</div>
      <div class="field" role="group" aria-label="Background"><span class="field-label">Background</span>${this._sceneColorGrid(draft.color, "data-scene-color")}</div></div>` : "";
    const actions = draft ? `<div class="editor-head"><h2>${escapeHtml(draft.name || "New scene")}</h2>
      ${draft.index != null ? '<button class="secondary compact" id="testScene">Test saved actions</button>' : ""}</div>
      <div class="action-box"><div class="action-title"><b>Home Assistant actions</b><span id="actionSummary">${this._actionSummary()}</span></div>
      <div id="visualActionEditor"></div><div id="selectOptionWarning" class="small" role="status"></div>
      <details><summary>Advanced JSON fallback</summary><textarea id="actionsJson" spellcheck="false">${escapeHtml(this._actionJsonDraft ?? JSON.stringify(this._draftActions, null, 2))}</textarea></details></div>` : "";
    return `<div class="workspace scene-workspace">
      <section class="remote-stage"><div class="device-wrap">${sceneFace}</div></section>
      <aside class="editor">
        ${busy === "read" ? '<p role="status">Reading scenes from the remote…</p>' : ""}
        ${draft ? `<nav class="mode-tabs"><button data-scene-tab="actions" class="${!this._scenePanel.appearance ? "selected" : ""}">Custom actions</button>
          <button data-scene-tab="appearance" class="${this._scenePanel.appearance ? "selected" : ""}">Appearance</button></nav>
          <div ${busy ? "inert" : ""}>${this._scenePanel.appearance ? appearance : actions}</div>
          ${this._feedback(error || status, error ? "error" : "success", draft.name || "Scene")}
          <footer class="studio-save"><span></span>
            <button class="primary compact" id="saveScene" ${busy ? "disabled" : ""}>${busy === "save" ? "Saving…" : "Save"}</button>
          </footer>
`
          : '<div class="empty small">Choose a scene on the remote, or add one.</div>'}
        ${!draft ? this._feedback(error || status, error ? "error" : "info", "Scenes") : ""}
      </aside></div>`;
  }

  _wireScenes() {
    const root = this.shadowRoot;
    const panel = this._scenePanel;
    if (!panel) return;
    root.querySelectorAll("[data-scene-tab]").forEach((button) => button.addEventListener("click", () => {
      if (panel.busy) return;
      panel.appearance = button.dataset.sceneTab === "appearance";
      this._render();
    }));
    root.querySelectorAll("[data-scene-appearance]").forEach((button) => button.addEventListener("click", () => {
      if (panel.busy) return;
      panel.appearance = true;
      this._render();
    }));
    root.getElementById("sceneName")?.addEventListener("input", (event) => {
      panel.draft.name = event.target.value;
      const selectedName = root.querySelector(".scene-workspace .scr-row.on .nm");
      if (selectedName) selectedName.textContent = event.target.value;
    });
    for (const field of ["icon", "color"]) {
      root.querySelectorAll(`[data-scene-${field}]`).forEach((button) => button.addEventListener("click", () => {
        if (panel.busy) return;
        panel.draft[field] = Number(button.getAttribute(`data-scene-${field}`));
        this._render();
      }));
    }
    root.getElementById("saveScene")?.addEventListener("click", () => this._saveScene(false));
    root.getElementById("testScene")?.addEventListener("click", async () => {
      try {
        await this._hass.callWS({type: `${DOMAIN}/studio/scenes/test`, entry_id: panel.entryId, index: panel.draft.index});
      } catch (error) { panel.error = error?.message || String(error); this._render(); }
    });
  }

  async _saveScene(remove) {
    const panel = this._scenePanel;
    if (!panel?.draft || panel.busy) return;
    if (!remove && !this._jsonValid) {
      panel.error = "Fix the actions JSON before saving.";
      this._render();
      return;
    }
    const { index, name, icon, color } = panel.draft;
    const fields = remove ? { index, delete: true } : { name, icon, color, actions: structuredClone(this._draftActions),
      ...(index == null ? {} : { index }) };
    const expected = panel.rows.map(({ index, name, icon, color }) => ({ index, name, icon, color }));
    const installedIndices = new Set(panel.rows.map((row) => row.index));
    Object.assign(panel, { busy: "save", error: "", status: "" });
    this._render();
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/scenes/save`,
        entry_id: panel.entryId, expected, ...fields });
      panel.drafts?.delete(index ?? "new");
      const saved = result.scenes.find((row) => index == null
        ? !installedIndices.has(row.index) : row.index === index);
      Object.assign(panel, { rows: result.scenes, draft: remove ? null : structuredClone(saved),
        status: remove ? "Scene deleted from the remote." : "Scene saved to the remote." });
      const entry = this._entry();
      if (entry && entry.entry_id === panel.entryId) {
        entry.remotes = [
          ...(entry.remotes || []).filter(remote => remote.kind !== "scene"),
          ...result.scenes.map(row => ({...row, kind: "scene", remote_id: `scene:${row.index}`,
            scene_index: row.index, device_type: "Scene", layout_editable: true, pages: []})),
        ];
      }
      if (remove) {
        this._scenePanel = null;
        this._remoteId = null;
        this._normalizeSelection();
        this._notify("Scene deleted from the remote.", "success");
      } else if (saved) {
        this._remoteId = `scene:${saved.index}`;
      }
    } catch (error) {
      panel.error = error?.message || String(error);
    } finally {
      panel.busy = "";
      this._render();
    }
  }

  _captionCounter(value, maxBytes, shown) {
    const bytes = new TextEncoder().encode((value || "").trim()).length;
    if (isTemplate(value)) {
      return shown ? `template · now on the remote: ${shown}` : "template · cut to fit when it is rendered";
    }
    return `${bytes}/${maxBytes} bytes`;
  }

  _renderMatterCaptionFields(captions, maxBytes, shown = []) {
    return `<div class="matter-captions">${Array.from("ABCD", (letter, index) => {
      const value = captions[index] ?? "";
      return `<label>Button ${letter}<input type="text" data-matter-caption="${index}"
        value="${escapeHtml(value)}" spellcheck="false"
        placeholder="Caption for ${letter}"><small>${escapeHtml(this._captionCounter(value, maxBytes, shown[index]))}</small></label>`;
    }).join("")}
      <p class="small">These words show on the remote's screen. Each fits ${maxBytes} bytes (Russian letters
      count double). To show a live value from Home Assistant, put it in double curly braces, like
      <code>Battery {{ states('sensor.vacuum_battery') }}%</code>.</p></div>`;
  }

  _renderMatterInterval(value, range = [0, 3600]) {
    return `<label class="matter-interval"><span>Refresh live captions at most with interval</span>
      <input type="number" data-matter-interval="1" min="${range[0]}" max="${range[1]}" step="1"
        value="${escapeHtml(String(value ?? 60))}"><span>seconds</span>
      <small>Every refresh briefly pauses the bridge, so a longer time is gentler. 0 = as often as possible.</small></label>`;
  }

  // Brands matching what is typed in the catalog search box; the text lives in the catalog state
  // so that choosing a brand or a model, which re-renders, does not wipe it.
  _catalogBrands() {
    const cat = this._catalog;
    const needle = (cat.search || "").trim().toLowerCase();
    return needle ? cat.brands.filter((name) => name.toLowerCase().includes(needle)) : cat.brands;
  }

  _renderAddRemote() {
    const add = this._add;
    if (!add) return "";
    if (add.loading || add.loadError) {
      return `<section class="add-remote">
        <div class="action-title"><b>Add a remote</b></div>
        ${add.loading
          ? '<p class="small" role="status">Loading remote options…</p>'
          : this._feedback(`Could not load remote options. ${add.loadError}`, "error", "Add a remote")}
        <div class="key-actions">
          ${add.loadError ? '<button class="primary" id="retryAddRemote">Retry</button>' : ""}
          <button class="secondary compact" id="addRemoteCancel">Cancel</button>
        </div>
      </section>`;
    }
    const sources = this._sources || {};
    const capacityError = this._installCapacityError(add, sources);
    const hidArtwork = this._hidArtworkSrc(add.deviceType);
    const cat = this._catalog;
    const kinds = [
      ["native", "Bridge remote", sources.native,
       "Sends button presses to Home Assistant through the bridge."],
      ["catalog", "IR from the catalog", sources.catalog && sources.cloud,
       "Search the bundled device database; the codes come from the SwitchBot cloud."],
      ["cloud", "IR saved in your account", (sources.cloud_remotes || []).length > 0,
       "Reinstall a remote you already made in the SwitchBot app."],
      ["hid", "HID remote", !!sources.hid,
       "Presses go out as Bluetooth keys to one paired host — a TV, a box, a computer."],
      ["scene", "Scene", true, "Run Home Assistant actions from a scene on the Universal Remote."],
      ["matter", "Text remote", !!sources.matter && !sources.matter.installed,
       sources.matter?.installed
         ? "This Universal Remote already has a text remote. Edit its captions instead."
         : "Four buttons A–D with captions you choose; presses reach Home Assistant over Bluetooth."],
    ];
    const option = (value, label, selected) =>
      `<option value="${escapeHtml(String(value))}" ${selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
    return `<section class="add-remote">
      <div class="action-title"><b>Add a remote</b><span>it is installed on the Universal Remote itself</span></div>
      <div class="mode-tabs">${kinds.map(([key, label, usable]) =>
        `<button data-add-kind="${key}" class="${add.kind === key ? "selected" : ""}" ${usable ? "" : "disabled"}>${escapeHtml(label)}</button>`).join("")}</div>
      <p class="small">${escapeHtml((kinds.find((item) => item[0] === add.kind) || [])[3] || "")}</p>
      ${add.kind === "catalog" ? `
        <label>Device type<select data-catalog="type">${
          cat.types.map((item) => option(item.value, item.label, item.value === cat.remoteType)).join("")
        }</select></label>
        <label>Brand<input type="search" data-catalog="search" autocomplete="off"
          value="${escapeHtml(cat.search || "")}"
          placeholder="Search ${cat.brands.length} brand${cat.brands.length === 1 ? "" : "s"}…"></label>
        <select data-catalog="brand" size="6">${
          this._catalogBrands().slice(0, 300).map((name) => option(name, name, name === cat.brand)).join("")
        }</select>
        ${cat.models.length ? `<label>Model<select data-catalog="model">
          <option value="">Choose a model…</option>${
            cat.models.map((item) => option(item.hxd_index, item.label, item.hxd_index === cat.hxd)).join("")
          }</select></label>` : ""}` : ""}
      ${add.kind === "native" ? `
        <div class="native-type-panel add-native-type-panel"><div class="native-type-heading"><b>Type</b>
          <span>Choose the built-in screen and button layout.</span></div>
          ${this._nativeTypeChoices(sources.native_options?.screen_profiles || [], add.nativeType || add.deviceType, "add-native-type")}
        </div>
        ${(sources.bridges || []).length ? `<details class="bridge-advanced" ${add.showBridgeOptions ? "open" : ""}>
          <summary>Bridge options</summary>
          <label>Address<select data-add-field="target_id">
            ${option("", "Automatic", !add.targetId)}
            ${sources.bridges.map((item) => option(item.target_id, item.name, item.target_id === add.targetId)).join("")}
          </select></label>
        </details>` : ""}` : ""}
      ${add.kind === "matter" ? this._renderMatterCaptionFields(
        add.captions || sources.matter?.default_captions || [], sources.matter?.max_bytes || 31) : ""}
      ${add.kind === "scene" ? `<div class="field" role="group" aria-label="Icon"><span class="field-label">Icon</span>${
        this._sceneIconGrid(add.scene?.icon ?? 0, "data-add-scene-icon")}</div>
        <div class="field" role="group" aria-label="Background"><span class="field-label">Background</span>${
        this._sceneColorGrid(add.scene?.color ?? 0, "data-add-scene-color")}</div>` : ""}
      ${add.kind === "cloud" ? `<label>Remote<select data-add-field="remote_id">${
        (sources.cloud_remotes || []).map((item) => option(item.remote_id, item.name, item.remote_id === add.remoteId)).join("")
      }</select></label>` : ""}
      ${add.kind === "hid" ? `
        <label>Kind<select data-add-field="device_type">${
          (sources.hid?.device_types || []).map((item) => option(item, item, item === add.deviceType)).join("")
        }</select></label>
        <div class="add-native-artwork"><div class="artwork-preview">${hidArtwork
          ? `<img src="${hidArtwork}" alt="Firmware artwork for ${escapeHtml(add.deviceType)}">`
          : "—"}</div><p class="small">The HID type determines the built-in screen illustration unless you choose an icon below.</p></div>
        <p class="small">After adding the remote, pair it from its settings.</p>` : ""}
      ${add.kind === "scene" ? "" : this._renderAddIconPicker(add)}
      <label>Name<input type="text" data-add-field="name" value="${escapeHtml(add.name || "")}"
        placeholder="What it is called on the remote's screen"></label>
      ${this._feedback(add.error || capacityError, add.error ? "error" : "warning", "Add a remote")}
      <div class="key-actions">
        <button class="primary" id="addRemoteConfirm" ${add.busy || capacityError ? "disabled" : ""}>${
          add.busy ? "Installing…" : "Install"}</button>
        <button class="secondary compact" id="addRemoteCancel">Cancel</button>
      </div>
    </section>`;
  }

  // Illustration choice for a remote that is about to be installed: the same firmware pictures as
  // the appearance editor. "device" is icon 0 (the type's, model's or profile's own picture).
  _renderAddIconPicker(add) {
    const picked = add.icon || "device";
    const names = ["device", ...(this._entry()?.icons || [])];
    // The picture "Type default" gives back for what is being added, where it is known.
    const irType = add.kind === "catalog"
      ? CATALOG_TO_REMOTE_IR_TYPE[Number(this._catalog?.remoteType)]
      : add.kind === "cloud"
        ? Number((this._sources?.cloud_remotes || []).find((item) => item.remote_id === add.remoteId)?.device_type)
        : NaN;
    const defaultSrc = add.kind === "native"
      ? this._nativeArtworkSrc(this._nativeProfile(add.nativeType || add.deviceType))
      : add.kind === "hid" ? this._hidArtworkSrc(add.deviceType)
        : add.kind === "matter" ? MATTER_ARTWORK
          : IR_PROFILE_ARTWORK[irType]
            ? `/switchbot_urc_static/artwork/profile-${IR_PROFILE_ARTWORK[irType]}.png` : "";
    const note = add.kind === "catalog" || add.kind === "cloud"
      ? "Type default keeps the picture of the IR model. A chosen icon replaces it."
      : add.kind === "matter"
        ? "The remote list shows the picture this icon selects."
        : "A chosen icon replaces the picture that the type selects.";
    return `<div class="field" role="group" aria-label="Illustration">
      <span class="appearance-field-label">Illustration</span>
      <p class="appearance-note">${escapeHtml(note)}</p>
      <div class="appearance-icon-grid">${names.map((name) => {
        const src = name === "device" ? defaultSrc : this._firmwareIconSrc(name);
        const label = name === "device" ? "Type default" : (APP_ICON_LABELS[name] || name);
        return `<button class="appearance-icon-choice${name === picked ? " selected" : ""}" type="button"
          data-add-icon="${escapeHtml(name)}" aria-label="${escapeHtml(label)}" aria-pressed="${name === picked}">${
          src ? `<img class="ic-art" src="${src}" alt="" aria-hidden="true">`
            : `<span class="ic-art ic-art-default" aria-hidden="true">↺</span>`}<span>${escapeHtml(label)}</span></button>`;
      }).join("")}</div></div>`;
  }

  async _ensureSources(refreshCapacity = false) {
    const entryId = this._entryId;
    if (!entryId) return null;
    if (this._sourcesRequest?.entryId === entryId) {
      if (!refreshCapacity || this._sourcesRequest.refreshCapacity) return this._sourcesRequest.promise;
      await this._sourcesRequest.promise;
      return this._entryId === entryId ? this._ensureSources(true) : null;
    }
    if (!refreshCapacity && this._sources && this._sourcesEntry === entryId) return this._sources;
    const request = { entryId, refreshCapacity };
    this._sourcesRequest = request;
    this._sourcesError = "";
    request.promise = Promise.resolve().then(async () => {
      try {
        const sources = await this._hass.callWS({
          type: `${DOMAIN}/studio/remote/sources`, entry_id: entryId,
          ...(refreshCapacity ? { refresh_capacity: true } : {}) });
        if (this._sourcesRequest !== request || this._entryId !== entryId) return null;
        this._sources = sources;
        this._sourcesEntry = entryId;
        return sources;
      } catch (error) {
        if (this._sourcesRequest === request && this._entryId === entryId) {
          this._sourcesError = error?.message || error?.code || String(error);
        }
        return null;
      } finally {
        if (this._sourcesRequest === request) {
          this._sourcesRequest = null;
          this._render();
        }
      }
    });
    return request.promise;
  }

  async _openAddRemote() {
    const entryId = this._entryId;
    const pending = { loading: true };
    this._add = pending;
    const request = this._ensureSources(true);
    this._render();
    const sources = await request;
    if (entryId !== this._entryId || this._add !== pending) return;
    if (!sources) {
      this._add = { loadError: this._sourcesError || "No response from Home Assistant." };
      this._render();
      return;
    }
    this._error = null;
    // Open on the first kind this installation can actually use.
    const kind = sources.native ? "native"
      : (sources.catalog && sources.cloud) ? "catalog"
      : (sources.cloud_remotes || []).length ? "cloud" : "hid";
    this._add = {
      kind, name: "", replace: false, busy: false, error: "",
      remoteId: (sources.cloud_remotes || [])[0]?.remote_id || "",
      deviceType: (kind === "native"
        ? sources.native_options?.default_screen_profile
        : (sources.hid?.device_types || [])[0]) || "",
      icon: "device",
      targetId: "",
    };
    this._render();
  }

  _wireAddRemote() {
    const root = this.shadowRoot;
    const add = this._add;
    if (!add) return;
    root.getElementById("retryAddRemote")?.addEventListener("click", () => this._openAddRemote());
    if (add.loading || add.loadError) {
      root.getElementById("addRemoteCancel")?.addEventListener("click", () => {
        this._add = null;
        this._render();
      });
      return;
    }

    root.querySelectorAll("[data-add-kind]").forEach((button) => {
      button.addEventListener("click", () => {
        add.kind = button.dataset.addKind;
        if (add.kind === "scene") add.scene ??= { icon: 0, color: 0 };
        add.nativeType = "";
        add.error = "";
        const kinds = this._sources || {};
        // Device types and icons differ per kind; carrying one tab's choice into another
        // would offer a value the backend rejects.
        add.deviceType = (add.kind === "native"
          ? kinds.native_options?.default_screen_profile
          : (kinds.hid?.device_types || [])[0]) || "";
        this._render();
      });
    });

    root.querySelectorAll("[data-add-icon]").forEach((button) => {
      button.addEventListener("click", () => {
        add.icon = button.dataset.addIcon;
        this._render();
      });
    });

    root.querySelectorAll("[data-add-scene-icon],[data-add-scene-color]").forEach((button) => {
      button.addEventListener("click", () => {
        add.scene = { icon: 0, color: 0, ...add.scene };
        if (button.dataset.addSceneIcon != null) add.scene.icon = Number(button.dataset.addSceneIcon);
        else add.scene.color = Number(button.dataset.addSceneColor);
        this._render();
      });
    });

    root.querySelectorAll(".add-remote [data-matter-caption]").forEach((field) => {
      field.addEventListener("input", () => {
        const base = add.captions || this._sources?.matter?.default_captions || [];
        add.captions = Array.from({ length: 4 }, (_, i) => base[i] ?? "");
        add.captions[Number(field.dataset.matterCaption)] = field.value;
      });
    });

    root.querySelectorAll("[data-add-native-type]").forEach((button) => {
      button.addEventListener("click", () => {
        const selected = (this._sources?.native_options?.screen_profiles || [])
          .find((item) => item.value === button.dataset.addNativeType);
        add.nativeType = button.dataset.addNativeType;
        add.deviceType = selected?.profile || button.dataset.addNativeType;
        this._render();
      });
    });

    root.querySelector(".bridge-advanced")?.addEventListener("toggle", (event) => {
      add.showBridgeOptions = event.target.open;
    });
    root.querySelectorAll("[data-add-field]").forEach((field) => {
      field.addEventListener("input", () => {
        const name = field.dataset.addField;
        if (name === "name") add.name = field.value;
        else if (name === "remote_id") add.remoteId = field.value;
        else if (name === "device_type") add.deviceType = field.value;
        else if (name === "icon") add.icon = field.value;
      });
      field.addEventListener("change", () => {
        const name = field.dataset.addField;
        if (name === "remote_id") add.remoteId = field.value;
        if (name === "device_type") {
          add.deviceType = field.value;
          if (add.kind === "native" || add.kind === "hid") this._render();
        }
        if (name === "icon") add.icon = field.value;
        if (name === "target_id") {
          add.targetId = field.value;
          this._render();
        }
      });
    });

    root.querySelector('.add-remote [data-catalog="type"]')?.addEventListener("change", async (event) => {
      try {
        await this._loadCatalogBrands(Number(event.target.value));
      } catch (error) { add.error = error?.message || String(error); }
      this._render();
    });

    root.querySelector('.add-remote [data-catalog="search"]')?.addEventListener("input", (event) => {
      // Filter in place: re-rendering here would steal focus mid-word.
      this._catalog.search = event.target.value;
      const list = root.querySelector('.add-remote [data-catalog="brand"]');
      if (!list) return;
      list.innerHTML = this._catalogBrands().slice(0, 300).map(
        (name) => `<option value="${escapeHtml(name)}"${name === this._catalog.brand ? " selected" : ""}>${escapeHtml(name)}</option>`).join("");
    });

    root.querySelector('.add-remote [data-catalog="brand"]')?.addEventListener("change", async (event) => {
      const cat = this._catalog;
      Object.assign(cat, { brand: event.target.value, models: [], hxd: "", buttons: [] });
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/catalog/models`,
          remote_type: cat.remoteType, brand: cat.brand });
        cat.models = result.models || [];
      } catch (error) { add.error = error?.message || String(error); }
      this._render();
    });

    root.querySelector('.add-remote [data-catalog="model"]')?.addEventListener("change", (event) => {
      const cat = this._catalog;
      Object.assign(cat, { hxd: event.target.value, buttons: [] });
      // Offer the catalog's own wording as the name until the user types one.
      if (!add.name && cat.hxd) {
        const model = cat.models.find((item) => item.hxd_index === cat.hxd);
        add.name = model ? `${cat.brand} ${model.label.split(" — ")[0]}`.trim() : cat.brand;
      }
      this._render();
    });

    root.getElementById("addRemoteCancel")?.addEventListener("click", () => {
      this._add = null;
      this._render();
    });

    root.getElementById("addRemoteConfirm")?.addEventListener("click", () => this._installRemote());
  }

  async _installScene(add, name) {
    const entry = this._entry();
    const rows = (entry.remotes || []).filter((item) => item.kind === "scene").map(
      ({ scene_index, name, icon, color }) => ({ index: scene_index, name, icon, color }));
    const result = await this._hass.callWS({ type: `${DOMAIN}/studio/scenes/save`,
      entry_id: this._entryId, expected: rows, name, icon: add.scene?.icon ?? 0,
      color: add.scene?.color ?? 0, actions: [] });
    const known = new Set(rows.map((row) => row.index));
    const saved = result.scenes.find((row) => !known.has(row.index));
    entry.remotes = [
      ...(entry.remotes || []).filter((remote) => remote.kind !== "scene"),
      ...result.scenes.map((row) => ({ ...row, kind: "scene", remote_id: `scene:${row.index}`,
        scene_index: row.index, device_type: "Scene", layout_editable: true, pages: [] })),
    ];
    this._scenePanels?.delete(this._entryId);
    this._notify("Scene installed. Add its Home Assistant actions on the right.", "success");
    if (saved) this._pickRemote(`scene:${saved.index}`);
    return result;
  }

  async _installRemote() {
    const add = this._add;
    if (this._installCapacityError(add)) return;
    const name = (add.name || "").trim();
    if (!name) { add.error = "Give the remote a name."; this._render(); return; }
    if (add.kind === "catalog" && !this._catalog.hxd) {
      add.error = "Choose a model from the catalog."; this._render(); return;
    }
    if (add.kind === "cloud" && !add.remoteId) {
      add.error = "Choose one of your saved remotes."; this._render(); return;
    }
    if (add.kind === "scene") {
      // Scenes live in the shared inventory already, so there is nothing to reload afterwards.
      add.busy = true;
      add.error = "";
      this._render();
      try {
        await this._installScene(add, name);
        this._add = null;
        this._error = null;
      } catch (error) {
        add.error = error?.message || String(error);
      } finally {
        add.busy = false;
        this._render();
      }
      return;
    }
    add.busy = true;
    add.error = "";
    this._physicalBusy = true;
    this._render();
    try {
      let result;
      if (add.kind === "native") {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/create`,
          entry_id: this._entryId, name,
          native_type: add.nativeType || add.deviceType, icon: add.icon || "device",
          ...(add.targetId ? { target_id: add.targetId } : { auto_address: true }) });
      } else if (add.kind === "matter") {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/matter/save`,
          entry_id: this._entryId, name,
          captions: add.captions || this._sources?.matter?.default_captions || [],
          icon: add.icon || "device" });
        if (result?.remote_id) {
          this._remoteId = result.remote_id;
          this._iconPickerFor = result.remote_id;
          this._pageIndex = 0;
          this._buttonId = null;
        }
      } else if (add.kind === "hid") {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/create_hid`,
          entry_id: this._entryId, name, device_type: add.deviceType,
          icon: add.icon || "device" });
        if (result?.remote_id) {
          this._remoteId = result.remote_id;
          this._iconPickerFor = result.remote_id;
          this._pageIndex = 0;
          this._buttonId = null;
        }
      } else {
        result = await this._hass.callWS({
          type: `${DOMAIN}/studio/remote/install_ir`,
          entry_id: this._entryId,
          source: add.kind,
          name,
          replace_existing: false,
          icon: add.icon || "device",
          ...(add.kind === "catalog"
            ? { hxd_index: this._catalog.hxd, remote_type: this._catalog.remoteType }
            : { remote_id: add.remoteId }),
        });
      }
      this._notify(result?.warning
        || (result?.new_bridge
          ? `Installed in slot ${result.slot} on the new bridge ${result.bridge}`
          : `Installed in slot ${result.slot}`), result?.warning ? "warning" : "success");
      this._add = null;
      this._physical = null;
      this._physicalFor = null;
      this._error = null;
    } catch (error) {
      add.error = error?.message || String(error);
    } finally {
      add.busy = false;
      this._physicalBusy = false;
      this._sources = null;
      await this._load();
    }
  }

  async _enterHidPairMode() {
    const scope = this._draftScope();
    const states = this._hidPairingByRemote;
    if (states.get(scope)?.busy) return;
    const state = {
      busy: true,
      message: "Open Bluetooth settings on your TV or player and select the SwitchBot Universal Remote.",
    };
    states.set(scope, state);
    this._render();
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/pair_hid`,
        entry_id: this._entryId, remote_id: this._remoteId });
      state.message = result.status === "paired" ? "Pairing complete."
        : result.status === "expired" ? "Pairing timed out. Start pairing mode again to retry."
        : "WoRWS did not confirm pairing. Check your TV or player's Bluetooth settings.";
    } catch (error) {
      state.message = error?.message || String(error);
    } finally {
      state.busy = false;
      if (scope === this._draftScope()) this._render();
    }
  }

  _renderApplyBar() {
    if (!this._physical) return "";
    const changes = this._physicalChanges();
    if (!changes) return "";
    return `<div class="apply-bar ${changes ? "dirty" : ""}" ${this._saving ? "inert" : ""}>
      <span>${changes} layout change${changes === 1 ? "" : "s"} to save.</span>
      <span class="spacer"></span>
      ${changes ? `<button class="secondary compact" id="physicalDiscard">Discard layout and button edits</button>` : ""}
    </div>`;
  }

  _physicalChanges() {
    if (!this._physical || !this._physicalBaseline) return 0;
    const canonical = (draft) => JSON.stringify({
      kind: draft.kind,
      template: draft.template || "",
      native_type: draft.native_type || "",
      pages: [...draft.pages].sort((a, b) => a.index - b.index).map((page) => ({
        index: page.index,
        title: page.title || "",
        link_glyph: page.link_glyph ?? null,
        link_record: page.link_record ?? null,
        buttons: [...page.buttons].sort((a, b) => a.index - b.index).map((key) => ({
          index: key.index, transport: key.transport, function: key.function ?? null,
          code_hex: key.code_hex || "", record: key.record || "", glyph: key.glyph ?? null,
          title: key.title || "",
        })),
      })),
    });
    return Number(canonical(this._physical) !== canonical(this._physicalBaseline)
      || this._identityMigrations().length > 0 || this._identityRemovals().length > 0);
  }

  _resetPhysicalOrigins(layout) {
    this._physicalOrigins = {};
    for (const page of layout?.pages || []) {
      for (const key of page.buttons || []) {
        const id = `p${page.index}_k${key.index}`;
        this._physicalOrigins[id] = id;
      }
    }
  }

  _identityMigrations() {
    const present = new Set((this._physical?.pages || []).flatMap((page) =>
      (page.buttons || []).map((key) => `p${page.index}_k${key.index}`)));
    return Object.entries(this._physicalOrigins || {})
      .filter(([current, original]) => current !== original && present.has(current))
      .map(([to, from]) => ({ from, to }));
  }

  _relocateDraftKey(oldId, newId) {
    const origin = this._physicalOrigins[oldId];
    delete this._physicalOrigins[oldId];
    if (origin) this._physicalOrigins[newId] = origin;
    const mappings = this._mappingDrafts();
    if (mappings.has(oldId)) {
      mappings.set(newId, mappings.get(oldId));
      mappings.delete(oldId);
    }
    if (this._buttonId === oldId) this._buttonId = newId;
  }

  _moveMainButton(from, to) {
    const page = this._physical?.pages?.find((item) => item.index === 0);
    const button = page?.buttons?.find((item) => item.index === from);
    if (!button || page.buttons.some((item) => item.index === to)) return;
    const oldId = `p0_k${from}`;
    const newId = `p0_k${to}`;
    button.index = to;
    this._relocateDraftKey(oldId, newId);
    this._physicalStatus = "";
    this._render();
  }

  _moveSubpage(from, to) {
    if (this._physical.pages.some((page) => page.index === to)) return;
    const page = this._physical.pages.find((item) => item.index === from);
    if (!page || !from || !to) return;
    for (const key of page.buttons) {
      const oldId = `p${from}_k${key.index}`;
      const newId = `p${to}_k${key.index}`;
      this._relocateDraftKey(oldId, newId);
    }
    page.index = to;
    this._physical.pages.sort((a, b) => a.index - b.index);
    if (this._pageIndex === from) this._pageIndex = to;
    this._physicalStatus = "";
    this._render();
  }

  _nativeProfileConflicts(profile) {
    if (!profile || this._physical?.kind !== "native") return [];
    const pages = this._physical.pages || [];
    const main = pages.find((page) => page.index === 0)?.buttons || [];
    const targetPages = profile.subpages || [];
    const supportedPageIds = new Set(targetPages.filter((page) => page.link_index != null)
      .map((page) => page.index));
    const supportedExistingPages = new Set(pages.filter((page) => page.index
      && supportedPageIds.has(page.index)).map((page) => page.index));
    const reserved = new Set([...supportedExistingPages].map((index) => index - 1));
    const usedPages = new Set(pages.filter((page) => page.index).map((page) => page.index));
    const availableMain = (profile.main_positions || []).filter((index) =>
      !main.some((key) => key.index === index) && !reserved.has(index));
    const availablePages = targetPages.filter((page) => page.link_index != null
      && !usedPages.has(page.index)
      && !main.some((key) => key.index === page.link_index));
    const conflicts = [];
    for (const page of pages) {
      if (page.index && !supportedPageIds.has(page.index)) {
        conflicts.push({ type: "page", page, targets: availablePages });
      }
    }
    for (const key of main) {
      if (!(profile.main_positions || []).includes(key.index) || reserved.has(key.index)) {
        conflicts.push({ type: "main", key, targets: availableMain });
      }
    }
    return conflicts;
  }

  _profileFunctionLabel(value) {
    return this._physicalFunctions.find((item) => item.value === value)?.label
      || `Function ${value}`;
  }

  _renderNativeProfileWarnings() {
    if (this._physical?.kind !== "native") return "";
    const profile = this._nativeProfile(this._physical.native_type || this._physical.template);
    if (!profile) return "";
    const conflicts = this._nativeProfileConflicts(profile);
    const mainKeys = profile.main_keys || [];
    const conflictRows = conflicts.map((item) => {
      if (item.type === "main") {
        const label = this._profileFunctionLabel(item.key.function);
        return `<div class="profile-conflict-row"><span><b>${escapeHtml(label)}</b><small>Main · position ${item.key.index + 1} is unavailable in this profile</small></span>
          ${item.targets.length ? `<label>Move to<select data-move-main="${item.key.index}"><option value="">Choose position…</option>${item.targets.map((index) => `<option value="${index}">${escapeHtml((mainKeys.find((slot) => slot.index === index)?.position || `Position ${index + 1}`))}</option>`).join("")}</select></label>` : `<small>No free Main position</small>`}</div>`;
      }
      return `<div class="profile-conflict-row"><span><b>Page ${"ABCD"[item.page.index - 1]}</b><small>${item.page.buttons.length} button${item.page.buttons.length === 1 ? "" : "s"} · unavailable in this profile</small></span>
        ${item.targets.length ? `<label>Move to<select data-move-page="${item.page.index}"><option value="">Choose page…</option>${item.targets.map((page) => `<option value="${page.index}">Page ${"ABCD"[page.index - 1]} · ${page.link_position}</option>`).join("")}</select></label>` : `<small>No free page link</small>`}</div>`;
    }).join("");
    const draftPageCount = this._physical.pages.filter((page) => page.index).length;
    const profilePageCount = (profile.subpages || []).filter((page) => page.link_index != null).length;
    const pageCapacityExceeded = draftPageCount > profilePageCount;
    if (!conflicts.length && !pageCapacityExceeded) return "";
    return `<section class="native-profile-warnings">
      <b>${escapeHtml(profile.label)} layout needs attention</b>
      ${pageCapacityExceeded ? `<div class="profile-capacity-warning"><b>This profile supports ${profilePageCount} submenu page${profilePageCount === 1 ? "" : "s"}; the draft has ${draftPageCount}.</b><span>Remove a page or choose a profile with more page slots.</span></div>` : ""}
      ${conflicts.length ? `<div class="profile-conflicts"><div class="profile-conflict-heading"><b>Resolve ${conflicts.length} placement conflict${conflicts.length === 1 ? "" : "s"} before writing</b><span>Button mappings move with their buttons.</span></div>${conflictRows}</div>` : ""}
    </section>`;
  }

  _wireKeyEditor(root) {
    const button = this._button();
    if (!button || !this._physical) return;
    const found = this._draftKey(button);

    // These two work on an empty position as well as a filled one, so they are wired before
    // the guard below: a position with no command is exactly where they are needed.
    // Scoped to the editor: the same attribute is on the device's own keys, and wiring both
    // here would attach a second listener to them.
    root.querySelectorAll(".key-editor [data-page-link]").forEach((element) =>
      element.addEventListener("click", () => {
        this._pageIndex = Number(element.dataset.pageLink);
        this._buttonId = null;
        this._normalizeSelection();
        this._render();
      }));

    root.getElementById("openCustomPage")?.addEventListener("click", () => {
      const index = button.button_index + 1;
      const nativeProfile = this._nativeProfile(this._physical.native_type || this._physical.template);
      if (this._physical.kind === "native" && !nativeProfile?.pages?.includes(index)) return;
      const home = this._physical.pages.find((item) => item.index === 0);
      if (!home || this._physical.pages.some((item) => item.index === index)) return;
      this._physical.pages.push({ index, buttons: [] });
      this._physical.pages.sort((a, b) => a.index - b.index);
      // The key gives up its command: the firmware will not let it both open a page and send.
      home.buttons = home.buttons.filter((item) => item.index !== button.button_index);
      const id = `p0_k${button.button_index}`;
      delete this._physicalOrigins[id];
      this._mappingDrafts().delete(id);
      this._selectButton(null, false);
      this._pageIndex = index;
      this._buttonId = null;
      this._pageEditing = true;
      this._physicalStatus = "";
      this._render();
    });

    root.getElementById("addKeyHere")?.addEventListener("click", () => {
      const target = this._physical.pages.find((item) => item.index === button.button_page);
      if (!target || target.buttons.some((item) => item.index === button.button_index)) return;
      const kindNow = this._physical.kind;
      target.buttons.push({
        index: button.button_index,
        transport: kindNow === "native" ? "native" : kindNow === "hid" ? "hid" : "ir",
        function: kindNow === "native" ? NATIVE_CUSTOM_FUNCTION : button.default_function ?? 115,
        code_hex: "",
      });
      this._selectButton(this._button());
    });

    if (!found) return;
    const { page, key } = found;

    root.querySelector('[data-key-field="transport"]')?.addEventListener("change", (event) => {
      key.transport = event.target.value;
      if (key.transport !== "ir" && this._physical.kind === "hid") delete key.glyph;
      if (key.transport === "hid") key.function ??= 0;
      this._render();
    });

    root.querySelector('[data-key-field="function"]')?.addEventListener("change", (event) => {
      key.function = Number(event.target.value);
      this._render();
    });

    root.querySelector('[data-key-field="ir_source"]')?.addEventListener("change", (event) => {
      if (event.target.value === "") return;
      key.code_hex = this._physicalSources[Number(event.target.value)].code_hex;
      this._render();
    });

    root.querySelector('[data-key-field="code_hex"]')?.addEventListener("input", (event) => {
      // Keep whatever is typed, including an odd length while it is still being pasted; the
      // backend validates before anything is written to the remote.
      key.code_hex = event.target.value.replace(/[^0-9a-fA-F]/g, "").toLowerCase();
    });

    root.querySelector('.key-editor [data-catalog="type"]')?.addEventListener("change", async (event) => {
      try {
        await this._loadCatalogBrands(Number(event.target.value));
      } catch (error) { this._catalog.error = error?.message || String(error); }
      this._render();
    });

    root.querySelector('.key-editor [data-catalog="search"]')?.addEventListener("input", (event) => {
      // Filter the brand list in place: re-rendering here would steal focus mid-word.
      this._catalog.search = event.target.value;
      const list = root.querySelector('.key-editor [data-catalog="brand"]');
      if (!list) return;
      list.innerHTML = this._catalogBrands().slice(0, 300).map(
        (name) => `<option value="${escapeHtml(name)}"${name === this._catalog.brand ? " selected" : ""}>${escapeHtml(name)}</option>`).join("");
    });

    root.querySelector('.key-editor [data-catalog="brand"]')?.addEventListener("change", async (event) => {
      const cat = this._catalog;
      Object.assign(cat, { brand: event.target.value, models: [], hxd: "", buttons: [], error: "" });
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/catalog/models`,
          remote_type: cat.remoteType, brand: cat.brand });
        cat.models = result.models || [];
      } catch (error) { cat.error = error?.message || String(error); }
      this._render();
    });

    root.querySelector('.key-editor [data-catalog="model"]')?.addEventListener("change", async (event) => {
      const cat = this._catalog;
      Object.assign(cat, { hxd: event.target.value, buttons: [], error: "" });
      if (!cat.hxd) { this._render(); return; }
      cat.busy = "Downloading this model's codes from the SwitchBot cloud…";
      this._render();
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/catalog/buttons`,
          entry_id: this._entryId, hxd_index: cat.hxd, remote_type: cat.remoteType });
        cat.buttons = result.buttons || [];
        if (!cat.buttons.length) cat.error = "This model has no usable codes.";
      } catch (error) { cat.error = error?.message || String(error); }
      cat.busy = "";
      this._render();
    });

    root.querySelector('.key-editor [data-catalog="button"]')?.addEventListener("change", (event) => {
      if (event.target.value === "") return;
      key.code_hex = this._catalog.buttons[Number(event.target.value)].code_hex;
      this._physicalStatus = "";
      this._render();
    });

    root.getElementById("removeKey")?.addEventListener("click", () => {
      if (page.index) {
        this._removeMenuRow(page, key);
        return;
      }
      page.buttons = page.buttons.filter((item) => item !== key);
      const id = `p${page.index}_k${key.index}`;
      delete this._physicalOrigins[id];
      this._mappingDrafts().delete(id);
      this._selectButton(null, false);
      this._render();
    });

    root.getElementById("moveRowUp")?.addEventListener("click", () =>
      this._movePageKey(page.index, key.index, -1));
    root.getElementById("moveRowDown")?.addEventListener("click", () =>
      this._movePageKey(page.index, key.index, 1));
  }

  _wirePhysical() {
    const root = this.shadowRoot;
    this._wireKeyEditor(root);
    root.querySelectorAll("[data-page-editor]").forEach((element) => element.addEventListener("click", () => {
      this._pageEditing = element.dataset.pageEditor === "menu";
      this._render();
    }));
    root.querySelectorAll("[data-glyph-field]").forEach((button) => button.addEventListener("click", () => {
      const { glyphField, glyphCode } = button.dataset;
      const owner = glyphField === "link_glyph"
        ? this._physical.pages.find((page) => page.index === this._page()?.index)
        : this._draftKey(this._button())?.key;
      if (!owner) return;
      if (glyphCode === "") delete owner[glyphField];
      else owner[glyphField] = Number(glyphCode);
      this._physicalStatus = "";
      const scrollTop = button.closest(".glyph-grid")?.scrollTop || 0;
      this._render();
      const next = root.querySelector(`[data-glyph-field="${glyphField}"][data-glyph-code="${glyphCode}"]`);
      if (!next) return;
      const picker = next.closest("details");
      picker.open = true;
      const grid = next.closest(".glyph-grid");
      if (grid) grid.scrollTop = scrollTop;
      (next.disabled ? picker.querySelector("summary") : next).focus({ preventScroll: true });
    }));
    root.querySelectorAll("[data-native-profile]").forEach((button) => button.addEventListener("click", () => {
      const selected = this._nativeProfiles.find((item) => item.value === button.dataset.nativeProfile);
      this._physical.native_type = button.dataset.nativeProfile;
      this._physical.template = selected?.profile || button.dataset.nativeProfile;
      this._physical.control_mode = selected?.control_mode ?? 0;
      this._physical.icon_code = selected?.icon_code ?? 1;
      this._physicalStatus = "";
      this._render();
    }));
    root.querySelectorAll("[data-move-main]").forEach((select) => {
      select.addEventListener("change", () => {
        if (!select.value) return;
        const target = Number(select.value);
        if (Number.isInteger(target)) this._moveMainButton(Number(select.dataset.moveMain), target);
      });
    });
    root.querySelectorAll("[data-move-page]").forEach((select) => {
      select.addEventListener("change", () => {
        if (!select.value) return;
        const target = Number(select.value);
        if (Number.isInteger(target)) this._moveSubpage(Number(select.dataset.movePage), target);
      });
    });
    root.getElementById("physicalDiscard")?.addEventListener("click", () => {
      this._physical = structuredClone(this._physicalBaseline);
      this._mappingDrafts().clear();
      this._layoutDraftsByRemote.delete(this._draftScope());
      this._resetPhysicalOrigins(this._physical);
      this._normalizeSelection();
      this._physicalStatus = "";
      this._render();
    });
  }

  _draftKey(button) {
    if (!button) return null;
    const page = this._physical?.pages?.find((item) => item.index === button.button_page);
    const key = page?.buttons?.find((item) => item.index === button.button_index);
    return key ? { page, key } : null;
  }



  _pageControl(button, key) {
    const index = key ? key.index : button.button_index;
    if (button.button_page !== 0 || index > 3) return "";
    const letter = "ABCD"[index];
    const target = index + 1;
    const nativeProfile = this._nativeProfile(this._physical.native_type || this._physical.template);
    if (this._physical.kind === "native" && !nativeProfile?.subpages?.some(
      (item) => item.index === target && item.link_index != null)) {
      return "";
    }
    const existing = this._pages().find((item) => item.index === target);
    if (existing) {
      return `<p class="small">Key <b>${letter}</b> already opens <b>${escapeHtml(existing.name)}</b>.
        <button class="link-button" data-page-link="${target}">Open it</button></p>`;
    }
    return `<div class="key-actions">
        <button class="secondary compact" id="openCustomPage">Turn key ${letter} into a page</button>
      </div>
      <p class="small">The key stops sending a command and instead opens a new screen of its
        own, where you can put as many buttons as fit. That is how the remote works: a key does
        one or the other, never both.</p>`;
  }

  _renderKeyEditor(button) {
    if (!this._physical) return "";
    const found = this._draftKey(button);
    const kind = this._physical.kind;
    if (!found) {
      // A position with no command has no entry in the draft layout. It is still a real key on
      // the remote, so offer the two things that can be done with it rather than nothing.
      const page = this._physical.pages?.find((item) => item.index === button.button_page);
      if (!page) return "";
      const label = kind === "native" ? "Assign an action" : "Give this key a command";
      return `<div class="action-box key-editor">
        ${kind === "native" ? "" : '<div class="action-title"><b>On the remote</b><span>this position is empty</span></div>'}
        <div class="key-actions">
          <button class="secondary compact" id="addKeyHere">${label}</button>
        </div>
        ${this._pageControl(button, null)}
      </div>`;
    }
    const { page, key } = found;
    if (kind === "native" && page.index) {
      return this._renderGlyphPicker(key, "glyph", "Button icon", key.function);
    }
    const linkedPage = button.button_page === 0 && key.index < 4
      ? this._physical.pages.find((item) => item.index === key.index + 1)
      : null;
    const pageControl = this._pageControl(button, key);
    const clearKey = `<button class="secondary compact destructive" id="removeKey"
      title="The key stays on the remote and sends nothing until you give it another command">Clear this key</button>`;
    if (kind === "native") {
      const glyphPicker = key.index < 4
        ? this._renderGlyphPicker(key, "glyph", "Button icon", key.function) : "";
      const stockKey = this._nativeProfile(this._physical.native_type || this._physical.template)
        ?.main_keys?.some((slot) => slot.index === key.index && slot.actionable);
      const canClear = !linkedPage && (key.index < 4 || !stockKey);
      return `${glyphPicker}${canClear || pageControl ? `<div class="key-editor">
        ${canClear ? `<div class="key-actions">${clearKey}</div>` : ""}
        ${pageControl}</div>` : ""}`;
    }
    const transports = kind === "hid" ? ["hid", "ir"] : ["stored", "ir"];
    const label = { stored: "Original IR command", hid: "HID", ir: "IR" };
    return `<div class="action-box key-editor">
      <div class="action-title"><b>On the remote</b><span>${linkedPage
        ? `opens Page ${"ABCD"[linkedPage.index - 1] || linkedPage.index}`
        : "what this key sends when pressed"}</span></div>
      <label>Command type<select data-key-field="transport">${
        transports.map((item) => `<option value="${item}" ${key.transport === item ? "selected" : ""}>${label[item]}</option>`).join("")
      }</select></label>
      ${key.transport === "hid" ? `<label>This key sends<select data-key-field="function">${
        this._hidFunctionOptions(key.function)
      }</select></label>` : ""}
      ${key.transport === "ir" ? `
        ${kind === "hid" && (page.index || key.index < 4)
          ? this._renderGlyphPicker(key, "glyph", "Button icon", key.function ?? 0x07D3,
            Object.keys(NATIVE_GLYPH_LABELS).map(Number).filter((code) => code > 0)) : ""}
        ${(this._physicalSources || []).length ? `<label>Copy from a button already on one of your remotes<select data-key-field="ir_source">
            <option value="">Choose…</option>${
            this._physicalSources.map((source, index) => `<option value="${index}" ${key.code_hex === source.code_hex ? "selected" : ""}>${escapeHtml(source.label)}</option>`).join("")
          }</select></label>` : ""}
        <label>IR code (hex)<textarea data-key-field="code_hex" spellcheck="false"
          placeholder="Paste the raw code, or copy one from a saved button above"
          >${escapeHtml(key.code_hex || "")}</textarea></label>
        ${this._renderCatalogPicker()}` : ""}
      <div class="key-actions">
        ${button.button_page || linkedPage ? "" : clearKey}
      </div>
      ${pageControl}
    </div>`;
  }

  _hidFunctionOptions(current = 0) {
    const functions = this._physicalFunctions || [];
    const selected = functions.find((item) => item.value === current || item.aliases?.includes(current));
    const options = functions.map((item) => `<option value="${item === selected ? current : item.value}"
      ${item === selected ? "selected" : ""}>${escapeHtml(item.label)}</option>`);
    if (!selected) {
      const code = current.toString(16).toUpperCase().padStart(4, "0");
      options.unshift(`<option value="${current}" selected>No HID action (0x${code})</option>`);
    }
    return options.join("");
  }

  _renderCatalogPicker() {
    const cat = this._catalog;
    if (cat.available === false) {
      return `<p class="small">The bundled IR catalog is not installed, so a pasted code is the
        only way to set this key.</p>`;
    }
    if (cat.available === null) return `<p class="small">Loading the IR catalog…</p>`;
    const option = (value, label, selected) =>
      `<option value="${escapeHtml(String(value))}" ${selected ? "selected" : ""}>${escapeHtml(label)}</option>`;
    return `<details class="catalog" ${cat.brand ? "open" : ""}>
      <summary>Choose a device from the IR catalog</summary>
      <label>Device type<select data-catalog="type">${
        cat.types.map((item) => option(item.value, item.label, item.value === cat.remoteType)).join("")
      }</select></label>
      <label>Brand<input type="search" data-catalog="search" autocomplete="off"
        value="${escapeHtml(cat.search || "")}"
        placeholder="Search ${cat.brands.length} brand${cat.brands.length === 1 ? "" : "s"}…"></label>
      <select data-catalog="brand" size="6">${
        this._catalogBrands().slice(0, 300).map((name) => option(name, name, name === cat.brand)).join("")
      }</select>
      ${cat.models.length ? `<label>Model<select data-catalog="model">
        <option value="">Choose a model…</option>${
          cat.models.map((item) => option(item.hxd_index, item.label, item.hxd_index === cat.hxd)).join("")
        }</select></label>` : ""}
      ${cat.buttons.length ? `<label>Button<select data-catalog="button">
        <option value="">Choose the button to copy…</option>${
          cat.buttons.map((item, index) => option(index, item.label, false)).join("")
        }</select></label>` : ""}
      ${cat.busy ? `<p class="small">${escapeHtml(cat.busy)}</p>` : ""}
      ${this._feedback(cat.error, "error", "IR catalog")}
    </details>`;
  }

  async _ensureCatalog() {
    if (this._catalog.available !== null || this._catalogLoading) return;
    this._catalogLoading = true;
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/catalog/types` });
      this._catalog.types = result.types || [];
      this._catalog.available = !!result.available;
      if (this._catalog.available) await this._loadCatalogBrands(this._catalog.remoteType);
    } catch (error) {
      this._catalog.available = false;
    }
    this._catalogLoading = false;
    this._render();
  }

  async _loadCatalogBrands(remoteType) {
    const cat = this._catalog;
    Object.assign(cat, { remoteType, brand: "", search: "", models: [], hxd: "", buttons: [], error: "" });
    const result = await this._hass.callWS({
      type: `${DOMAIN}/studio/catalog/brands`, remote_type: remoteType });
    cat.brands = result.brands || [];
  }

  _editor(button, remote) {
    if (this._physical?.kind === "native" && button.button_page === 0 && !this._draftKey(button)) {
      return `<div class="editor-head"><h2>${escapeHtml(button.label)}</h2></div>
        ${this._renderKeyEditor(button)}`;
    }
    const [status, statusLabel] = this._status(button);
    return `
      <div class="editor-head">
        <div><span class="status-pill ${status}">${escapeHtml(statusLabel)}</span><h2>${escapeHtml(button.label)}</h2></div>
        ${remote?.reachability?.level === "none" ? "" : `<button class="secondary compact" id="testButton"
          ${this._canTest(button) ? "" : "disabled"}
          title="Run the saved Home Assistant mapping for this button">Test saved mapping</button>`}
      </div>
      <dl>
        <div><dt>Button ID</dt><dd><code>${escapeHtml(button.button_id)}</code></dd></div>
        <div><dt>Page / index</dt><dd>${button.button_page} / ${button.button_index}</dd></div>
        ${this._physical?.kind === "native"
          ? "" : `<div><dt>Function</dt><dd>${button.button_function}</dd></div>`}
        <div><dt>Remote</dt><dd>${escapeHtml(remote.remote_id)}</dd></div>
      </dl>
      ${this._renderKeyEditor(button)}
      ${button.draft_only ? '<p class="small">New button. Saving writes the layout to the remote before saving its Home Assistant actions.</p>' : ""}
      ${remote?.reachability?.level === "none" ? `<div class="explanation">
        <b>No Home Assistant mapping for this remote.</b><span>${escapeHtml(remote.reachability.text)}
        A mapping saved here would never run, so it is not offered — what the key is on the
        remote is set above.</span></div>` : `
      <div class="mode-tabs">
        <button data-mode="preset" class="${this._mode === "preset" ? "selected" : ""}">Quick bind</button>
        <button data-mode="actions" class="${this._mode === "actions" ? "selected" : ""}">Custom actions</button>
        <button data-mode="disabled" class="${this._mode === "disabled" ? "selected" : ""}">Disabled</button>
      </div>
      <div class="mode-content">
        ${this._mode === "preset" ? `<div class="explanation"><b>Use the whole-remote preset.</b><span>${
          button.preset_action
            ? `This button will ${escapeHtml(button.preset_action.replaceAll("_", " "))}${
                remote.binding?.entity_id ? ` ${escapeHtml(remote.binding.entity_id)}` : ""}.`
            : "No Quick-bind action currently matches this button."
        }</span></div>` : ""}
        ${this._mode === "disabled" ? `<div class="explanation danger"><b>Ignore this button.</b><span>Physical presses will be received but no Home Assistant action will run.</span></div>` : ""}
        ${this._mode === "actions" ? `<div class="action-box"><div class="action-title"><b>Home Assistant actions</b><span id="actionSummary">${this._actionSummary()}</span></div><div id="visualActionEditor"></div><div id="selectOptionWarning" class="small" role="status">${escapeHtml(this._selectOptionWarning())}</div><p class="json-help">To run a script, choose <b>Script: Turn on</b> and select the script, or choose the script’s own action.</p><details><summary>Advanced JSON fallback</summary><textarea id="actionsJson" spellcheck="false" class="${this._jsonValid ? "" : "invalid"}">${escapeHtml(this._actionJsonDraft ?? JSON.stringify(this._draftActions, null, 2))}</textarea></details></div>` : ""}
      </div>
      `}
      `;
  }

  _actionSummary() {
    const count = this._draftActions.length;
    return count ? `${count} action${count === 1 ? "" : "s"}` : "No custom actions";
  }

  _selectOptionWarning() {
    if (!this._jsonValid) return "";
    const warnings = [];
    for (const step of this._draftActions) {
      if ((step?.action ?? step?.service) !== "select.select_option") continue;
      const option = step.data?.option;
      if (typeof option !== "string" || option.includes("{{") || option.includes("{%")) continue;
      const targets = step.target?.entity_id ?? step.data?.entity_id;
      for (const entity of [targets].flat()) {
        const state = this._hass?.states?.[entity];
        const options = state?.attributes?.options;
        if (state?.state === "unavailable" || !Array.isArray(options)
            || !options.length || options.includes(option)) continue;
        warnings.push(`${entity} currently offers ${options.join(", ")}. “${option}” is unavailable for this entity.`);
      }
    }
    return warnings.join(" ");
  }

  _updateSelectOptionWarning() {
    const warning = this.shadowRoot.getElementById("selectOptionWarning");
    if (warning) warning.textContent = this._selectOptionWarning();
  }

  _saveStatus() {
    const mappingDrafts = [...this._mappingDrafts().values()];
    if (mappingDrafts.some(({ mode, valid }) => mode === "actions" && !valid)) {
      return "Fix the invalid actions JSON before saving.";
    }
    if (this._physicalChanges() && this._physical.pages.length === 1 && !this._physical.pages[0].buttons.length) {
      return "Add a command to Main or keep a menu with at least one row.";
    }
    if (this._physicalChanges() && this._physical.pages.some((page) => page.index && !page.buttons.length)) {
      return "Add a row to each new menu or remove the empty menu.";
    }
    if (this._hasAppearanceChanges() && !this._appearanceDraftsByRemote.get(this._draftScope()).name.trim()) {
      return "Give the remote a name before saving.";
    }
    if (this._remote()?.matter) {
      const captionProblem = this._captionsProblem(
        this._remote(), this._appearanceDraftsByRemote?.get(this._draftScope()));
      if (captionProblem) return captionProblem;
    }
    return "";
  }

  _saveLabel() {
    if (this._saving) return "Saving changes…";
    const pending = this._mappingDrafts().size || this._physicalChanges()
      || this._hasAppearanceChanges() || this._presetDraftsByRemote?.has(this._draftScope());
    return pending ? "Unsaved changes for this remote" : "";
  }

  _canSave() {
    return !this._physicalBusy && !this._saving && !this._saveStatus()
      && Boolean(this._physicalChanges() || this._mappingDrafts().size
        || this._hasAppearanceChanges() || this._presetDraftsByRemote?.has(this._draftScope()));
  }

  _renderSaveButton() {
    return `<button class="primary compact" id="saveButton" ${this._canSave() ? "" : "disabled"}>${this._saving ? "Saving…" : "Save"}</button>`;
  }

  _updateSaveButton() {
    const save = this.shadowRoot.getElementById("saveButton");
    if (save) save.disabled = !this._canSave();
    const status = this.shadowRoot.getElementById("saveStatus");
    if (status) status.textContent = this._saveStatus() || this._saveLabel();
  }

  _canTest(button = this._button()) {
    return Boolean(button && !button.draft_only && !this._dirty && !this._saving && !this._physicalChanges());
  }

  _updateActionEditor() {
    if (this._scenePanel) {
      this._updateSelectOptionWarning();
      const summary = this.shadowRoot.getElementById("actionSummary");
      if (summary) summary.textContent = this._actionSummary();
      return;
    }
    this._updateSelectOptionWarning();
    const summary = this.shadowRoot.getElementById("actionSummary");
    if (summary) summary.textContent = this._actionSummary();
    const test = this.shadowRoot.getElementById("testButton");
    if (test) test.disabled = !this._canTest();
    this._updateSaveButton();
  }

  _wireEvents() {
    const root = this.shadowRoot;
    this._wireFeedback();
    for (const id of ["entrySelect", "remoteSelect", "refresh", "addRemote",
                      "recreateRemote", "moveRemote", "deleteRemote"]) {
      const el = root.getElementById(id);
      if (el) el.disabled = this._physicalBusy || this._saving || Boolean(this._scenePanel?.busy);
    }
    root.getElementById("refresh")?.addEventListener("click", () => this._refresh());
    root.getElementById("checkRemoteCapacity")?.addEventListener("click", () => {
      void this._ensureSources(true);
      this._render();
    });
    root.getElementById("readDeviceTable")?.addEventListener("click", () => this._readDeviceTable());
    root.querySelector(".device-table")?.addEventListener("toggle", (event) => {
      if (this._deviceTable && !this._deviceTable.loading) this._deviceTable.open = event.target.open;
    });
    root.querySelectorAll("[data-drag-handle]").forEach((handle) => {
      handle.addEventListener("pointerdown", (event) => this._startRowDrag(event, Number(handle.dataset.dragHandle)));
    });
    root.querySelectorAll("[data-move-row]").forEach((button) => {
      button.addEventListener("click", () =>
        this._moveTableRow(Number(button.dataset.moveRow), Number(button.dataset.moveDir)));
    });
    root.getElementById("applyOrder")?.addEventListener("click", () => this._applyTableOrder());
    root.getElementById("resetOrder")?.addEventListener("click", () => {
      if (this._deviceTable) { this._deviceTable.order = (this._deviceTable.rows || []).map((row) => row.slot); }
      this._render();
    });
    root.querySelectorAll("[data-delete-row]").forEach((button) => {
      button.addEventListener("click", () => this._deleteTableRow(button.dataset));
    });
    root.getElementById("cleanupBindings")?.addEventListener("click", async () => {
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/bindings/cleanup`,
          entry_id: this._entryId });
        this._notify(result.removed.length
          ? `Removed ${result.removed.length} leftover action set(s)`
          : "Nothing to remove");
        this._diagnostics = null;
        await this._load();
      } catch (error) { this._error = error?.message || String(error); this._render(); }
    });
    root.getElementById("addKeyToPage")?.addEventListener("click", () => this._addKeyToCurrentPage());
    root.getElementById("removeThisPage")?.addEventListener("click", () => {
      const page = this._physical?.pages?.find((item) => item.index === this._page()?.index);
      if (!page) return;
      this._removeMenu(page);
    });
    root.getElementById("moveCurrentPage")?.addEventListener("change", (event) => {
      if (!event.target.value) return;
      this._moveSubpage(this._page()?.index, Number(event.target.value));
    });

    root.getElementById("addRemote")?.addEventListener("click", () => this._openAddRemote());

    root.getElementById("recreateRemote")?.addEventListener("click", async () => {
      const remote = this._remote();
      if (!remote) return;
      // This deletes the tile and writes it again, so it is confirmed like a delete.
      if (!confirm(`Write "${remote.name}" to the Universal Remote again? The current tile is removed first.`)) return;
      this._physicalBusy = true;
      this._render();
      let rewriteError = null;
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/recreate`,
          entry_id: this._entryId, remote_id: this._remoteId });
        this._notify(`Rewritten into slot ${result.slot}`, "success");
        this._physical = null;
        this._physicalFor = null;
        this._error = null;
      } catch (error) { rewriteError = error?.message || String(error); }
      finally {
        this._physicalBusy = false;
        this._sources = null;
        await this._load();
      }
      if (rewriteError) {
        this._error = rewriteError;
        this._render();
      }
    });

    root.getElementById("moveRemote")?.addEventListener("click", async () => {
      const remote = this._remote();
      if (!remote) return;
      this._sources = null;
      await this._ensureSources();
      if (!this._sources?.native_options?.next_move_address) {
        this._notify("No free address is available on a configured bridge.", "warning");
        return;
      }
      if (!confirm(`This removes "${remote.name}" from the remote and writes it again. Continue?`)) return;
      let moveError;
      this._physicalBusy = true;
      this._render();
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/recreate`,
          entry_id: this._entryId, remote_id: this._remoteId,
          auto_address: true });
        this._notify(result?.warning
          || (result.moved_from
            ? `Moved from ${result.moved_from} to ${result.address}`
            : `Rewritten into slot ${result.slot}`), result?.warning ? "warning" : "success");
        this._sources = null;
        this._physical = null;
        this._physicalFor = null;
        this._error = null;
      } catch (error) { moveError = error?.message || String(error); }
      finally {
        this._physicalBusy = false;
        this._sources = null;
        await this._load();
      }
      if (moveError) {
        this._error = moveError;
        this._render();
      }
    });

    root.getElementById("deleteRemote")?.addEventListener("click", async () => {
      if (this._scenePanel) {
        if (!this._scenePanel.busy && confirm(`Delete "${this._scenePanel.draft.name}" from the remote?`)) await this._saveScene(true);
        return;
      }
      const remote = this._remote();
      if (!remote) return;
      // Deleting touches the remote itself and cannot be undone from here, so it is confirmed
      // by name rather than by a single click next to the selector.
      if (!confirm(`Delete "${remote.name}" from the Universal Remote? This cannot be undone.`)) return;
      this._physicalBusy = true;
      this._render();
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/delete`,
          entry_id: this._entryId, remote_id: this._remoteId });
        this._notify(result?.device_untouched
          ? "Removed from Home Assistant; it was no longer on the remote"
          : "Remote deleted", "success");
        this._remoteId = null;
        this._buttonId = null;
        this._physical = null;
        this._physicalFor = null;
        this._error = null;
      } catch (error) { this._error = error?.message || String(error); }
      finally {
        this._physicalBusy = false;
        this._sources = null;
        await this._load();
      }
    });


    this._wirePhysical();
    root.getElementById("entrySelect")?.addEventListener("change", (event) => {
      if (this._saving) return;
      this._notice = null;
      this._error = null;
      this._rememberMapping();
      this._stashLayout();
      this._entryId = event.target.value;
      this._iconPickerFor = null;
      this._cloud = null;
      this._sources = null;
      this._physical = null;
      this._physicalFor = null;
      this._remoteId = null;
      this._buttonId = null;
      this._normalizeSelection();
      this._render();
    });
    root.getElementById("remoteSelect")?.addEventListener("change", (event) => this._pickRemote(event.target.value));
    root.querySelectorAll("[data-page]").forEach((element) =>
      element.addEventListener("click", () => {
        this._pageIndex = Number(element.dataset.page);
        this._buttonId = null;
        this._normalizeSelection();
        this._pageEditing = true;
        this._render();
      }),
    );
    root.querySelectorAll("[data-page-link]").forEach((element) => {
      const open = () => {
        this._pageIndex = Number(element.dataset.pageLink);
        this._buttonId = null;
        this._normalizeSelection();
        this._pageEditing = true;
        this._render();
      };
      element.addEventListener("click", open);
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
      });
    });

    root.querySelectorAll("[data-remote]").forEach((element) => {
      element.addEventListener("click", () => this._pickRemote(element.dataset.remote));
    });

    root.querySelectorAll("[data-icon-for]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._iconPickerFor = element.dataset.iconFor;
        this._selectButton(null, false);
        this._render();
      });
    });
    root.getElementById("enterHidPairMode")?.addEventListener("click", () => this._enterHidPairMode());

    const editAppearance = (change) => {
      const remote = this._remote();
      const scope = this._draftScope();
      const draft = this._appearanceDraftsByRemote.get(scope)
        || { name: remote.name, icon: remote.icon, ...(remote.matter
          ? { captions: [...(remote.matter.fields || remote.matter.captions)] } : {}) };
      this._appearanceDraftsByRemote.set(scope, { ...draft, ...change });
      this._updateSaveButton();
    };
    root.querySelectorAll("[data-pick-icon]").forEach((element) => element.addEventListener("click", () => {
      editAppearance({ icon: element.dataset.pickIcon });
      this._render();
    }));
    root.querySelectorAll(".appearance-editor [data-matter-caption]").forEach((field) => {
      field.addEventListener("input", () => {
        const remote = this._remote();
        if (!remote?.matter) return;
        const scope = this._draftScope();
        const base = this._appearanceDraftsByRemote.get(scope)?.captions
          || remote.matter.fields || remote.matter.captions;
        const captions = [...base];
        captions[Number(field.dataset.matterCaption)] = field.value;
        editAppearance({ captions });
        const counter = field.parentElement?.querySelector("small");
        const index = Number(field.dataset.matterCaption);
        if (counter) counter.textContent = this._captionCounter(
          field.value, remote.matter.max_bytes, remote.matter.captions[index]);
      });
    });
    root.querySelector(".appearance-editor [data-matter-interval]")?.addEventListener("input", (event) => {
      editAppearance({ interval: event.target.value });
    });

    root.querySelector("[data-rename-input]")?.addEventListener("input", (event) => {
      editAppearance({ name: event.target.value });
    });
    root.querySelector("[data-rename-input]")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); void this._save(); }
    });

    root.querySelectorAll("[data-button]").forEach((element) => {
      const select = () => {
        if (element.closest(".screen-softkeys")) this._pageIndex = 0;
        const button = this._page()?.buttons.find((item) => item.button_id === element.dataset.button);
        this._selectButton(button);
      };
      element.addEventListener("click", select);
      if (element.getAttribute("role") === "button") {
        element.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            select();
          }
        });
      }
    });
    root.querySelectorAll("[data-mode]").forEach((element) =>
      element.addEventListener("click", () => {
        const mode = element.dataset.mode;
        if (this._mode === mode) return;
        this._mode = mode;
        if (mode !== "actions" || this._draftActions.length || !this._jsonValid) {
          this._dirty = true;
          this._rememberMapping();
        }
        this._render();
      }),
    );
    root.getElementById("saveButton")?.addEventListener("click", () => this._save());
    root.getElementById("testButton")?.addEventListener("click", () => this._test());
    root.getElementById("lightSelect")?.addEventListener("change", (event) => {
      const scope = this._draftScope();
      const entity = event.target.value;
      if (entity && entity !== this._remote()?.binding?.entity_id) this._presetDraftsByRemote.set(scope, entity);
      else {
        this._presetDraftsByRemote.delete(scope);
        event.target.value = this._remote()?.binding?.entity_id || "";
      }
      this._updateSaveButton();
    });
    root.getElementById("actionsJson")?.addEventListener("input", (event) => {
      this._actionJsonDraft = event.target.value;
      try {
        const parsed = JSON.parse(event.target.value || "[]");
        if (!Array.isArray(parsed)) throw new Error("The root value must be an array");
        this._draftActions = parsed;
        this._dirty = true;
        this._jsonValid = true;
        event.target.classList.remove("invalid");
        if (this._actionSelectorEl) this._actionSelectorEl.value = structuredClone(parsed);
      } catch (_error) {
        this._dirty = true;
        this._jsonValid = false;
        event.target.classList.add("invalid");
      }
      this._rememberMapping();
      this._updateActionEditor();
    });
  }

  async _mountActionSelector() {
    this._actionSelectorEl = null;
    const host = this.shadowRoot.getElementById("visualActionEditor");
    if (!host || this._mode !== "actions") return;
    const token = Symbol("mount");
    this._mountToken = token;
    host.innerHTML = `<div class="json-help">Loading the action editor…</div>`;
    const selectorAvailable = await this._ensureActionSelector();
    if (this._mountToken !== token || !host.isConnected || this._mode !== "actions") return;
    if (!selectorAvailable) {
      host.innerHTML = `<div class="json-help">The visual action editor could not be loaded. <button class="link-button" id="retryActionEditor">Retry</button><br>Until it loads, the JSON field below accepts any Home Assistant action.</div>`;
      host.querySelector("#retryActionEditor")?.addEventListener("click", () => this._mountActionSelector());
      const details = host.closest(".action-box")?.querySelector("details");
      if (details) details.open = true;
      return;
    }
    const selector = document.createElement("ha-selector");
    selector.hass = this._hass;
    selector.selector = { action: {} };
    selector.label = "Actions";
    selector.addEventListener("value-changed", (event) => {
      if (!selector.isConnected || this._actionSelectorEl !== selector) return;
      const actions = event.detail?.value ?? [];
      if (!Array.isArray(actions) || (this._jsonValid
          && JSON.stringify(actions) === JSON.stringify(this._draftActions))) return;
      this._draftActions = structuredClone(actions);
      selector.value = structuredClone(actions);
      this._dirty = true;
      this._jsonValid = true;
      this._actionJsonDraft = undefined;
      const textarea = this.shadowRoot.getElementById("actionsJson");
      if (textarea) {
        textarea.value = JSON.stringify(this._draftActions, null, 2);
        textarea.classList.remove("invalid");
      }
      this._rememberMapping();
      this._updateActionEditor();
    });
    this._actionSelectorEl = selector;
    host.innerHTML = "";
    host.append(selector);
    // After appending, not before: a property set on a detached element is the usual way a
    // web component ends up showing nothing when it does have a value.
    selector.value = structuredClone(this._draftActions);
  }

  async _ensureActionSelector() {
    if (customElements.get("ha-selector")) return true;

    // Home Assistant lazy-loads its form controls. A custom panel can be opened
    // before any core page has registered ha-selector, so waiting for the tag
    // alone can otherwise hang forever. Loading a built-in card editor is the
    // supported frontend entry point that also loads ha-form/ha-selector.
    try {
      if (typeof window.loadCardHelpers === "function") {
        const helpers = await window.loadCardHelpers();
        const card = await helpers?.createCardElement?.({
          type: "button",
          name: "Remote Studio action editor loader",
        });
        if (typeof card?.constructor?.getConfigElement === "function") {
          await card.constructor.getConfigElement();
        }
      }
    } catch (error) {
      console.warn("SwitchBot URC: could not preload Home Assistant selectors", error);
    }

    if (customElements.get("ha-selector")) return true;
    let timer;
    try {
      return await Promise.race([
        customElements.whenDefined("ha-selector").then(() => true),
        new Promise((resolve) => {
          timer = setTimeout(() => resolve(false), 5000);
        }),
      ]);
    } finally {
      clearTimeout(timer);
    }
  }

  async _applyPhysical() {
    if (!this._physicalChanges()) return;
    const identityMigrations = this._identityMigrations();
    const identityRemovals = this._identityRemovals();
    this._physicalBusy = true;
    this._render();
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/apply`,
        entry_id: this._entryId, remote_id: this._remoteId, layout: this._physical,
        identity_migrations: identityMigrations, identity_removals: identityRemovals });
      if (result.entry) this._replaceEntry(result.entry);
      this._physicalStatus = result.status;
      this._physical = result.layout || this._physical;
      this._physicalBaseline = structuredClone(this._physical);
      this._resetPhysicalOrigins(this._physical);
      this._layoutDraftsByRemote?.delete(this._draftScope());
    } finally {
      this._physicalBusy = false;
      this._render();
    }
  }

  async _save() {
    if (!this._canSave()) return;
    const entryId = this._entryId;
    const remoteId = this._remoteId;
    const scope = this._draftScope();
    const layoutChanges = this._physicalChanges();
    const mappings = this._mappingDrafts();
    this.shadowRoot.activeElement?.blur();
    this._saving = true;
    this._error = null;
    this._render();
    try {
      // The remote must expose the new button positions before HA can save actions for them.
      if (layoutChanges) await this._applyPhysical();
      const entity = this._presetDraftsByRemote?.get(scope);
      if (entity) {
        const updated = await this._hass.callWS({
          type: `${DOMAIN}/studio/quick_bind`, entry_id: entryId, remote_id: remoteId, entity_id: entity,
        });
        this._replaceEntry(updated);
        this._presetDraftsByRemote.delete(scope);
      }
      for (const [buttonId, mapping] of mappings) {
        const mode = mapping.mode === "actions" && !mapping.actions.length ? "preset" : mapping.mode;
        const updated = await this._hass.callWS({
          type: `${DOMAIN}/studio/save_button_action`, entry_id: entryId, remote_id: remoteId,
          button_id: buttonId, mode, actions: mode === "actions" ? mapping.actions : [],
        });
        this._replaceEntry(updated);
        mappings.delete(buttonId);
        if (buttonId === this._buttonId) this._dirty = false;
      }
      const warning = await this._saveAppearance();
      this._dirty = false;
      await this._load();
      if (!this._error) {
        this._notify(warning || (layoutChanges ? "Layout and actions saved. The remote acknowledged the layout." : "Changes saved."), warning ? "warning" : "success");
      }
    } catch (error) {
      this._error = error?.message || String(error);
      this._selectButton(this._button(), false);
    } finally {
      this._saving = false;
      this._render();
    }
  }

  async _test() {
    if (!this._canTest()) return;
    try {
      await this._hass.callWS({
        type: `${DOMAIN}/studio/test_button`,
        entry_id: this._entryId,
        remote_id: this._remoteId,
        button_id: this._buttonId,
      });
      this._notify("Test press sent to Home Assistant", "success");
    } catch (error) {
      this._notify(error?.message || String(error), "error");
    }
  }

  _replaceEntry(updated) {
    const index = this._entries().findIndex((item) => item.entry_id === updated.entry_id);
    if (index >= 0) this._data.entries[index] = updated;
  }

  _feedback(message, tone = "info", context = "", dismissible = false) {
    if (!message) return "";
    const labels = { error: "Could not complete", warning: "Check this", success: "Done", info: "Information" };
    return `<div class="studio-feedback ${tone}" role="${tone === "error" ? "alert" : "status"}">
      <div><b>${escapeHtml(context || labels[tone])}</b><span>${escapeHtml(message)}</span></div>
      ${dismissible ? '<button type="button" class="link-button" id="dismissFeedback" aria-label="Dismiss notification">Dismiss</button>' : ""}</div>`;
  }

  _renderStudioFeedback() {
    if (this._error) return this._feedback(this._error, "error", "Remote Studio", true);
    const notice = this._notice;
    if (!notice || notice.entryId !== this._entryId) return "";
    return this._feedback(notice.message, notice.tone, notice.context, true);
  }

  _wireFeedback() {
    this.shadowRoot.getElementById("dismissFeedback")?.addEventListener("click", () => {
      this._notice = null;
      this._error = null;
      const feedback = this.shadowRoot.getElementById("studioFeedback");
      if (feedback) feedback.innerHTML = "";
    });
  }

  _notify(message, tone = "info") {
    this._error = null;
    this._notice = { message, tone, entryId: this._entryId, context: this._remote()?.name || "Remote Studio" };
    const feedback = this.shadowRoot.getElementById("studioFeedback");
    if (feedback) {
      feedback.innerHTML = this._renderStudioFeedback();
      this._wireFeedback();
    }
  }

  _styles() {
    return `
      #studioFeedback{position:sticky;top:12px;z-index:30}
      .studio-feedback{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin:14px 0;padding:14px 16px;border:1px solid var(--divider-color,#ddd);border-left:4px solid var(--primary-color,#03a9f4);border-radius:12px;font-size:13px;line-height:1.5;color:var(--primary-text-color,#17202a);
        /* Opaque even when the theme's card colour is translucent: the notice floats over content. */
        background:linear-gradient(var(--card-background-color,#fff),var(--card-background-color,#fff)),var(--primary-background-color,#fff);
        box-shadow:0 10px 30px #0000002e;-webkit-backdrop-filter:blur(14px);backdrop-filter:blur(14px)}
      .studio-feedback>div{display:grid;gap:3px;min-width:0}.studio-feedback span{white-space:pre-wrap;overflow-wrap:anywhere}.studio-feedback b{font-size:13px}.studio-feedback .link-button{flex:none;margin-top:2px}
      /* The generic .error rule (translucent red, 22px padding) also matches this notice; take it back. */
      .studio-feedback.error{margin:14px 0;padding:14px 16px;border-radius:12px;color:var(--primary-text-color,#17202a);
        background:linear-gradient(#ee5b6618,#ee5b6618),linear-gradient(var(--card-background-color,#fff),var(--card-background-color,#fff)),var(--primary-background-color,#fff);
        border-left-color:var(--error-color,#db4437)}
      .studio-feedback.error b{color:var(--error-color,#c62828)}.studio-feedback.warning{border-left-color:var(--warning-color,#e09b24)}.studio-feedback.success{border-left-color:var(--success-color,#209e69)}
      .device-settings-dialog{box-sizing:border-box;width:min(620px,calc(100vw - 32px));max-height:calc(100dvh - 48px);padding:26px;border:1px solid var(--divider-color,#ddd);border-radius:22px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#17202a);box-shadow:0 24px 80px #0005;overflow:auto}
      .device-settings-dialog::backdrop{background:#0008}
      .device-settings-dialog h2{margin:0;font-size:24px;letter-spacing:-.02em}
      .device-settings-dialog .editor-head{margin-bottom:14px}
      .device-settings-dialog .small{line-height:1.5;color:var(--secondary-text-color,#68727d)}
      .device-settings-dialog fieldset{min-width:0;padding:0;margin:0;border:0;display:grid;gap:0}
      .remote-setting-toggle{display:flex;justify-content:space-between;align-items:center;gap:20px;padding:15px 0;border-bottom:1px solid var(--divider-color,#ddd);font-size:14px;font-weight:600;cursor:pointer}
      .remote-setting-toggle small{display:block;margin-top:5px;font-size:12px;font-weight:400;line-height:1.5;color:var(--secondary-text-color,#68727d)}
      .remote-setting-toggle input{flex:none;width:20px;height:20px;accent-color:var(--primary-color,#03a9f4)}
      .remote-setting-range{display:grid;gap:12px;padding-top:20px;font-size:14px;font-weight:600}
      .remote-setting-range>span{display:flex;justify-content:space-between;gap:16px}
      .remote-setting-range output{font-variant-numeric:tabular-nums;color:var(--secondary-text-color,#68727d)}
      .remote-setting-range input{width:100%;margin:0;accent-color:var(--primary-color,#03a9f4)}
      .remote-setting-range:has(input:disabled){opacity:.5}
      .remote-setting-selects{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:16px;margin-top:22px}
      .remote-setting-selects label{display:grid;gap:8px;font-size:13px;font-weight:600}
      .remote-setting-selects select{width:100%;min-width:0}
      .device-settings-dialog .studio-save{margin-top:12px}
      .scene-icon{width:18px;height:18px;object-fit:contain}
      .scene-tile{background-size:cover;display:grid;place-items:center;width:18px;height:18px;min-width:18px;border-radius:8px;flex:none;overflow:hidden}.scene-tile .scene-icon{width:100%;height:100%}
      .scene-icon-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(52px,1fr));gap:8px}
      .scene-icon-grid button{display:grid;place-items:center;aspect-ratio:1;min-height:48px;padding:0;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--secondary-background-color,#f5f6f8);cursor:pointer;transition:border-color .15s,background .15s}
      .scene-icon-grid button:hover{border-color:var(--primary-color,#03a9f4)}
      .scene-icon-grid .scene-icon{width:28px;height:28px}
      .scene-icon-grid button.selected{border:2px solid var(--primary-color,#03a9f4);background:color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff))}
      .scene-colors{display:flex;flex-wrap:wrap;gap:12px;padding:3px}
      .scene-colors button{background-size:cover;width:36px;height:36px;border-radius:50%;border:1px solid #00000022;cursor:pointer;transition:transform .12s}
      .scene-colors button:hover{transform:scale(1.08)}
      .scene-colors button.selected{border-color:#fff;box-shadow:0 0 0 2px var(--primary-color,#03a9f4)}
      .scene-icon-grid button:focus-visible,.scene-colors button:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}
      .scene-workspace .editor-head{align-items:center}
      .scene-workspace .editor>.mode-tabs{margin-bottom:20px}
      .scene-workspace .editor>.mode-tabs+div .editor-head{margin-bottom:16px}
      .scene-workspace .editor>.mode-tabs+div .action-box{margin-top:4px}
      .scene-workspace .scr-row .pick-remote{gap:10px}
      .scene-workspace .remote-stage .k.inactive{pointer-events:none;opacity:.5}
      .appearance{display:grid;gap:18px}.appearance-head{display:flex;align-items:flex-start;justify-content:space-between}.appearance-head>div{display:grid;gap:3px}.appearance-head b{font-size:22px;letter-spacing:-.03em}.appearance-head span,.appearance-part-body p,.appearance-note{font-size:12px;line-height:1.45;color:var(--secondary-text-color,#68727d)}
      .add-native-artwork{display:flex;align-items:center;gap:14px;padding:12px;border:1px solid var(--divider-color,#e2e5e8);border-radius:8px;background:var(--secondary-background-color,#f5f6f8)}.add-native-artwork p{line-height:1.5}.add-native-artwork .artwork-preview{width:86px;height:86px}.add-native-artwork .artwork-preview img{max-width:82px;max-height:82px}.ic-fallback{display:grid;place-items:center;flex:none;width:18px;height:18px;color:var(--secondary-text-color,#68727d)}
      .appearance-grid{display:grid;gap:12px}.appearance-part{display:flex;align-items:center;gap:16px;min-width:0;padding:14px;border:1px solid var(--divider-color,#e2e5e8);border-radius:16px;background:var(--secondary-background-color,#f5f6f8)}.appearance-part-body{flex:1;min-width:0}.appearance-part-body label{display:grid;gap:3px;font-size:12px;font-weight:700}.appearance-part-body select{margin-top:3px}.appearance-part-body p{margin:6px 0 0}.artwork-preview,.app-icon-preview{display:grid;place-items:center;flex:none;width:100px;height:100px;border-radius:14px;background:#171d24;color:#fff}.artwork-preview img{display:block;max-width:96px;max-height:96px;object-fit:contain}.app-icon-preview .ic-img{width:74px;height:74px;object-fit:contain}.appearance-profile-save{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px}.appearance-draft{font-size:11px;font-weight:700;color:var(--primary-color,#03a9f4)}
      .native-type-panel{display:grid;gap:10px;min-width:0}.native-type-heading{display:grid;gap:3px}.native-type-heading b{font-size:15px}.native-type-heading span{font-size:12px;color:var(--secondary-text-color,#68727d)}.native-type-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(72px,1fr));gap:8px}
      .native-type-choice{display:grid;place-items:center;min-width:0;min-height:72px;padding:6px;border:1px solid var(--divider-color,#d9dee3);border-radius:8px;background:var(--card-background-color,#fff);cursor:pointer}.native-type-choice:hover{border-color:var(--primary-color,#03a9f4)}.native-type-choice.selected{border-color:var(--primary-color,#03a9f4);box-shadow:inset 0 0 0 1px var(--primary-color,#03a9f4);background:color-mix(in srgb,var(--primary-color,#03a9f4) 8%,var(--card-background-color,#fff))}.native-type-choice:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}.native-type-art{display:grid;place-items:center;width:56px;height:56px;border-radius:6px;background:#171d24;color:#fff}.native-type-art img{max-width:54px;max-height:54px;object-fit:contain}.add-native-type-panel{margin:14px 0}
      .appearance-editor{display:grid;gap:10px;padding-top:16px;border-top:1px solid var(--divider-color,#e2e5e8)}.appearance-editor label{display:grid;gap:6px;font-size:12px;font-weight:700}.appearance-editor input{height:42px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:10px;background:var(--card-background-color,#fff);color:inherit;font:inherit}.appearance-field-label{font-size:12px;font-weight:700}.appearance-icon-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:8px}.appearance-icon-choice{display:grid;justify-items:center;align-content:center;gap:5px;min-height:88px;padding:8px 5px;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--secondary-background-color,#f5f6f8);color:inherit;cursor:pointer}.appearance-icon-choice:hover{border-color:var(--primary-color,#03a9f4)}.appearance-icon-choice.selected{border:2px solid var(--primary-color,#03a9f4);background:color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff))}.appearance-icon-choice .ic-img{width:43px;height:43px;object-fit:contain;padding:4px;border-radius:8px;background:#171d24}.appearance-icon-choice span{font-size:10px;font-weight:700;text-align:center;line-height:1.15}.appearance-note{margin:0}.appearance-icon-choice .ic-art{width:76px;height:52px;object-fit:contain;padding:4px;border-radius:8px;background:#171d24}.appearance-icon-choice .ic-art-default{display:grid;place-items:center;color:#fff;font-size:22px}.appearance-actions{display:flex;gap:8px;flex-wrap:wrap}.appearance-details{display:grid;gap:4px}.appearance-details span{display:block;font:11px/1.5 ui-monospace,monospace;color:var(--secondary-text-color,#68727d)}.appearance .native-profile-warnings{margin:0;padding:12px}
      .native-profile-warnings{display:grid;gap:10px;margin:16px 0 0;padding:14px 16px;border:1px solid var(--divider-color,#e2e5e8);border-radius:8px;background:var(--card-background-color,#fff)}
      .profile-capacity-warning{display:grid;gap:3px;margin-top:14px;padding:11px 13px;border-left:3px solid #bd6a0f;border-radius:5px;background:#bd6a0f12;font-size:12px}.profile-capacity-warning span{color:var(--secondary-text-color,#68727d)}
      .profile-conflicts{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px}.profile-conflict-heading{display:grid;gap:4px;margin-bottom:6px}.profile-conflict-heading span,.profile-conflict-row small{color:var(--secondary-text-color,#68727d);font-size:12px}
      .profile-conflict-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(180px,260px);align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--divider-color,#e2e5e8)}.profile-conflict-row>span{display:grid;gap:3px}.profile-conflict-row label{display:grid;gap:3px;font-size:11px;font-weight:700;color:var(--secondary-text-color,#68727d)}.profile-conflict-row select{height:38px;margin:0;border-radius:7px}
      .physical-editor{margin-top:20px;padding:22px;background:var(--card-background-color,#fff);border-radius:20px}.physical-editor fieldset{border:0;padding:0;margin:0;min-width:0}.physical-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.physical-page{margin-top:20px;padding:18px;border:1px solid var(--divider-color,#ddd);border-radius:16px}.physical-key{display:grid;grid-template-columns:150px 160px minmax(180px,1fr) auto;gap:12px;align-items:center;padding:14px 0;border-bottom:1px solid var(--divider-color,#ddd)}.physical-key label{display:grid;gap:6px;font-size:12px}.physical-key input,.action-box input{width:100%;min-height:40px;padding:8px;background:var(--card-background-color,#fff);color:inherit;border:1px solid var(--divider-color,#ddd);border-radius:8px}.physical-status{padding:12px;background:var(--secondary-background-color,#eee);border-radius:10px;white-space:pre-wrap}@media(max-width:850px){.physical-key{grid-template-columns:1fr 1fr}.physical-toolbar button{height:auto;min-height:42px;padding:8px}.header-actions{flex-wrap:wrap}.layout-button{display:block!important}}
      @media(max-width:600px){.profile-conflict-row{grid-template-columns:1fr}}
      :host{display:block;min-height:100%;background:var(--primary-background-color,#f5f6f8);color:var(--primary-text-color,#17202a);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
      .apply-bar{flex-wrap:wrap}.apply-bar .profile-select{display:grid;gap:4px;min-width:min(100%,260px);font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.apply-bar .profile-select select{margin:0}.apply-bar>.small{flex:1 1 260px}
      *{box-sizing:border-box}button,select,textarea{font:inherit}main{max-width:1460px;margin:auto;padding:28px clamp(16px,3vw,44px) 64px}header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}h1{font-size:clamp(30px,4vw,48px);line-height:1;margin:5px 0 8px;letter-spacing:-.04em}header p{margin:0;color:var(--secondary-text-color,#68727d)}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.18em;color:var(--primary-color,#03a9f4)}.header-actions{display:flex;align-items:center;gap:10px}.battery,.live{height:40px;display:flex;align-items:center;gap:8px;padding:0 14px;border-radius:20px;background:var(--card-background-color,#fff);box-shadow:0 6px 18px #0000000a;font-weight:700}.live i{width:8px;height:8px;border-radius:50%;background:#26c281;box-shadow:0 0 0 5px #26c28122}.icon-button{width:40px;height:40px;border:0;border-radius:50%;background:var(--card-background-color,#fff);cursor:pointer;font-size:22px}.selectors{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;background:var(--card-background-color,#fff);padding:20px 22px;border-radius:20px;box-shadow:0 12px 40px #0000000a}.selectors label{font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}select{width:100%;height:44px;margin-top:7px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.identity{display:grid;align-content:center;min-width:150px;padding-top:2px}.identity span,.identity small{font-size:11px;color:var(--secondary-text-color,#68727d)}.identity code{font-weight:800;font-size:14px;margin:3px 0}.quick-bind{display:grid;grid-template-columns:1fr minmax(220px,320px);align-items:center;gap:16px;margin:18px 0;padding:18px 22px;background:color-mix(in srgb,var(--primary-color,#03a9f4) 8%,var(--card-background-color,#fff));border:1px solid color-mix(in srgb,var(--primary-color,#03a9f4) 24%,transparent);border-radius:16px}.quick-bind div{display:grid}.quick-bind span{font-size:12px;color:var(--secondary-text-color,#68727d);margin-top:3px}.quick-bind select{margin:0}.pages{display:flex;gap:8px;overflow:auto;margin:22px 0 16px;padding:5px}.pages button,.mode-tabs button{border:0;padding:10px 16px;border-radius:12px;background:transparent;color:var(--secondary-text-color,#68727d);font-weight:700;cursor:pointer;white-space:nowrap}.pages button.selected,.mode-tabs button.selected{background:var(--primary-color,#03a9f4);color:#fff;box-shadow:0 5px 14px color-mix(in srgb,var(--primary-color,#03a9f4) 30%,transparent)}.workspace{display:grid;grid-template-columns:minmax(340px,.9fr) minmax(400px,1.1fr);gap:26px;align-items:start}.remote-stage,.editor{background:var(--card-background-color,#fff);border-radius:24px;padding:26px 28px;box-shadow:0 14px 50px #0000000d}.remote-stage{display:grid;justify-items:center}.remote-shell{width:min(100%,420px);padding:18px;border-radius:42px;background:linear-gradient(145deg,#242a31,#0f1318);box-shadow:0 30px 55px #0005,inset 0 1px 1px #ffffff2b}.remote-top{height:62px;padding:4px 10px;color:#eaf0f4;display:flex;justify-content:space-between;align-items:center}.remote-top span{font-weight:800}.remote-top small{color:#8f9ba7}.screen{min-height:455px;padding:18px;border-radius:26px;background:linear-gradient(160deg,#edf2ed,#dce7df);color:#1f2924;box-shadow:inset 0 0 0 1px #ffffffaa,inset 0 8px 30px #8295891f}.screen-title{text-align:center;text-transform:uppercase;font-size:11px;letter-spacing:.16em;font-weight:900;color:#627168;margin-bottom:15px}.button-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.remote-button{position:relative;min-height:82px;padding:10px 5px 8px;border:1px solid #26392d14;border-radius:18px;background:#f7faf7;color:#27352d;display:grid;place-items:center;align-content:center;gap:4px;cursor:pointer;transition:transform .16s,box-shadow .16s,border-color .16s}.remote-button:hover{transform:translateY(-2px);box-shadow:0 8px 18px #354d3c1c}.remote-button.selected{border-color:#03a9f4;box-shadow:0 0 0 3px #03a9f429}.remote-button.pressed{animation:press .85s ease}.remote-button .glyph{font-size:23px;font-weight:500}.remote-button>span:not(.glyph){max-width:100%;font-size:9px;font-weight:800;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis}.remote-button i{position:absolute;top:8px;right:8px;width:7px;height:7px;border-radius:50%}.remote-button.preset i,.legend i.preset{background:#3c8cff}.remote-button.custom i,.legend i.custom{background:#25bd76}.remote-button.disabled i,.legend i.disabled{background:#ee5b66}.remote-button.none i,.legend i.none{background:#9aa4ad}.remote-footer{height:54px;display:flex;align-items:center;justify-content:center;gap:8px}.remote-footer span{width:5px;height:5px;border-radius:50%;background:#ffffff40}.legend{display:flex;flex-wrap:wrap;justify-content:center;gap:16px;margin-top:22px;color:var(--secondary-text-color,#68727d);font-size:11px}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:8px;height:8px;border-radius:50%}.editor{min-height:570px}.editor-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.editor h2{font-size:28px;margin:8px 0 2px;letter-spacing:-.025em}.status-pill{display:inline-flex;border-radius:10px;padding:5px 9px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.09em}.status-pill.preset{background:#3c8cff1c;color:#2373de}.status-pill.custom{background:#25bd761c;color:#15965a}.status-pill.disabled{background:#ee5b661c;color:#d93f4b}.status-pill.none{background:#9aa4ad22;color:#69747d}dl{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:20px 0;border:1px solid var(--divider-color,#e2e5e8);border-radius:14px;overflow:hidden}dl div{padding:12px 14px;border-bottom:1px solid var(--divider-color,#e2e5e8)}dl div:nth-last-child(-n+2){border-bottom:0}dt{font-size:10px;text-transform:uppercase;color:var(--secondary-text-color,#68727d);letter-spacing:.08em}dd{margin:4px 0 0;font-weight:700}.mode-tabs{display:flex;gap:4px;padding:4px;background:var(--secondary-background-color,#f1f3f5);border-radius:14px}.mode-tabs button{flex:1;font-size:12px;padding:10px}.mode-content{min-height:215px;margin-top:16px}.explanation{display:grid;gap:6px;padding:20px;border-radius:16px;background:#3c8cff12;border:1px solid #3c8cff33}.explanation span,.action-title span,.json-help{font-size:12px;color:var(--secondary-text-color,#68727d)}.explanation.danger{background:#ee5b6610;border-color:#ee5b6633}.action-box{display:grid;gap:14px}.action-title{display:flex;justify-content:space-between}#visualActionEditor{min-height:70px}.link-button{border:0;padding:0;background:none;color:var(--primary-color,#03a9f4);font-weight:800;cursor:pointer;text-decoration:underline}details{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px}summary{cursor:pointer;font-size:12px;color:var(--secondary-text-color,#68727d)}textarea{width:100%;min-height:160px;margin-top:10px;padding:12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--code-editor-background-color,#111820);color:var(--code-editor-text-color,#dce8ef);font:12px/1.5 ui-monospace,monospace;resize:vertical}textarea.invalid{border-color:#e74c3c;box-shadow:0 0 0 2px #e74c3c33}.primary,.secondary{height:42px;padding:0 18px;border:1px solid transparent;border-radius:12px;font-weight:700;white-space:nowrap;cursor:pointer;transition:background .15s,box-shadow .15s,transform .12s,border-color .15s}
      .primary{background:var(--primary-color,#03a9f4);color:#fff}
      .primary:hover:not(:disabled){transform:translateY(-1px);box-shadow:0 8px 20px color-mix(in srgb,var(--primary-color,#03a9f4) 38%,transparent)}
      .secondary{background:var(--secondary-background-color,#edf0f3);color:var(--primary-text-color,#17202a)}
      .secondary:hover:not(:disabled){background:var(--card-background-color,#fff);border-color:#c7ced6;box-shadow:0 5px 14px #00000014}
      .secondary.compact{height:36px;padding:0 14px;font-size:13px}
      .primary:focus-visible,.secondary:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}
      .primary:disabled,.secondary:disabled{opacity:.45;cursor:default;transform:none;box-shadow:none}
      /* Removing something is never the same shape as adding it. */
      .secondary.destructive{color:#d33b47;background:#fdf2f3}
      .secondary.destructive:hover:not(:disabled){background:#fbe8ea;border-color:#e4939b}.error,.loading,.empty{padding:22px;border-radius:16px;background:var(--card-background-color,#fff);margin:16px 0}.error{background:#ee5b6613;color:#d73a46}.loading{display:flex;gap:10px;align-items:center}.loading span{width:14px;height:14px;border:2px solid #ccc;border-top-color:var(--primary-color,#03a9f4);border-radius:50%;animation:spin .7s linear infinite}.empty{text-align:center;color:var(--secondary-text-color,#68727d);line-height:1.7}.empty.small{margin:120px 0}.device-table{margin:10px 0}.device-table table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}.device-table th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--secondary-text-color,#68727d);padding:4px 6px}.device-table td{padding:4px 6px;border-top:1px solid var(--divider-color,#e2e5e8)}.device-table .small{font-size:11px;color:var(--secondary-text-color,#68727d);margin:4px 0}.device-table .warning{color:#d73a46}.toolbar{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0 4px}
      .action{display:inline-flex;align-items:center;gap:9px;height:42px;padding:0 16px;white-space:nowrap;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#17202a);font-weight:700;cursor:pointer;transition:border-color .15s,background .15s,transform .12s,box-shadow .15s}
      .action .g{font-size:16px;line-height:1;opacity:.75}
      .action:hover{transform:translateY(-1px);box-shadow:0 6px 16px #0000001a;border-color:#c7ced6}
      .action:active{transform:none}
      .action:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}
      .action:disabled{opacity:.45;cursor:default;transform:none;box-shadow:none}
      /* Weight where it matters: the one that creates, and the one that cannot be undone. */
      .action.accent{background:var(--primary-color,#03a9f4);border-color:transparent;color:#fff}
      .action.accent .g{opacity:1}
      .action.accent:hover{box-shadow:0 8px 20px color-mix(in srgb,var(--primary-color,#03a9f4) 38%,transparent)}
      .action.danger{color:#d33b47;border-color:#f0c2c6}
      /* One look for every text field and its caption, wherever a form appears. */
      .small{font-size:12px;line-height:1.5;color:var(--secondary-text-color,#68727d)}
      .form-stack{display:grid;gap:22px}
      .field{display:grid;gap:8px;min-width:0;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}
      .field-label{font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}
      .field input,.matter-captions input{width:100%;height:42px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:10px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#17202a);font:inherit;font-weight:500}
      .field input:focus-visible,.matter-captions input:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:1px;border-color:transparent}
      .matter-captions{display:grid;grid-template-columns:repeat(auto-fit,minmax(200px,1fr));gap:14px 12px;margin:12px 0}
      .matter-captions label{display:grid;gap:6px;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}
      .matter-captions label small{font-weight:500;font-size:11px;font-variant-numeric:tabular-nums}
      .matter-captions>.small{grid-column:1/-1;margin:0}
      .appearance-editor .matter-captions{margin:0}
      .device-table .drag-handle{cursor:grab;touch-action:none;user-select:none;text-align:center;width:24px;color:var(--secondary-text-color,#68727d)}
      .device-table tr.dragging{opacity:.6;background:color-mix(in srgb,var(--primary-color,#03a9f4) 12%,transparent)}
      .device-table .row-actions{white-space:nowrap}
      .matter-interval{display:flex;flex-wrap:wrap;align-items:center;gap:8px;white-space:nowrap;font-size:12px;font-weight:700}
      .matter-interval input{width:84px;height:36px;padding:0 10px;border:1px solid var(--divider-color,#dfe3e8);border-radius:10px;background:var(--card-background-color,#fff);color:inherit;font:inherit}
      .matter-interval small{flex-basis:100%;white-space:normal;font-weight:500;font-size:11px;color:var(--secondary-text-color,#68727d)}
      /* The three read-only panels are a group of cards, not stray rows of text. */
      details.device-table{margin:8px 0;padding:12px 16px;border:1px solid var(--divider-color,#e2e5e8);border-radius:14px;background:var(--card-background-color,#fff)}
      details.device-table>summary{font-size:13px;font-weight:600;color:var(--primary-text-color,#17202a)}
      details.device-table[open]>summary{margin-bottom:10px}
      .action.danger:hover{background:#fdf2f3;border-color:#e4939b}.reachability{margin:10px 0;padding:10px 14px;border-radius:12px;font-size:13px;background:var(--secondary-background-color,#f1f3f5)}.reachability.full{background:#25bd7614}.reachability.conditional{background:#f0a52014}.reachability.none{background:#ee5b6614}.apply-bar{display:flex;align-items:center;gap:12px;margin:18px 0;padding:14px 18px;border-radius:14px;background:var(--card-background-color,#fff);box-shadow:0 6px 18px #0000000a;font-size:13px}.apply-bar.dirty{background:color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff));border:1px solid color-mix(in srgb,var(--primary-color,#03a9f4) 28%,transparent)}.apply-bar .spacer{flex:1}.key-editor{display:grid;gap:14px;margin:20px 0;padding:18px 20px;border-radius:16px;background:var(--secondary-background-color,#f1f3f5)}.key-editor label{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.key-editor select{margin:0}.key-editor textarea{min-height:70px;margin-top:4px}.key-editor details.catalog{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px;display:grid;gap:10px}.key-editor details.catalog>summary{font-weight:700}.key-editor input[type=search]{height:40px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.key-editor select[size]{height:auto;padding:4px}.key-editor .warning{color:#d73a46}.add-remote{display:grid;gap:12px;margin:14px 0;padding:18px;border-radius:18px;background:var(--card-background-color,#fff);box-shadow:0 12px 40px #0000000a}.add-remote label{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.add-remote label.inline{display:flex;align-items:center;gap:8px}.add-remote select{margin:0}.add-remote select[size]{height:auto;padding:4px}.add-remote input[type=text],.add-remote input[type=search]{height:44px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.add-remote .mode-tabs button:disabled{opacity:.4;cursor:default}.add-remote .small{margin:0}.add-remote .warning{color:#d73a46}.diagnostics code{font:11px/1.5 ui-monospace,monospace}.diagnostics table{margin-top:10px}.key-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:2px}.stage-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:center;margin-top:18px}@keyframes spin{to{transform:rotate(360deg)}}@keyframes press{0%,100%{transform:scale(1)}20%{transform:scale(.9);background:#c9f6dc;box-shadow:0 0 0 7px #25bd7630}}
      .device-wrap{width:min(100%,360px)}
      .device{width:100%;height:auto;filter:drop-shadow(0 14px 26px #0000002b)}
      .device .shell{stroke:#d2d5da;stroke-width:1.2}
      .device .glass{fill:#090a0c}
      .device .glass-edge{fill:none;stroke:#ffffff29;stroke-width:1.2;stroke-linecap:round}
      /* The list is a window onto the device's own display: a plain rectangle below the glass
         curve, so rows slide out at its edges instead of running under the rounded top. */
      .scr-scroll{height:198px;overflow-y:auto;overscroll-behavior:contain;touch-action:pan-y;
        -webkit-overflow-scrolling:touch;padding:8px 13px 14px;scrollbar-width:thin;
        -webkit-mask-image:linear-gradient(to bottom,transparent 0,#000 8px,#000 calc(100% - 14px),transparent 100%);
        mask-image:linear-gradient(to bottom,transparent 0,#000 8px,#000 calc(100% - 14px),transparent 100%);
        scrollbar-color:#ffffff40 transparent;font:600 12px/1.2 system-ui,sans-serif;color:#fff}
      .scr-scroll::-webkit-scrollbar{width:4px}
      .scr-scroll::-webkit-scrollbar-thumb{background:#ffffff40;border-radius:2px}
      .scr-empty{color:#ffffff66;font-weight:500;text-align:center;margin:60px 0}
      .scr-row{display:flex;align-items:center;gap:4px;min-height:30px;border-radius:5px;margin-bottom:3px}
      .scr-row.on{background:#ffffff1f}
      .scr-row>.k{flex:1;display:flex;align-items:center;gap:9px;padding:6px 7px;cursor:pointer;
        border-radius:5px;min-width:0;pointer-events:auto}
      .scr-row>.pick-remote{border:0;background:transparent;color:inherit;text-align:left;font-weight:inherit}
      .pick-remote>*{pointer-events:none}
      .scr-row>.k:hover{background:#ffffff14}
      .scr-row>.k:focus-visible{outline:2px solid #03a9f4;outline-offset:-2px}
      .scr-row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .scr-row .pos{font-size:10px;font-weight:800;color:#ffffff7a;min-width:28px}
      .native-glyph{display:block;width:24px;height:24px;object-fit:contain;flex:none}
      .glyph-picker{margin:14px 0;padding:12px 14px;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px}
      .page-editor{display:grid;gap:18px}
      .page-heading{display:flex;align-items:center;flex-wrap:wrap;gap:8px 14px;margin:8px 0 4px}
      .page-heading h2{margin:0;overflow-wrap:anywhere}
      .page-kicker{font-size:12px;color:var(--secondary-text-color,#68727d)}
      .page-tools{display:flex;align-items:center;flex-wrap:wrap;gap:10px;padding:16px;border:1px solid var(--divider-color,#dfe3e8);border-radius:14px}
      .page-tools .page-move{display:grid;gap:4px;font-size:12px;color:var(--secondary-text-color,#68727d)}
      .page-tools select{margin:0;min-width:140px}
      .page-editor-tabs{margin-bottom:4px}
      .glyph-picker summary{cursor:pointer;line-height:32px}
      .glyph-picker summary .native-glyph{display:inline-block;vertical-align:middle;margin:0 8px 0 5px;padding:4px;background:#171c23;border-radius:6px}
      .glyph-picker[open] summary{margin-bottom:10px}
      .glyph-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,104px),1fr));gap:8px;max-height:320px;overflow:auto;margin-top:10px;padding:2px}
      .glyph-grid button{display:grid;justify-items:center;align-content:start;gap:6px;min-height:66px;padding:8px 6px;background:#171c23;color:#eaf0f4;border:1px solid #657181;border-radius:7px;cursor:pointer}
      .glyph-grid button span{font-size:12px;line-height:1.25;overflow-wrap:anywhere}
      .glyph-grid button:hover{background:#273445}
      .glyph-grid button[aria-pressed="true"],.glyph-grid button:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:-2px}
      .scr-row .scr-icon{width:20px;height:20px}
      .scr-row.custom .nm{color:#8df0bd}.scr-row.disabled .nm{color:#ff9aa2}
      .scr-row.on .nm{color:#fff}
      .scr-row.unsaved{outline:1px dashed #ffffff80;outline-offset:-1px}
      .remote-button.unsaved{border-style:dashed}
      .remote-button.none i{display:none}
      .legend i.unsaved{width:12px;border:1px dashed currentColor;border-radius:3px}
      .scr-scroll .ic-img{width:18px;height:18px;flex:none;object-fit:contain}
      .scr-row>.ic-btn{flex:0 0 26px;width:26px;height:26px;padding:0;justify-content:center;
        margin-right:4px;border:0;border-radius:5px;
        background:#ffffff26;color:#fff;font-size:13px;line-height:1;cursor:pointer}
      .ic-btn:hover{background:#ffffff3d}
      .device .scr-sep path{stroke:#ffffff4d;stroke-width:1;fill:none}
      .device .cap{fill:#f7f7f9;stroke:#dadddf;stroke-width:1}
      .device .cap.ring{fill:#f4f4f7}
      .device .cap.seg{fill:#f4f4f7;stroke:#e6e6ea;stroke-linejoin:round}
      .device text.cap-t{fill:#30343a;font:700 11px/1 system-ui,sans-serif;text-anchor:middle}
      .device .mark{fill:none;stroke:#41464d;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
      .device .logo{stroke:#a00;stroke-width:1}.device .logo-mark{fill:#fff;stroke:none}
      /* One rule for every key: the state colours the outline, never the glyph. */
      .device .k{cursor:pointer;transition:opacity .15s}
      .device .k:hover .cap{stroke:#03a9f4;stroke-width:2}
      .device .k:focus-visible{outline:none}
      .device .k:focus-visible .cap{stroke:#03a9f4;stroke-width:2.5}
      .device .k.ghost{cursor:default;opacity:.35}
      .page-note{margin:-6px 0 12px;color:var(--secondary-text-color,#68727d)}
      .device .k.link .cap{fill:#f3f7ff;stroke:#c9d9f5;stroke-dasharray:3 3}
      .device .link-mark{stroke:#6b8cc7;stroke-width:2}
      .battery-icon{position:relative;display:flex;align-items:stretch;width:21px;height:12px;
        flex:none;border:1.5px solid currentColor;border-radius:3px;padding:1.5px;margin-right:3px}
      .battery-icon::after{content:"";position:absolute;left:calc(100% + 1px);top:50%;
        transform:translateY(-50%);width:2px;height:5px;border-radius:0 1px 1px 0;background:currentColor}
      .battery-fill{display:block;background:currentColor;border-radius:1px}
      .device .k.preset .cap{stroke:#3c8cff;stroke-width:2;fill:#f0f6ff}
      .device .k.custom .cap{stroke:#25bd76;stroke-width:2;fill:#eefaf3}
      .device .k.disabled .cap{stroke:#ee5b66;stroke-width:2;fill:#fff2f3}
      .device .k.selected .cap{stroke:#03a9f4;stroke-width:3;fill:#e6f5fe}
      .device .k.pressed .cap{animation:keypress .85s ease}
      .device .screen-softkeys .k .cap{fill:#18191b;stroke:#ffffff38;stroke-dasharray:none}
      .device .screen-softkeys .cap-t{fill:#ddd;font-size:9px}
      .device .screen-softkeys .k.custom .cap{stroke:#25bd76}
      .device .screen-softkeys .k.preset .cap{stroke:#3c8cff}
      .device .screen-softkeys .k.disabled .cap{stroke:#ee5b66}
      .device .screen-softkeys .k:hover .cap,.device .screen-softkeys .k:focus-visible .cap,
      .device .screen-softkeys .k.selected .cap,.device .screen-softkeys .k.current-page .cap{stroke:#8bd4ff}
      .device .k.unsaved .cap{stroke-dasharray:3 2}
      @keyframes keypress{0%,100%{fill:#f7f7f9}20%{fill:#c9f6dc}}
      .stage-actions{width:100%;justify-content:flex-start}.page-move{display:flex;align-items:center;gap:7px;margin-left:auto;color:var(--secondary-text-color,#68727d);font-size:12px;font-weight:700}.page-move select{width:auto;min-width:125px;height:36px;margin:0;border-radius:7px}.page-capacity{margin-left:auto}
      .remote-capacity{display:flex;align-items:center;flex-wrap:wrap;gap:8px 16px;margin:4px 0 14px;color:var(--secondary-text-color,#68727d);font-size:13px}
      .remote-capacity b{color:var(--primary-text-color,#212121)}
      .studio-save{display:flex;justify-content:flex-end;align-items:center;flex-wrap:wrap;gap:12px;margin-top:20px;padding-top:16px;border-top:1px solid var(--divider-color,#dfe3e8)}
      .studio-save span{color:var(--secondary-text-color,#68727d);font-size:13px}
      #selectOptionWarning:empty{display:none}
      .row-tools{margin-top:12px}
      @media(max-width:900px){.workspace{grid-template-columns:1fr}.device-wrap{margin:auto}}
      @media(max-width:430px){header{align-items:center}.live{padding:0 10px}.device-wrap{width:100%}
      .button-grid{gap:7px}.remote-button{min-height:72px;border-radius:15px}dl{grid-template-columns:1fr}
      dl div:nth-last-child(2){border-bottom:1px solid var(--divider-color,#e2e5e8)}}`;
  }
}

// Home Assistant can evaluate this module more than once — navigating back to the panel, or a
// version change that leaves an earlier copy registered. A second define() throws, and because
// that happens while the module is still being evaluated nothing below it runs and the panel
// stays blank, with no chance for the render-time error handler to report anything.
if (!customElements.get("switchbot-urc-panel")) {
  customElements.define("switchbot-urc-panel", SwitchBotUrcPanel);
}
