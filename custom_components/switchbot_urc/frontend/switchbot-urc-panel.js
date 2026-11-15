const DOMAIN = "switchbot_urc";
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
  pool: "Pool", ventilator: "Fan",
};
const HID_PROFILE_ARTWORK = {
  APPLE_TV: "1d", FIRE_TV: "1e", UNIVERSAL_BLE: "20", GOOGLE_TV: "1f",
};
const IR_PROFILE_ARTWORK = {
  1: "1a", 2: "18", 3: "19", 4: "0f", 5: "05", 6: "09", 7: "0e",
  8: "08", 9: "00", 10: "06", 11: "01", 12: "0a", 13: "10", 14: "0c",
};
const NATIVE_GLYPH_FUNCTIONS = new Set([
  0x0000, 0x0001, 0x0002, 0x0003, 0x0004, 0x0005, 0x0006, 0x000c, 0x000d, 0x000f,
  0x0010, 0x0011, 0x0012, 0x0013, 0x0014, 0x0015, 0x0016, 0x0017, 0x0018, 0x0019,
  0x001a, 0x001b, 0x001c, 0x001e, 0x001f, 0x0020, 0x0021, 0x0027, 0x0028, 0x0029,
  0x002a, 0x002b, 0x002c, 0x002d, 0x002e, 0x002f, 0x0030, 0x0031, 0x0032, 0x0033,
  0x0034, 0x0035, 0x0036, 0x0037, 0x0038, 0x0039, 0x003a, 0x003b, 0x003c, 0x003d,
  0x003e, 0x0046, 0x0047, 0x0048, 0x0049, 0x004a, 0x004b, 0x004c, 0x004d, 0x004e,
  0x0050, 0x0051, 0x0052, 0x0053, 0x0054, 0x0055, 0x0059, 0x005a, 0x005b, 0x005c,
  0x005e, 0x0064, 0x0065, 0x0066, 0x0067, 0x0068, 0x0069, 0x006a, 0x006b, 0x006c,
  0x006d, 0x006e, 0x006f, 0x0070, 0x0071, 0x0072, 0x0073, 0x0074, 0x0075, 0x0076,
  0x0077, 0x0078, 0x0079, 0x007a, 0x007b, 0x007c, 0x007d, 0x007e, 0x007f, 0x0080,
  0x0081, 0x0082, 0x0083, 0x0084, 0x0085, 0x0086, 0x0087, 0x0088, 0x0089, 0x008a,
  0x008b, 0x008c, 0x008d, 0x008e, 0x008f, 0x0090, 0x0091, 0x0092, 0x0093, 0x0094,
  0x0095, 0x0096, 0x0097, 0x0098, 0x0099, 0x009a, 0x00c8, 0x00c9, 0x00ca, 0x00cb,
  0x00d2, 0x00d3, 0x00d4, 0x00d5, 0x00d6, 0x00dc, 0x00dd, 0x00de, 0x00df, 0x00e0,
  0x012c, 0x012d, 0x012e, 0x012f, 0x0137, 0x0138, 0x0139, 0x013a, 0x013b, 0x013c,
  0x013d, 0x013e, 0x0140, 0x0141, 0x0142, 0x0143, 0x014a, 0x014b, 0x014c, 0x014d,
  0x014e, 0x014f, 0x0150, 0x0151, 0x0152, 0x0153, 0x0154, 0x0155, 0x0156, 0x0157,
  0x0158, 0x0159, 0x02bc, 0x0320, 0x0321, 0x0322, 0x0384, 0x0385, 0x0387, 0x0388,
  0x0389, 0x038a, 0x038b, 0x038c, 0x038d, 0x038e, 0x038f, 0x0390, 0x0391, 0x0392,
  0x0393, 0x0394, 0x0395, 0x0396, 0x05dc, 0x0640, 0x06a4, 0x07d0, 0x07d1, 0x07d2,
  0x07d3, 0x0834, 0x0835, 0x0836, 0x0837, 0x0838, 0x0839,
]);

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
    this._mode = "preset";
    this._draftActions = [];
    this._activeButton = null;
    this._activeEntryId = null;
    this._activeRemoteId = null;
    this._loading = false;
    this._error = null;
    this._dirty = false;
    this._jsonValid = true;
    this._physical = null;
    this._nativeProfiles = [];
    this._physicalOrigins = {};
    this._lastIdentityMigrations = [];
    this._physicalSources = [];
    // Catalog picker state. `available` stays null until the first lookup answers, so the
    // picker can say "loading" once instead of asking on every render.
    this._catalog = { available: null, types: [], remoteType: 2, brands: [], brand: "",
                      models: [], hxd: "", buttons: [], busy: "", error: "" };
    // Add-remote dialog: null when closed, otherwise the half-filled form.
    this._add = null;
    this._sources = null;
    // Which remote's tile is being edited on the screen, and the icon picked for it but
    // not yet written.
    this._iconPickerFor = null;
    this._iconDraft = null;
    this._tileNameDraft = null;
    this._physicalStatus = "";
    this._physicalBusy = false;
  }

  set hass(value) {
    this._hass = value;
    if (this._actionSelectorEl) this._actionSelectorEl.hass = value;
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
    this._physicalBusy = true;
    this._render();
    let adopted = 0;
    let dropped = 0;
    let importError = null;
    let readback = null;
    try {
      const result = await this._hass.callWS({
        type: `${DOMAIN}/studio/physical/import`, entry_id: this._entryId,
        ...(this._remoteId ? { remote_id: this._remoteId } : {}) });
      adopted = result?.imported || 0;
      dropped = result?.dropped || 0;
      importError = result?.appearance_error;
      readback = result?.native_readback;
    } catch (error) { importError = error?.message || String(error); }
    this._physical = null;
    this._physicalFor = null;
    this._physicalBusy = false;
    await this._load();
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

  async _load() {
    this._loading = true;
    this._error = null;
    this._render();
    try {
      this._data = await this._hass.callWS({ type: `${DOMAIN}/studio/get` });
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
      this._physicalStatus = "This page has no room for another row.";
      this._render();
      return;
    }
    page.buttons.push({
      index: free,
      transport: kind === "native" ? "native" : kind === "hid" ? "hid" : "ir",
      function: kind === "native" ? 5 : 115,
      code_hex: "",
    });
    this._buttonId = `p${page.index}_k${free}`;
    this._render();
  }

  _pageKeyEntries(page) {
    return [...(page?.buttons || [])].sort((a, b) => a.index - b.index).map((key) => ({
      key,
      origin: this._physicalOrigins[`p${page.index}_k${key.index}`]
        || `p${page.index}_k${key.index}`,
    }));
  }

  _replacePageKeyOrder(page, entries) {
    for (const key of page.buttons) delete this._physicalOrigins[`p${page.index}_k${key.index}`];
    page.buttons = entries.map(({ key, origin }, index) => {
      key.index = index;
      this._physicalOrigins[`p${page.index}_k${index}`] = origin;
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
    this._replacePageKeyOrder(page, entries);
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
    const original = this._physicalOrigins[current] || current;
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
            if (linkedPositions.has(index)) return false;
            if (this._physical.kind !== "native") return true;
            return nativeProfile?.main_positions?.includes(index);
          }) : [];
        const physicalKeys = page.index === 0
          ? visibleMainPositions.map((index) => page.buttons.find((item) => item.index === index)
            || { index }) : page.buttons;
        const buttons = physicalKeys.map((key) => {
          const currentId = `p${page.index}_k${key.index}`;
          const identity = this._physicalOrigins[currentId] || currentId;
          const source = remotePages.flatMap((item) => item.buttons || [])
            .find((item) => item.button_id === identity);
          const profileKey = page.index === 0
            ? nativeProfile?.main_keys?.find((item) => item.index === key.index) : null;
          const functionLabel = this._profileFunctionLabel(key.function);
          return {
            ...source,
            button_id: identity,
            button_page: page.index,
            button_index: key.index,
            button_function: key.function ?? source?.button_function ?? profileKey?.function ?? 0,
            button_glyph: key.glyph,
            default_function: source?.default_function ?? profileKey?.function,
            can_add_command: this._physical.kind !== "native" || !!profileKey?.actionable
              || (page.index === 0 && key.index < 4 && !profileKey),
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
    if (!this._remote()?.layout_editable) return;
    // Track the attempt, not its result. Keying this on `_physical` meant that a remote whose
    // layout cannot be loaded was retried from inside every render, and since the request ends
    // in another render that was an endless loop that took the whole panel down.
    const token = `${this._entryId}:${this._remoteId}`;
    if (this._physicalFor === token) return;
    this._physicalFor = token;
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
      this._iconPickerFor = null;
      this._iconDraft = null;
      this._tileNameDraft = null;
    }
    // A position with no function yet becomes one as soon as it is picked, using the meaning the
    // position already carries. No dialogue: the choice was made by clicking it.
    const draft = button ? this._draftKey(button) : null;
    if (draft && !draft.key.function && button.default_function) {
      draft.key.function = button.default_function;
    }
    this._draftActions = structuredClone(button?.actions || []);
    this._dirty = false;
    this._jsonValid = true;
    this._mode = button?.has_override
      ? button.actions.length
        ? "actions"
        : "disabled"
      : "preset";
    if (rerender) this._render();
  }

  _handleLiveEvent(event) {
    if (this._physical) return;
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
      if (this._dirty) {
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
    if (!Number.isInteger(functionCode) || !NATIVE_GLYPH_FUNCTIONS.has(functionCode)) return "";
    return `/switchbot_urc_static/native-glyphs/keyfun-${functionCode.toString(16).padStart(4, "0")}.png`;
  }

  _nativeGlyph(button, className = "") {
    const src = this._nativeGlyphSrc(button);
    return src ? `<img class="native-glyph ${className}" src="${src}" alt="" aria-hidden="true">` : "";
  }

  _renderGlyphPicker(owner, field, label, defaultFunction) {
    const selected = owner[field];
    const preview = this._nativeGlyph({ button_glyph: selected, button_function: defaultFunction });
    return `<details class="glyph-picker">
      <summary>${preview}<b>${label}</b></summary>
      <button class="secondary compact" data-glyph-field="${field}" data-glyph-code=""
        ${selected === undefined ? "disabled" : ""}>Reset to default</button>
      <div class="glyph-grid" role="group" aria-label="${label}">
        ${[...NATIVE_GLYPH_FUNCTIONS].map((code) => {
          const name = `Icon 0x${code.toString(16).padStart(4, "0")}`;
          return `<button type="button" data-glyph-field="${field}" data-glyph-code="${code}"
            aria-label="${escapeHtml(name)}" title="${escapeHtml(name)}" aria-pressed="${code === (selected ?? defaultFunction)}">
            ${this._nativeGlyph({ button_function: code })}</button>`;
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
    return this._renderGlyphPicker(owner, "link_glyph", "Menu icon", defaultFunction);
  }

  _renderMenuNames(page, button) {
    if (!page?.index || !this._physical) return "";
    const menu = this._physical.pages.find((item) => item.index === page.index);
    if (!menu) return "";
    const row = button ? this._draftKey(button)?.key : null;
    const hasDraft = this._physicalChanges();
    const field = (label, title, placeholder, rowIndex) => `<form class="menu-name-form"
      data-name-key="${escapeHtml(`${this._entryId}:${this._remoteId}:${page.index}:${rowIndex ?? "menu"}`)}"
      data-menu-name data-page="${page.index}" ${rowIndex == null ? "" : `data-row="${rowIndex}"`}>
      <label>${label}<input name="title" value="${escapeHtml(title || "")}"
        placeholder="${escapeHtml(placeholder)}" maxlength="60"></label>
      <button class="secondary compact" type="submit" ${this._physicalBusy ? "disabled" : ""}>
        ${hasDraft ? "Keep in draft" : "Save name"}</button>
    </form>`;
    return `<section class="menu-names">
      <p class="small">Names are displayed in Remote Studio.</p>
      ${field("Menu name", menu.title, `Page ${"ABCD"[page.index - 1]}`)}
      ${row ? field("Selected item name", row.title, "Default name", row.index) : ""}
    </section>`;
  }

  _iconImage(name) {
    const asset = APP_ICON_ASSETS[name] || APP_ICON_ASSETS.light;
    return `<img class="ic-img" src="/switchbot_urc_static/app-icons/${asset}.webp"
      alt="" aria-hidden="true">`;
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
    const searchAttribute = dataAttribute === "native-profile"
      ? "data-native-type-search-edit" : "data-native-type-search-add";
    const searchId = dataAttribute === "native-profile" ? "nativeTypeSearchEdit" : "nativeTypeSearchAdd";
    const filter = String(this._nativeTypeSearch || "").trim().toLowerCase();
    const visible = filter ? profiles.filter((item) =>
      `${item.title} ${item.value} ${item.profile} ${item.control_mode}`.toLowerCase().includes(filter)) : profiles;
    return `<label class="native-type-search">Filter types<input id="${searchId}" type="search" ${searchAttribute}
      value="${escapeHtml(this._nativeTypeSearch || "")}" placeholder="Search type or screen mode"></label>
      <div class="native-type-grid">${visible.map((item) => {
      const artwork = this._nativeArtworkSrc(item);
      const detail = (item.label || "").split(" · ").slice(1).join(" · ");
      const active = item.value === selected || item.equivalent_types?.includes(selected);
      return `<button class="native-type-choice${active ? " selected" : ""}"
        type="button" data-${dataAttribute}="${escapeHtml(item.value)}"
        aria-pressed="${!!active}">
        <span class="native-type-art">${artwork
          ? `<img src="${artwork}" alt="">` : '<span title="Artwork not verified">—</span>'}</span>
        <span>${escapeHtml(item.title || item.value)}</span>
        ${detail ? `<span class="native-type-detail">${escapeHtml(detail)}</span>` : ""}
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

  async _saveTile() {
    // Native icons rewrite their saved page records in place; other remote types use their
    // existing rebuild path. Rename is a separate metadata command when both fields changed.
    const remote = this._remote();
    if (!remote) return;
    const input = this.shadowRoot.querySelector("[data-rename-input]");
    const name = (this._tileNameDraft ?? input?.value ?? "").trim();
    const icon = this._iconDraft ?? remote.icon;
    const renamed = name && name !== remote.name;
    const reiconed = icon !== remote.icon;
    if (this._physicalChanges()) {
      this._error = "Save the screen layout before changing the name or icon.";
      this._render();
      return;
    }
    if (!renamed && !reiconed) {
      this._iconPickerFor = null;
      this._iconDraft = null;
      this._tileNameDraft = null;
      this._render();
      return;
    }
    if (!name) {
      this._error = "Give the remote a name.";
      this._render();
      return;
    }
    this._physicalBusy = true;
    this._render();
    try {
      let result = null;
      if (reiconed && remote.can_test_native_icon) {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/update_native_icon`,
          entry_id: this._entryId, remote_id: this._remoteId, icon });
        if (renamed) {
          result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/rename`,
            entry_id: this._entryId, remote_id: this._remoteId, name });
        }
      } else if (reiconed) {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/recreate`,
          entry_id: this._entryId, remote_id: this._remoteId, icon, name });
      } else {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/rename`,
          entry_id: this._entryId, remote_id: this._remoteId, name });
      }
      this._notify(result?.warning
        || (reiconed && renamed ? `Saved as "${name}" with the ${icon} icon`
          : reiconed ? `Icon changed to ${icon}` : `Renamed to ${name}`));
      this._iconPickerFor = null;
      this._iconDraft = null;
      this._tileNameDraft = null;
      this._physical = null;
      this._physicalFor = null;
      this._error = null;
    } catch (error) { this._error = error?.message || String(error); }
    finally { this._physicalBusy = false; await this._load(); }
  }

  _renderScreen(page) {
    // Real HTML inside the SVG screen, so the list scrolls like the device's own does instead
    // of silently cutting off whatever does not fit.
    if ((page?.index ?? 0) !== 0) {
      const keys = page?.buttons || [];
      if (!keys.length) {
        return `<p class="scr-empty">This page has no buttons yet</p>`;
      }
      return keys.map((item) => {
        const [status] = this._status(item);
        const on = item.button_id === this._buttonId;
        const draft = this._draftLabel(item);
        const glyph = this._nativeGlyph(item, "scr-icon");
        return `<div class="scr-row k ${status}${on ? " on" : ""}${draft ? " unsaved" : ""}" role="button" tabindex="0"
          data-button="${escapeHtml(item.button_id)}" title="${escapeHtml(item.label)}${draft ? ` · ${draft} in draft` : ""}">
          ${glyph}
          <span class="pos">${escapeHtml(item.position || `#${item.button_index + 1}`)}</span>
          <span class="nm">${escapeHtml(item.label)}</span></div>`;
      }).join("");
    }
    const remotes = this._entry()?.remotes || [];
    if (!remotes.length) return `<p class="scr-empty">No remotes yet</p>`;
    return remotes.map((item) => {
      const current = item.remote_id === this._remoteId;
      const nativeProfile = item.can_test_native_icon
        ? this._nativeProfile(item.native_type || item.device_type) : null;
      const artwork = item.can_test_native_icon
        ? this._nativeArtworkSrc(nativeProfile, item.artwork_id)
        : this._hidArtworkSrc(item.device_type, item.artwork_id) || this._irArtworkSrc(item);
      return `<div class="scr-row${current ? " on" : ""}">
        <button class="k pick-remote" type="button"
          data-remote="${escapeHtml(item.remote_id)}"
          title="${escapeHtml(item.name)} · ${escapeHtml(item.device_type)}">
          ${artwork ? `<img class="ic-img" src="${artwork}" alt="">`
            : item.can_test_native_icon ? `<span class="ic-fallback" aria-hidden="true">▣</span>`
              : this._iconImage(item.icon)}<span class="nm">${escapeHtml(item.name)}</span></button>
        ${current ? `<button class="k ic-btn" data-icon-for="${escapeHtml(item.remote_id)}"
          title="Edit this remote's name and appearance">✎</button>` : ""}
      </div>`;
    }).join("");
  }

  _renderAppearance(remote) {
    const isNative = !!remote.can_test_native_icon;
    const native = this._physical?.kind === "native";
    const isHid = remote.device_type in HID_PROFILE_ARTWORK;
    const isIr = String(remote.device_type).startsWith("IR_");
    const firmwareArtwork = isNative || isHid || isIr;
    const profile = native
      ? this._nativeProfile(this._physical.native_type || this._physical.template) : null;
    const editing = this._iconPickerFor === remote.remote_id;
    const pickedIcon = editing ? this._iconDraft ?? remote.icon : remote.icon;
    const choices = this._entry()?.icons || [];
    const installedArtwork = this._physical?.native_type === remote.native_type ? remote.artwork_id : undefined;
    const artwork = native ? this._nativeArtworkSrc(profile, installedArtwork)
      : this._hidArtworkSrc(remote.device_type, remote.artwork_id) || this._irArtworkSrc(remote);
    const canChooseIcon = !firmwareArtwork;
    return `<section class="appearance">
      <div class="appearance-head"><div><b>Appearance</b><span>How this remote is shown and arranged</span></div></div>
      <div class="appearance-grid">
        ${native ? `<section class="native-type-panel"><div class="native-type-heading"><b>Type</b>
          <span>Choose the built-in screen and button layout.</span></div>
          ${this._nativeTypeChoices(this._nativeProfiles, this._physical.native_type || this._physical.template, "native-profile")}
          ${this._physicalChanges() ? `<div class="appearance-profile-save"><span class="appearance-draft">Type or layout change pending</span>
            <button class="primary compact" data-physical-apply ${this._physicalBusy ? "disabled" : ""}>Save to remote</button></div>` : ""}
        </section>` : isHid || isIr ? `<div class="appearance-part">
          <div class="artwork-preview">${artwork ? `<img src="${artwork}" alt="Firmware illustration for ${escapeHtml(native ? profile?.title : remote.device_type)}">` : "—"}</div>
          <div class="appearance-part-body">
            ${isHid ? `<b>HID screen</b><p>This illustration is built into the selected HID type. Changing the catalog icon code does not change it.</p>`
              : `<b>IR screen</b><p>${artwork ? "The IR type and saved icon variant select this built-in illustration." : "No decoded firmware illustration is available for this IR type."}</p>`}
          </div>
        </div>` : ""}
        ${canChooseIcon ? `<div class="appearance-part">
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
          value="${escapeHtml(this._tileNameDraft ?? remote.name)}"></label>
        ${canChooseIcon ? `<span class="appearance-field-label">Device icon</span>
        <div class="appearance-icon-grid">${choices.map((name) => `<button
          class="appearance-icon-choice${name === pickedIcon ? " selected" : ""}"
          data-pick-icon="${escapeHtml(name)}" type="button" aria-label="${escapeHtml(APP_ICON_LABELS[name] || name)}"
          aria-pressed="${name === pickedIcon}">${this._iconImage(name)}<span>${escapeHtml(APP_ICON_LABELS[name] || name)}</span></button>`).join("")}</div>` : ""}
        ${isHid ? `<p class="appearance-note">This remote keeps its saved icon code.</p>`
          : isIr ? `<p class="appearance-note">This remote keeps its saved icon code. The app's 18 icon names are not 18 distinct firmware illustrations.</p>`
          : `<p class="appearance-note">These previews come from the SwitchBot app. Distinct physical artwork for every catalog icon is not confirmed.</p>`}
        ${this._physicalChanges() ? `<p class="appearance-note">Save the screen layout first, then save the name${firmwareArtwork ? "" : " and icon"}.</p>` : ""}
        <div class="appearance-actions"><button class="primary" data-tile-save="1" ${this._physicalBusy || this._physicalChanges() ? "disabled" : ""}>${canChooseIcon ? "Save name and icon" : "Save name"}</button>
          <button class="secondary compact" data-icon-cancel="1">Cancel</button></div>
      </div>` : ""}
      ${native ? this._renderNativeProfileWarnings() : ""}
    </section>`;
  }

  _renderFace(page) {
    const byPos = {};
    (page?.buttons || []).forEach((item) => {
      byPos[String(item.position || "").toUpperCase()] = item;
    });
    const key = (tag, body, label) => this._key(byPos, tag, body, label);
    const pages = this._pages();
    const mainButtons = pages.find((item) => item.index === 0)?.buttons || [];
    const softkeys = Object.fromEntries(mainButtons.map((item) => [
      String(item.position || "").toUpperCase(), item,
    ]));
    const profile = this._nativeProfile(this._physical?.native_type || this._physical?.template);
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
          <clipPath id="screenClip">
            <path d="M35 65 C35 40 55 20 80 20 H220 C245 20 265 40 265 65 V262 H35 Z"/>
          </clipPath>
        </defs>
        <rect x="35" y="20" width="230" height="617" rx="45" fill="url(#body)" class="shell"/>
        <path d="M35 65 C35 40 55 20 80 20 H220 C245 20 265 40 265 65 V296 H35 Z" class="glass"/>
        <path d="M48 58 C50 43 63 32 80 32 H220 C237 32 250 43 252 58" class="glass-edge"/>
        <foreignObject x="35" y="20" width="230" height="242" clip-path="url(#screenClip)">
          <div xmlns="http://www.w3.org/1999/xhtml" class="scr-scroll" tabindex="0"
            data-screen-key="${escapeHtml(`${this._entryId}:${page?.index ?? 0}:${page?.index ? this._remoteId : "home"}`)}">
            ${this._renderScreen(page)}
          </div>
        </foreignObject>
        <g class="scr-sep"><path d="M35 262h230"/></g>
        <g class="screen-softkeys">
        ${Array.from("ABCD", (tag, index) => {
          const linked = pages.find((item) => item.index === index + 1);
          const linkFunction = profile?.main_keys?.find((item) =>
            item.index === index && !item.actionable)?.function
            ?? profile?.subpages?.find((item) => item.index === index + 1)?.link_function;
          const linkGlyph = this._physical?.pages.find((item) => item.index === linked?.index)?.link_glyph;
          const glyphSrc = this._nativeGlyphSrc(linked
            ? { button_function: linkFunction, button_glyph: linkGlyph }
            : softkeys[tag]);
          const x = 52 + index * 52;
          const shape = `<rect x="${x}" y="265" width="44" height="27" rx="5" class="cap"/>
            ${glyphSrc ? `<image href="${glyphSrc}" x="${x + 6}" y="269" width="19" height="19"/>` : ""}
            <text x="${x + (glyphSrc ? 33 : 22)}" y="282" class="cap-t">${tag}</text>`;
          // A key that opens a page has no command of its own: that is what the firmware does
          // with it, and it is why it cannot carry a Home Assistant action.
          if (linked) {
            const previousLink = this._physicalBaseline?.pages.find((item) => item.index === linked.index);
            const changed = this._physical && (!previousLink || previousLink.link_glyph !== linkGlyph);
            return `<g class="k link${page?.index === linked.index ? " current-page" : ""}${changed ? " unsaved" : ""}"
              role="button" tabindex="0" data-page-link="${linked.index}">
              <title>${escapeHtml(tag)} opens ${escapeHtml(linked.name)}</title>${shape}</g>`;
          }
          return this._key(softkeys, tag, shape, tag);
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
    const known = new Set(["ON", "OFF", "UP", "DOWN", "LEFT", "RIGHT", "OK", "BACK", "HOME",
      "KATA", "SOUNDOFF", "VOLADD", "VOLDEL", "CHUP", "CHDOWN", "A", "B", "C", "D"]);
    const extras = (page?.buttons || []).filter(
      (item) => !known.has(String(item.position || "").toUpperCase()));
    const extrasRow = extras.length
      ? `<div class="screen-keys"><div class="sk-title">Positions this remote uses that the
         device has no key for</div><div class="button-grid">${extras.map((item) => {
          const [status, statusLabel] = this._status(item);
          const draft = this._draftLabel(item);
          return `<button class="remote-button ${status}${item.button_id === this._buttonId ? " selected" : ""}${draft ? " unsaved" : ""}"
            data-button="${escapeHtml(item.button_id)}" title="${escapeHtml(statusLabel)}${draft ? ` · ${draft} in draft` : ""}">
            ${this._nativeGlyph(item, "glyph")}<span>${escapeHtml(item.label)}</span><i></i></button>`;
        }).join("")}</div></div>`
      : "";
    return svg + extrasRow;
  }

  _render() {
    if (!this.shadowRoot) return;
    const active = this.shadowRoot.activeElement;
    const nameForm = active?.matches('input[name="title"]')
      ? active.closest("[data-menu-name]") : null;
    const editingName = nameForm ? {
      key: nameForm.dataset.nameKey, value: active.value,
      start: active.selectionStart, end: active.selectionEnd,
      direction: active.selectionDirection,
    } : null;
    // A throw while building the markup used to leave an empty shadow root and a blank page,
    // which hides the very message that would explain it. Render failures are shown instead.
    try {
      this._renderUnsafe();
      if (editingName) {
        const form = [...this.shadowRoot.querySelectorAll("[data-menu-name]")]
          .find((item) => item.dataset.nameKey === editingName.key);
        const input = form?.elements.title;
        if (input) {
          input.value = editingName.value;
          input.focus({ preventScroll: true });
          input.setSelectionRange(editingName.start, editingName.end, editingName.direction);
        }
      }
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
            <button class="secondary" id="refresh" title="Re-read the remote and pick up anything created in the SwitchBot app">${this._physicalBusy ? "Refreshing…" : "Refresh"}</button>
          </div>
        </header>
        ${this._error ? `<div class="error">${escapeHtml(this._error)}</div>` : ""}
        ${this._loading ? `<div class="loading"><span></span>Loading remotes…</div>` : ""}
        ${!this._loading && !entries.length ? `<div class="empty"><b>No configured Universal Remote found.</b><br>Set up the integration first.</div>` : ""}
        ${entries.length ? `
          <section class="selectors">
            <label>Universal Remote
              <select id="entrySelect">${entries.map((item) => `<option value="${escapeHtml(item.entry_id)}" ${item.entry_id === this._entryId ? "selected" : ""}>${escapeHtml(item.title)} · ${escapeHtml(item.address)}</option>`).join("")}</select>
            </label>
            <label>Logical remote
              <select id="remoteSelect">${(entry?.remotes || []).map((item) => `<option value="${escapeHtml(item.remote_id)}" ${item.remote_id === this._remoteId ? "selected" : ""}>${escapeHtml(item.name)} · ${escapeHtml(item.device_type)}</option>`).join("")}</select>
            </label>
            <div class="identity"><span>Stable ID</span><code>${escapeHtml(remote?.remote_id || "—")}</code><small>Slot ${escapeHtml(remote?.remote_slot ?? "unknown")}</small></div>
          </section>
          <div class="toolbar">
            ${this._action("addRemote", "＋", "Add a remote",
              "Install a new remote on the Universal Remote", "accent")}
            ${remote ? this._action("recreateRemote", "↻", "Write again",
              "Remove this remote from the device and write it back, unchanged") : ""}
            ${remote?.can_test_native_icon ? `<button class="secondary" id="nativeIconVariantTest"
              title="Temporarily show the built-in Floor lamp screen profile; the original page is saved">Test Floor lamp screen</button>
              ${remote.native_icon_test_active ? `<button class="secondary" id="nativeIconVariantRestore"
                title="Restore the saved original Main page">Restore original</button>` : ""}` : ""}
            ${remote?.can_move ? this._action("moveRemote", "⇄", "Move to another bridge",
              "Bind this remote to a different Bluetooth address") : ""}
            ${remote ? this._action("deleteRemote", "🗑", "Delete",
              `Remove "${remote.name}" from the Universal Remote for good`, "danger") : ""}
          </div>
          ${this._renderAddRemote()}
          ${remote?.reachability ? `<p class="reachability ${escapeHtml(remote.reachability.level)}">${escapeHtml(remote.reachability.text)}</p>` : ""}
          ${this._renderApplyBar()}
          ${this._iconPickerFor ? "" : this._renderNativeProfileWarnings()}
          ${this._renderCloud()}
          ${this._renderDeviceTable()}
          ${this._renderDiagnostics()}
          ${remote ? `
            <section class="quick-bind">
              <div><b>Quick bind</b><span>Apply a complete light preset; individual buttons can override it.</span></div>
              <select id="lightSelect"><option value="">Choose a light…</option>${lights.map((state) => `<option value="${escapeHtml(state.entity_id)}" ${state.entity_id === boundLight ? "selected" : ""}>${escapeHtml(state.attributes.friendly_name || state.entity_id)}</option>`).join("")}</select>
              <button class="secondary" id="quickBind">Apply preset</button>
            </section>
            <nav class="pages">${this._pages().map((item) => `<button data-page="${item.index}" class="${item.index === page?.index ? "selected" : ""}">${escapeHtml(item.name)}${item.draft_only ? " •" : ""}</button>`).join("")}</nav>
            ${page?.index ? `<p class="small page-note">Opened by key
              <b>${"ABCD"[page.index - 1] || page.index}</b> on Main. That is a property of the
              layout, not a Home Assistant action: a key either opens a page or sends a command,
              never both.</p>` : ""}
            <div class="workspace">
              <section class="remote-stage">
                <div class="device-wrap">${this._renderFace(page)}</div>
                ${this._physical?.pages?.some((item) => item.index === page?.index) ? `
                <div class="stage-actions">
                  ${!page?.index
                    ? `<span class="small">Pick a key above to give it a command.</span>`
                    : this._freeIndexOnPage(page.index) !== null
                      ? `<button class="secondary compact" id="addKeyToPage" title="Put a new row on this page's screen list">Add a row</button>`
                      : `<span class="small">This page is full.</span>`}
                  ${page?.index ? `${this._availablePageIndexes().length ? `<label class="page-move">Move page<select id="moveCurrentPage"><option value="">Choose letter…</option>${this._availablePageIndexes().map((index) => `<option value="${index}">Page ${"ABCD"[index - 1]}</option>`).join("")}</select></label>` : `<span class="small page-capacity">No free page letter</span>`}<button class="secondary compact destructive" id="removeThisPage" title="Remove this page and every button on it">Delete page</button>` : ""}
                </div>` : ""}
              <div class="legend"><span><i class="preset"></i>Quick bind</span><span><i class="custom"></i>Custom</span><span><i class="disabled"></i>Disabled</span>${this._physical ? '<span><i class="unsaved"></i>Unsaved change</span>' : ""}</div>
              </section>
              <aside class="editor">${this._iconPickerFor === remote.remote_id
                ? this._renderAppearance(remote)
                : this._renderMenuNames(page, button) + this._renderMenuIcon(page) + (button ? this._editor(button, remote)
                  : `<div class="empty small">Choose a button, or use the pencil on a remote to edit its appearance.</div>`)}</aside>
            </div>
          ` : `<div class="empty"><b>No locally managed remotes.</b><br>Press Refresh to pick up remotes created in the SwitchBot app, or add one in the integration settings.</div>`}
        ` : ""}
      </main>`;
    const screen = this.shadowRoot.querySelector(".scr-scroll");
    if (screen) screen.scrollTop = previousScroll;
    this._wireEvents();
    this.shadowRoot.querySelectorAll(".native-type-search input").forEach((input) => {
      input.addEventListener("input", () => {
        this._nativeTypeSearch = input.value;
        const start = input.selectionStart;
        const end = input.selectionEnd;
        this._render();
        const replacement = this.shadowRoot.getElementById(input.id);
        replacement?.focus({ preventScroll: true });
        if (start !== null && end !== null) replacement?.setSelectionRange(start, end);
      });
    });
    this._wireAddRemote();
    this._wireDiagnostics();
    this._wireCloud();
    this._mountActionSelector();
    this._ensureLayout();
    this._ensureCatalog();
    this._ensureCloud();
    // The diagnostics table reports each controller's capacity, which comes from here.
    if (!this._sourcesError) this._ensureSources();
  }

  async _openPhysical() {
    clearTimeout(this._activeTimer);
    const request = Symbol();
    this._physicalRequest = request;
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/get`,
        entry_id: this._entryId, remote_id: this._remoteId });
      if (request !== this._physicalRequest) return;
      this._physical = result.layout;
      this._physicalBackup = result.backup;
      this._physicalSources = result.ir_sources;
      this._physicalFunctions = result.functions || [];
      this._nativeProfiles = result.native_profiles || [];
      this._physicalBaseline = structuredClone(result.layout);
      this._resetPhysicalOrigins(result.layout);
      this._physicalStatus = result.status || "";
    } catch (error) {
      if (request !== this._physicalRequest) return;
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
      ${cloud.error ? `<p class="small warning">${escapeHtml(cloud.error)}</p>` : ""}
      ${cloud.note ? `<p class="small">${escapeHtml(cloud.note)}</p>` : ""}
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
      ${diag?.error ? `<p class="small warning">${escapeHtml(diag.error)}</p>` : ""}
      ${diag?.rows ? `<table><thead><tr><th>Query</th><th>Answer</th></tr></thead><tbody>${
        diag.rows.map((row) => `<tr><td><code>${escapeHtml(row.query)}</code></td>
          <td><code>${escapeHtml(row.value)}</code></td></tr>`).join("")
      }</tbody></table>` : ""}
      ${(this._sources?.native_options?.controllers || []).length ? `
        <table><thead><tr><th>Controller</th><th>Tiles</th><th>Advertising now</th></tr></thead>
        <tbody>${this._sources.native_options.controllers.map((item) => `<tr>
          <td>${escapeHtml(item.adapter)}<br><code>${escapeHtml(item.address)}</code></td>
          <td>${item.used} of ${item.capacity}${
            item.extended_advertising ? "" : "<br><span class=\"small\">no Bluetooth 5</span>"}</td>
          <td>${(item.serving || []).map((a) => `<code>${escapeHtml(a)}</code>`).join("<br>")
            || "<span class=\"small\">not reported</span>"}</td></tr>`).join("")}
        </tbody></table>
        <p class="small">The add-on's <b>addresses</b> option is only the starting list; Remote
          Studio adds to it as remotes are created, and the add-on keeps those across restarts.
          This column is what it is actually advertising.</p>` : ""}
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

  async _readDeviceTable() {
    this._deviceTable = { loading: true };
    this._render();
    try {
      this._deviceTable = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/table`,
        entry_id: this._entryId });
    } catch (error) { this._deviceTable = { error: error?.message || String(error) }; }
    this._render();
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
      return `<details class="device-table"><summary>Installed on the remote</summary>
        <p class="small">Could not read the device table: ${escapeHtml(table.error)}</p></details>`;
    }
    const rows = (table.rows || []).map((row) => `<tr>
        <td>${row.slot}</td><td>${escapeHtml(row.kind)}</td>
        <td>${escapeHtml(row.device_type)}</td><td>${escapeHtml(row.target_mac)}</td>
      </tr>`).join("");
    const warnings = (table.warnings || []).map(
      (text) => `<p class="small warning">${escapeHtml(text)}</p>`).join("");
    return `<details class="device-table">
      <summary>Installed on the remote (${(table.rows || []).length}, next free slot ${table.next_free_slot})</summary>
      <table><thead><tr><th>Slot</th><th>Kind</th><th>Type</th><th>Target</th></tr></thead>
      <tbody>${rows}</tbody></table>
      ${warnings}
      <p class="small">A row is identified by its slot, not by its target address.</p>
    </details>`;
  }

  _action(id, glyph, label, hint, tone = "") {
    // One shape for every top-level action: a glyph to find it by, a short label, and the
    // consequence on hover. The tone carries the weight, so nothing is only a word.
    return `<button class="action ${tone}" id="${id}" title="${escapeHtml(hint)}">
      <span class="g">${glyph}</span><span>${escapeHtml(label)}</span></button>`;
  }

  _renderAddRemote() {
    const add = this._add;
    if (!add) return "";
    if (add.loading || add.loadError) {
      return `<section class="add-remote">
        <div class="action-title"><b>Add a remote</b></div>
        ${add.loading
          ? '<p class="small" role="status">Loading remote options…</p>'
          : `<p class="error" role="alert">Could not load remote options. ${escapeHtml(add.loadError)}</p>`}
        <div class="key-actions">
          ${add.loadError ? '<button class="primary" id="retryAddRemote">Retry</button>' : ""}
          <button class="secondary compact" id="addRemoteCancel">Cancel</button>
        </div>
      </section>`;
    }
    const sources = this._sources || {};
    const hidArtwork = this._hidArtworkSrc(add.deviceType);
    const cat = this._catalog;
    const kinds = [
      ["native", "Bridge remote", sources.native,
       "Reuses the credentials captured when the first native remote was added."],
      ["catalog", "IR from the catalog", sources.catalog && sources.cloud,
       "Search the bundled device database; the codes come from the SwitchBot cloud."],
      ["cloud", "IR saved in your account", (sources.cloud_remotes || []).length > 0,
       "Reinstall a remote you already made in the SwitchBot app."],
      ["hid", "HID remote", !!sources.hid,
       "Presses go out as Bluetooth keys to one paired host — a TV, a box, a computer."],
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
          placeholder="Search ${cat.brands.length} brand${cat.brands.length === 1 ? "" : "s"}…"></label>
        <select data-catalog="brand" size="6">${
          cat.brands.slice(0, 300).map((name) => option(name, name, name === cat.brand)).join("")
        }</select>
        ${cat.models.length ? `<label>Model<select data-catalog="model">
          <option value="">Choose a model…</option>${
            cat.models.map((item) => option(item.hxd_index, item.label, item.hxd_index === cat.hxd)).join("")
          }</select></label>` : ""}` : ""}
      ${add.kind === "native" ? `
        <p class="small">${escapeHtml(sources.native_options?.summary || "")}</p>
        <label>Bridge address<select data-add-field="target_id">${
          [sources.native_options?.free
            ? option("__auto__", `Next free address${
                sources.native_options?.next_address
                  ? ` (${sources.native_options.next_address})` : ""}`,
              add.addressMode === "auto")
            : ""]
            .concat((sources.bridges || []).map((item) =>
              option(item.target_id, item.name,
                add.addressMode === "stored" && item.target_id === add.targetId)))
            .concat(option("__new__", "An address I type myself…", add.addressMode === "new"))
            .join("")
        }</select></label>
        ${add.addressMode === "new" ? `
          <label>New address<input type="text" data-add-field="new_target_address"
            value="${escapeHtml(add.newAddress || "")}" placeholder="DA:71:16:E0:1F:92"></label>` : ""}
        ${!sources.native_options?.free ? `<p class="small warning">Every address on every
          controller is in use. Add another Bluetooth adapter with its own add-on instance to
          go further.</p>` : ""}
        <div class="native-type-panel add-native-type-panel"><div class="native-type-heading"><b>Type</b>
          <span>Choose the built-in screen and button layout.</span></div>
          ${this._nativeTypeChoices(sources.native_options?.screen_profiles || [], add.nativeType || add.deviceType, "add-native-type")}
        </div>
        <label>AES key<input type="text" data-add-field="target_key" spellcheck="false"
          value="${escapeHtml(add.targetKey || "")}"
          placeholder="32 hex characters, the same as the add-on's device_key"></label>
        <p class="small">The remote encrypts each press with this key, so it must match the
          add-on's <b>device_key</b> exactly, or the press decodes to nothing.</p>` : ""}
      ${add.kind === "cloud" ? `<label>Remote<select data-add-field="remote_id">${
        (sources.cloud_remotes || []).map((item) => option(item.remote_id, item.name, item.remote_id === add.remoteId)).join("")
      }</select></label>` : ""}
      ${add.kind === "hid" ? `
        <label>Kind<select data-add-field="device_type">${
          (sources.hid?.device_types || []).map((item) => option(item, item, item === add.deviceType)).join("")
        }</select></label>
        <div class="add-native-artwork"><div class="artwork-preview">${hidArtwork
          ? `<img src="${hidArtwork}" alt="Firmware artwork for ${escapeHtml(add.deviceType)}">`
          : "—"}</div><p class="small">The HID type determines the built-in screen illustration.</p></div>
        <label>Paired host<input type="text" data-add-field="device_id" value="${escapeHtml(add.deviceId || "")}"
          placeholder="AA:BB:CC:DD:EE:FF — the machine that receives the key presses"></label>
        <p class="small">${sources.hid?.host_mac
          ? `This remote is paired with ${escapeHtml(sources.hid?.host_mac)}.`
          : "No host is paired yet. The remote refuses a HID remote until one is."}
          <button class="link-button" id="pairHost">${sources.hid?.host_mac ? "Pair a different host" : "Pair a host"}</button></p>
        <label>Buttons</label>
        <div class="button-picks">${(sources.hid?.buttons || []).map((name) =>
          `<label class="inline"><input type="checkbox" data-add-button="${escapeHtml(name)}"
            ${(add.buttons || []).includes(name) ? "checked" : ""}>${escapeHtml(name)}</label>`).join("")}</div>` : ""}
      <label>Name<input type="text" data-add-field="name" value="${escapeHtml(add.name || "")}"
        placeholder="What it is called on the remote's screen"></label>
      ${add.kind === "native" ? "" : `<label class="inline"><input type="checkbox" data-add-field="replace"
        ${add.replace ? "checked" : ""}>Replace an existing copy of the same remote</label>`}
      ${add.error ? `<p class="small warning">${escapeHtml(add.error)}</p>` : ""}
      <div class="key-actions">
        <button class="primary" id="addRemoteConfirm" ${add.busy ? "disabled" : ""}>${
          add.busy ? "Installing…" : "Install"}</button>
        <button class="secondary compact" id="addRemoteCancel">Cancel</button>
      </div>
    </section>`;
  }

  async _ensureSources() {
    const entryId = this._entryId;
    if (!entryId) return null;
    if (this._sources && this._sourcesEntry === entryId) return this._sources;
    if (this._sourcesRequest?.entryId === entryId) return this._sourcesRequest.promise;
    const request = { entryId };
    this._sourcesRequest = request;
    this._sourcesError = "";
    request.promise = Promise.resolve().then(async () => {
      try {
        const sources = await this._hass.callWS({
          type: `${DOMAIN}/studio/remote/sources`, entry_id: entryId });
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
    this._render();
    const sources = await this._ensureSources();
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
      icon: (kind === "native"
        ? "light"
        : (sources.hid?.icons || [])[0]) || "",
      deviceId: sources.hid?.host_mac || "",
      buttons: [...(sources.hid?.default_buttons || [])],
      targetId: (sources.bridges || [])[0]?.target_id || "",
      // Let the integration pick the address by default: it knows every controller's
      // capacity and which addresses are already bound.
      addressMode: sources.native_options?.free ? "auto" : "stored",
      newAddress: "",
      targetKey: sources.native_options?.default_key || "",
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
        add.nativeType = "";
        add.error = "";
        const kinds = this._sources || {};
        // Device types and icons differ per kind; carrying one tab's choice into another
        // would offer a value the backend rejects.
        add.deviceType = (add.kind === "native"
          ? kinds.native_options?.default_screen_profile
          : (kinds.hid?.device_types || [])[0]) || "";
        add.icon = (add.kind === "native"
          ? "light"
          : (kinds.hid?.icons || [])[0]) || "";
        this._render();
      });
    });

    root.querySelectorAll("[data-add-native-type]").forEach((button) => {
      button.addEventListener("click", () => {
        const selected = (this._sources?.native_options?.screen_profiles || [])
          .find((item) => item.value === button.dataset.addNativeType);
        add.nativeType = button.dataset.addNativeType;
        add.deviceType = selected?.profile || button.dataset.addNativeType;
        add.icon = "light";
        this._render();
      });
    });

    root.querySelectorAll("[data-add-field]").forEach((field) => {
      field.addEventListener("input", () => {
        const name = field.dataset.addField;
        if (name === "name") add.name = field.value;
        else if (name === "replace") add.replace = field.checked;
        else if (name === "remote_id") add.remoteId = field.value;
        else if (name === "device_type") add.deviceType = field.value;
        else if (name === "icon") add.icon = field.value;
        else if (name === "device_id") add.deviceId = field.value;
        else if (name === "new_target_address") add.newAddress = field.value;
        else if (name === "target_key") add.targetKey = field.value.replace(/\s+/g, "");
      });
      field.addEventListener("change", () => {
        const name = field.dataset.addField;
        if (name === "remote_id") add.remoteId = field.value;
        if (name === "replace") add.replace = field.checked;
        if (name === "device_type") {
          add.deviceType = field.value;
          if (add.kind === "native" || add.kind === "hid") this._render();
        }
        if (name === "icon") add.icon = field.value;
        if (name === "target_id") {
          add.addressMode = field.value === "__new__" ? "new"
            : field.value === "__auto__" ? "auto" : "stored";
          if (add.addressMode === "stored") add.targetId = field.value;
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
      const needle = event.target.value.trim().toLowerCase();
      const list = root.querySelector('.add-remote [data-catalog="brand"]');
      if (!list) return;
      const matches = needle
        ? this._catalog.brands.filter((name) => name.toLowerCase().includes(needle))
        : this._catalog.brands;
      list.innerHTML = matches.slice(0, 300).map(
        (name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
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

    root.querySelectorAll("[data-add-button]").forEach((box) => {
      box.addEventListener("change", () => {
        const name = box.dataset.addButton;
        const picked = new Set(add.buttons || []);
        if (box.checked) picked.add(name); else picked.delete(name);
        // Keep the catalog's own order so the remote's screen matches the list.
        add.buttons = (this._sources?.hid?.buttons || []).filter((item) => picked.has(item));
      });
    });

    root.getElementById("pairHost")?.addEventListener("click", async () => {
      const current = this._sources?.hid?.host_mac || add.deviceId || "";
      const host = prompt("Bluetooth address of the host that should receive the key presses", current);
      if (!host) return;
      add.busy = true;
      this._render();
      try {
        await this._hass.callWS({ type: `${DOMAIN}/studio/host/pair`,
          entry_id: this._entryId, host_mac: host });
        if (this._sources?.hid) this._sources.hid.host_mac = host;
        if (!add.deviceId) add.deviceId = host;
        add.error = "";
        this._notify(`Paired with ${host}`);
      } catch (error) { add.error = error?.message || String(error); }
      finally { add.busy = false; this._render(); }
    });

    root.getElementById("addRemoteCancel")?.addEventListener("click", () => {
      this._add = null;
      this._render();
    });

    root.getElementById("addRemoteConfirm")?.addEventListener("click", () => this._installRemote());
  }

  async _installRemote() {
    const add = this._add;
    const name = (add.name || "").trim();
    if (!name) { add.error = "Give the remote a name."; this._render(); return; }
    if (add.kind === "catalog" && !this._catalog.hxd) {
      add.error = "Choose a model from the catalog."; this._render(); return;
    }
    if (add.kind === "cloud" && !add.remoteId) {
      add.error = "Choose one of your saved remotes."; this._render(); return;
    }
    if (add.kind === "hid") {
      if (!add.deviceId) { add.error = "Give the address of the host to send keys to."; this._render(); return; }
      if (!(add.buttons || []).length) { add.error = "Pick at least one button."; this._render(); return; }
    }
    if (add.kind === "native" && add.targetKey && !/^[0-9a-fA-F]{32}$/.test(add.targetKey)) {
      add.error = "The AES key must be exactly 32 hexadecimal characters.";
      this._render(); return;
    }
    add.busy = true;
    add.error = "";
    this._physicalBusy = true;
    this._render();
    try {
      let result;
      if (add.kind === "native") {
        if (add.addressMode === "new" && !(add.newAddress || "").trim()) {
          add.error = "Give the new bridge address.";
          add.busy = false; this._physicalBusy = false; this._render(); return;
        }
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/create`,
          entry_id: this._entryId, name,
          native_type: add.nativeType || add.deviceType, icon: add.icon,
          ...(add.targetKey ? { target_key: add.targetKey } : {}),
          ...(add.addressMode === "new"
            ? { new_target_address: add.newAddress.trim() }
            : add.addressMode === "auto"
              ? { auto_address: true }
              : add.targetId ? { target_id: add.targetId } : {}) });
      } else if (add.kind === "hid") {
        result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/create_hid`,
          entry_id: this._entryId, name, device_type: add.deviceType,
          device_id: add.deviceId, icon: add.icon, buttons: add.buttons });
      } else {
        result = await this._hass.callWS({
          type: `${DOMAIN}/studio/remote/install_ir`,
          entry_id: this._entryId,
          source: add.kind,
          name,
          replace_existing: !!add.replace,
          ...(add.kind === "catalog"
            ? { hxd_index: this._catalog.hxd, remote_type: this._catalog.remoteType }
            : { remote_id: add.remoteId }),
        });
      }
      this._notify(result?.warning
        || (result?.new_bridge
          ? `Installed in slot ${result.slot} on the new bridge ${result.bridge}`
          : `Installed in slot ${result.slot}`));
      this._add = null;
      this._physical = null;
      this._physicalFor = null;
      this._error = null;
    } catch (error) {
      add.error = error?.message || String(error);
    } finally {
      add.busy = false;
      this._physicalBusy = false;
      await this._load();
    }
  }

  _renderApplyBar() {
    if (!this._physical) return "";
    const changes = this._physicalChanges();
    if (!changes && !this._physicalStatus) return "";
    return `<div class="apply-bar ${changes ? "dirty" : ""}">
      <span>${changes
        ? `${changes} change${changes === 1 ? "" : "s"} to the remote itself. Save writes them.`
        : escapeHtml(this._physicalStatus)}</span>
      <span class="spacer"></span>
      ${this._physicalBackup ? `<button class="secondary compact" id="physicalRestore">Load previous layout</button>` : ""}
      ${changes ? `<button class="secondary compact" id="physicalDiscard">Discard</button>` : ""}
      ${changes && !this._iconPickerFor ? `<button class="primary compact" data-physical-apply ${this._physicalBusy ? "disabled" : ""}>Save screen layout</button>` : ""}
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

  _moveMainButton(from, to) {
    const page = this._physical?.pages?.find((item) => item.index === 0);
    const button = page?.buttons?.find((item) => item.index === from);
    if (!button || page.buttons.some((item) => item.index === to)) return;
    const oldId = `p0_k${from}`;
    const newId = `p0_k${to}`;
    const origin = this._physicalOrigins[oldId] || oldId;
    delete this._physicalOrigins[oldId];
    button.index = to;
    this._physicalOrigins[newId] = origin;
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
      const origin = this._physicalOrigins[oldId] || oldId;
      delete this._physicalOrigins[oldId];
      this._physicalOrigins[newId] = origin;
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
    const actionableMain = new Set((profile.main_keys || [])
      .filter((slot) => slot.actionable).map((slot) => slot.index));
    for (let index = 0; index < 4; index++) actionableMain.add(index);
    const availableMain = (profile.main_positions || []).filter((index) =>
      actionableMain.has(index) &&
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
      delete this._physicalOrigins[`p0_k${button.button_index}`];
      this._pageIndex = index;
      this._buttonId = null;
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
        function: button.default_function ?? (kindNow === "native" ? 5 : 115),
        code_hex: "",
      });
      this._render();
    });

    if (!found) return;
    const { page, key } = found;
    const kind = this._physical.kind;
    const rowPosition = page.index ? this._pageKeyEntries(page).findIndex((item) => item.key === key) : -1;
    const lastRowPosition = page.index ? page.buttons.length - 1 : -1;

    root.querySelector('[data-key-field="transport"]')?.addEventListener("change", (event) => {
      key.transport = event.target.value;
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
      const needle = event.target.value.trim().toLowerCase();
      const list = root.querySelector('.key-editor [data-catalog="brand"]');
      if (!list) return;
      const matches = needle
        ? this._catalog.brands.filter((name) => name.toLowerCase().includes(needle))
        : this._catalog.brands;
      list.innerHTML = matches.slice(0, 300).map(
        (name) => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join("");
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
        const entries = this._pageKeyEntries(page).filter((item) => item.key !== key);
        this._replacePageKeyOrder(page, entries);
      } else {
        page.buttons = page.buttons.filter((item) => item !== key);
        delete this._physicalOrigins[`p${page.index}_k${key.index}`];
      }
      this._buttonId = null;
      this._render();
    });

    root.getElementById("moveRowUp")?.addEventListener("click", () =>
      this._movePageKey(page.index, key.index, -1));
    root.getElementById("moveRowDown")?.addEventListener("click", () =>
      this._movePageKey(page.index, key.index, 1));

    root.getElementById("addKey")?.addEventListener("click", () => {
      const reserved = page.index === 0
        ? this._physical.pages.filter((item) => item.index).map((item) => item.index - 1) : [];
      const limit = page.index ? (kind === "hid" ? 15 : 18) : 19;
      const index = Array.from({ length: limit }, (_, i) => i).find(
        (i) => !reserved.includes(i) && !page.buttons.some((item) => item.index === i));
      if (index == null) {
        this._physicalStatus = "This page is full.";
      } else {
        page.buttons.push({
          index,
          transport: kind === "native" ? "native" : kind === "hid" ? "hid" : "ir",
          function: kind === "native" ? 5 : 115,
          code_hex: "",
        });
        this._buttonId = `p${page.index}_k${index}`;
      }
      this._render();
    });

    root.getElementById("removePage")?.addEventListener("click", () => {
      for (const key of page.buttons) delete this._physicalOrigins[`p${page.index}_k${key.index}`];
      this._physical.pages = this._physical.pages.filter((item) => item !== page);
      this._pageIndex = 0;
      this._buttonId = null;
      this._render();
    });

  }

  _wirePhysical() {
    const root = this.shadowRoot;
    this._wireKeyEditor(root);
    root.querySelectorAll("[data-menu-name]").forEach((form) => form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (this._physicalBusy) return;
      const page = Number(form.dataset.page);
      const row = form.dataset.row == null ? undefined : Number(form.dataset.row);
      const title = form.elements.title.value.trim();
      if (this._physicalChanges()) {
        const menu = this._physical.pages.find((item) => item.index === page);
        const owner = row == null ? menu : menu.buttons.find((item) => item.index === row);
        owner.title = title;
        this._render();
        return;
      }
      this._physicalBusy = true;
      this._render();
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/rename_menu_item`,
          entry_id: this._entryId, remote_id: this._remoteId, page, title,
          ...(row == null ? {} : { row }) });
        this._physical = result.layout;
        this._physicalBaseline = structuredClone(result.layout);
        this._error = null;
        this._notify("Menu name saved in Remote Studio");
      } catch (error) {
        this._error = error?.message || String(error);
      } finally {
        this._physicalBusy = false;
        this._render();
      }
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
    root.querySelectorAll("[data-physical-apply]").forEach((element) => element.addEventListener("click", async () => {
      try {
        await this._applyPhysical();
        this._error = null;
        this._notify(this._physicalStatus || "Screen layout saved to the remote");
      } catch (error) {
        this._error = error?.message || String(error);
        this._render();
      }
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
      this._resetPhysicalOrigins(this._physical);
      this._physicalStatus = "";
      this._render();
    });
    root.getElementById("physicalRestore")?.addEventListener("click", () => {
      this._physical = structuredClone(this._physicalBackup.layout);
      this._resetPhysicalOrigins(this._physical);
      for (const item of this._lastIdentityMigrations) {
        this._physicalOrigins[item.from] = item.to;
      }
      this._physicalStatus = "Previous layout loaded. Apply it to restore the physical remote.";
      this._render();
    });
    const newKey = (index) => ({ index, transport: this._physical.kind === "native" ? "native" : this._physical.kind === "hid" ? "hid" : "ir", function: this._physical.kind === "native" ? 5 : 115, code_hex: "" });
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
    if (!found) {
      // A position with no command has no entry in the draft layout. It is still a real key on
      // the remote, so offer the two things that can be done with it rather than nothing.
      const page = this._physical.pages?.find((item) => item.index === button.button_page);
      if (!page) return "";
      return `<div class="action-box key-editor">
        <div class="action-title"><b>On the remote</b><span>this position is empty</span></div>
        <div class="key-actions">
          ${button.can_add_command === false ? `<span class="small">This position opens a page and cannot also send a command.</span>` : `<button class="secondary compact" id="addKeyHere" title="Start using this position, so it can send something">Give this key a command</button>`}
        </div>
        ${this._pageControl(button, null)}
      </div>`;
    }
    const { page, key } = found;
    const kind = this._physical.kind;
    const rowPosition = page.index
      ? this._pageKeyEntries(page).findIndex((item) => item.key === key) : -1;
    const lastRowPosition = page.index ? page.buttons.length - 1 : -1;
    const linkedPage = button.button_page === 0 && key.index < 4
      ? this._physical.pages.find((item) => item.index === key.index + 1)
      : null;
    const pageControl = this._pageControl(button, key);
    const glyphPicker = kind === "native" && (page.index || key.index < 4)
      ? this._renderGlyphPicker(key, "glyph", "Button icon", key.function)
      : "";
    const nativeSoftkey = kind === "native" && page.index === 0 && key.index < 4 && !linkedPage;
    if (kind === "native" && button.button_page === 0 && !linkedPage && !pageControl
        && !nativeSoftkey) return glyphPicker;
    const transports = kind === "native" ? ["native"] : kind === "hid" ? ["hid", "ir"] : ["stored", "ir"];
    const label = { stored: "Original IR command", native: "Native / bridge", hid: "HID", ir: "IR" };
    return `${glyphPicker}<div class="action-box key-editor">
      <div class="action-title"><b>On the remote</b><span>${linkedPage
        ? `opens Page ${"ABCD"[linkedPage.index - 1] || linkedPage.index}`
        : "what this key sends when pressed"}</span></div>
      ${transports.length > 1 ? `<label>Command type<select data-key-field="transport">${
        transports.map((item) => `<option value="${item}" ${key.transport === item ? "selected" : ""}>${label[item]}</option>`).join("")
      }</select></label>` : ""}
      ${key.transport === "hid" || nativeSoftkey ? `<label>This key sends<select data-key-field="function">${
        (this._physicalFunctions || []).map((item) =>
          `<option value="${item.value}" ${key.function === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")
      }</select></label>` : ""}
      ${key.transport === "ir" ? `
        ${(this._physicalSources || []).length ? `<label>Copy from a button already on one of your remotes<select data-key-field="ir_source">
            <option value="">Choose…</option>${
            this._physicalSources.map((source, index) => `<option value="${index}" ${key.code_hex === source.code_hex ? "selected" : ""}>${escapeHtml(source.label)}</option>`).join("")
          }</select></label>` : ""}
        <label>IR code (hex)<textarea data-key-field="code_hex" spellcheck="false"
          placeholder="Paste the raw code, or copy one from a saved button above"
          >${escapeHtml(key.code_hex || "")}</textarea></label>
        ${this._renderCatalogPicker()}` : ""}
      <div class="key-actions">
        ${button.button_page ? `<button class="secondary compact destructive" id="removePage" title="Remove this page and every button on it">Delete this page</button>` : ""}
        ${this._freeIndexOnPage(button.button_page) !== null
          ? `<button class="secondary compact" id="addKey" title="Put a new row on this page's screen list">Add a row</button>` : ""}
        ${button.button_page ? `<div class="row-order"><span>Screen order</span>
          <button class="secondary compact" id="moveRowUp" ${rowPosition <= 0 ? "disabled" : ""} title="Move this row up">↑</button>
          <button class="secondary compact" id="moveRowDown" ${rowPosition >= lastRowPosition ? "disabled" : ""} title="Move this row down">↓</button></div>` : ""}
        ${button.button_page
          ? `<button class="secondary compact destructive" id="removeKey"
              title="Take this row off the page; the rows below it move up">Delete this row</button>`
          : linkedPage || (kind === "native" && !nativeSoftkey) ? "" : `<button class="secondary compact destructive" id="removeKey"
              title="The key stays on the remote and sends nothing until you give it another command">Clear this key</button>`}
      </div>
      ${pageControl}
    </div>`;
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
        placeholder="Search ${cat.brands.length} brand${cat.brands.length === 1 ? "" : "s"}…"></label>
      <select data-catalog="brand" size="6">${
        cat.brands.slice(0, 300).map((name) => option(name, name, name === cat.brand)).join("")
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
      ${cat.error ? `<p class="small warning">${escapeHtml(cat.error)}</p>` : ""}
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
    Object.assign(cat, { remoteType, brand: "", models: [], hxd: "", buttons: [], error: "" });
    const result = await this._hass.callWS({
      type: `${DOMAIN}/studio/catalog/brands`, remote_type: remoteType });
    cat.brands = result.brands || [];
  }

  _editor(button, remote) {
    if (button.draft_only) {
      return `
        <div class="editor-head"><div><h2>${escapeHtml(button.label)}</h2></div></div>
        ${this._renderKeyEditor(button)}
        <div class="explanation"><b>Not on the remote yet.</b><span>Save writes this page to the
        remote. Home Assistant actions can be assigned once it is there, because they are keyed on
        the button identity the remote reports when it is pressed.</span></div>`;
    }
    const [status, statusLabel] = this._status(button);
    const actionSummary = button.actions.length
      ? `${button.actions.length} action${button.actions.length === 1 ? "" : "s"}`
      : "No custom actions";
    return `
      <div class="editor-head">
        <div><span class="status-pill ${status}">${escapeHtml(statusLabel)}</span><h2>${escapeHtml(button.label)}</h2></div>
        <button class="secondary compact" id="testButton">Test</button>
      </div>
      <dl>
        <div><dt>Button ID</dt><dd><code>${escapeHtml(button.button_id)}</code></dd></div>
        <div><dt>Page / index</dt><dd>${button.button_page} / ${button.button_index}</dd></div>
        <div><dt>Function</dt><dd>${button.button_function}</dd></div>
        <div><dt>Remote</dt><dd>${escapeHtml(remote.remote_id)}</dd></div>
      </dl>
      ${this._renderKeyEditor(button)}
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
        }${remote.binding?.entity_id
          ? ` Every button on this remote that has no actions of its own drives
             ${escapeHtml(remote.binding.entity_id)}.` : ""}</span></div>` : ""}
        ${this._mode === "disabled" ? `<div class="explanation danger"><b>Ignore this button.</b><span>Physical presses will be received but no Home Assistant action will run.</span></div>` : ""}
        ${this._mode === "actions" ? `<div class="action-box"><div class="action-title"><b>Home Assistant actions</b><span>${escapeHtml(actionSummary)}${
          this._draftActions.length > 1 ? ", all of them on one press" : ""}</span></div><div id="visualActionEditor"></div><details><summary>Advanced JSON fallback</summary><textarea id="actionsJson" spellcheck="false">${escapeHtml(JSON.stringify(this._draftActions, null, 2))}</textarea><div class="json-help">This uses standard Home Assistant script action syntax.</div></details></div>` : ""}
      </div>
      `}
      <div class="save-row"><span id="saveStatus"></span><button class="primary" id="saveButton" ${
        this._mode === "actions" && !this._jsonValid ? "disabled" : ""}>${
        this._physicalChanges() ? "Save and write to remote" : "Save"}</button></div>`;
  }

  _wireEvents() {
    const root = this.shadowRoot;
    for (const id of ["entrySelect", "remoteSelect", "refresh", "addRemote",
                      "recreateRemote", "nativeIconVariantTest", "nativeIconVariantRestore", "moveRemote", "deleteRemote"]) {
      const el = root.getElementById(id);
      if (el) el.disabled = this._physicalBusy;
    }
    root.getElementById("refresh")?.addEventListener("click", () => this._refresh());
    root.getElementById("readDeviceTable")?.addEventListener("click", () => this._readDeviceTable());
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
      for (const key of page.buttons) delete this._physicalOrigins[`p${page.index}_k${key.index}`];
      this._physical.pages = this._physical.pages.filter((item) => item !== page);
      this._pageIndex = 0;
      this._buttonId = null;
      this._render();
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
        this._notify(`Rewritten into slot ${result.slot}`);
        this._physical = null;
        this._physicalFor = null;
        this._error = null;
      } catch (error) { rewriteError = error?.message || String(error); }
      finally { this._physicalBusy = false; await this._load(); }
      if (rewriteError) {
        this._error = rewriteError;
        this._render();
      }
    });

    const runNativeIconVariant = async (restore) => {
      const remote = this._remote();
      if (!remote) return;
      if (!restore && !confirm(`Temporarily switch "${remote.name}" to the built-in Floor lamp screen profile? The original Main page is saved for restore.`)) return;
      let actionError = null;
      this._physicalBusy = true;
      this._render();
      try {
        await this._hass.callWS({ type: `${DOMAIN}/studio/remote/icon_variant_test`,
          entry_id: this._entryId, remote_id: this._remoteId, restore });
        this._notify(restore ? "Original Main page restored" : "Floor lamp screen profile command acknowledged");
        this._error = null;
      } catch (error) { actionError = error?.message || String(error); }
      finally { this._physicalBusy = false; await this._load(); }
      if (actionError) {
        this._error = actionError;
        this._render();
        this._notify(actionError);
      }
    };
    root.getElementById("nativeIconVariantTest")?.addEventListener("click", () => runNativeIconVariant(false));
    root.getElementById("nativeIconVariantRestore")?.addEventListener("click", () => runNativeIconVariant(true));

    root.getElementById("moveRemote")?.addEventListener("click", async () => {
      const remote = this._remote();
      if (!remote) return;
      await this._ensureSources();
      const next = this._sources?.native_options?.next_address || "";
      // Typed in full rather than picked, because the usual reason to move is that the
      // controller changed and the address being moved to may not be one we know yet.
      const address = prompt(
        `Bind "${remote.name}" to which address?\n\n` +
        (next ? `Leave empty to take the next free one (${next}).` : "No free address is known."),
        "");
      if (address === null) return;
      if (!address && !next) return;
      if (!confirm(`This removes "${remote.name}" from the remote and writes it again. Continue?`)) return;
      this._physicalBusy = true;
      this._render();
      try {
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/remote/recreate`,
          entry_id: this._entryId, remote_id: this._remoteId,
          ...(address ? { target_address: address.trim() } : { auto_address: true }) });
        this._notify(result?.warning
          || (result.moved_from
            ? `Moved from ${result.moved_from} to ${result.address}`
            : `Rewritten into slot ${result.slot}`));
        this._sources = null;
        this._physical = null;
        this._physicalFor = null;
        this._error = null;
      } catch (error) { this._error = error?.message || String(error); }
      finally { this._physicalBusy = false; await this._load(); }
    });

    root.getElementById("deleteRemote")?.addEventListener("click", async () => {
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
          : "Remote deleted");
        this._remoteId = null;
        this._buttonId = null;
        this._physical = null;
        this._physicalFor = null;
        this._error = null;
      } catch (error) { this._error = error?.message || String(error); }
      finally { this._physicalBusy = false; await this._load(); }
    });


    this._wirePhysical();
    root.getElementById("entrySelect")?.addEventListener("change", (event) => {
      this._entryId = event.target.value;
      this._iconPickerFor = null;
      this._cloud = null;
      this._sources = null;
      this._physical = null;
      this._remoteId = null;
      this._buttonId = null;
      this._normalizeSelection();
      this._render();
    });
    root.getElementById("remoteSelect")?.addEventListener("change", (event) => {
      this._remoteId = event.target.value;
      this._iconPickerFor = null;
      this._iconDraft = null;
      this._physical = null;
      this._pageIndex = 0;
      this._buttonId = null;
      this._normalizeSelection();
      this._render();
    });
    root.querySelectorAll("[data-page]").forEach((element) =>
      element.addEventListener("click", () => {
        this._pageIndex = Number(element.dataset.page);
        this._buttonId = null;
        this._normalizeSelection();
        this._render();
      }),
    );
    root.querySelectorAll("[data-page-link]").forEach((element) => {
      const open = () => {
        this._pageIndex = Number(element.dataset.pageLink);
        this._buttonId = null;
        this._normalizeSelection();
        this._render();
      };
      element.addEventListener("click", open);
      element.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") { event.preventDefault(); open(); }
      });
    });

    root.querySelectorAll("[data-remote]").forEach((element) => {
      const pick = () => {
        this._remoteId = element.dataset.remote;
        this._iconPickerFor = null;
        this._iconDraft = null;
        this._buttonId = null;
        this._physical = null;
        this._physicalFor = null;
        this._normalizeSelection();
        this._render();
      };
      element.addEventListener("click", pick);
    });

    root.querySelectorAll("[data-icon-for]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._iconPickerFor = element.dataset.iconFor;
        this._iconDraft = null;
        this._tileNameDraft = this._remote()?.name || "";
        this._buttonId = null;
        this._render();
      });
    });

    root.querySelectorAll("[data-icon-cancel]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        this._iconPickerFor = null;
        this._iconDraft = null;
        this._tileNameDraft = null;
        this._render();
      });
    });

    root.querySelectorAll("[data-pick-icon]").forEach((element) => {
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        // Chosen, not yet written: the name may be being edited in the same breath.
        this._iconDraft = element.dataset.pickIcon;
        this._render();
      });
    });

    root.querySelector("[data-rename-input]")?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") { event.preventDefault(); this._saveTile(); }
      if (event.key === "Escape") {
        this._iconPickerFor = null;
        this._iconDraft = null;
        this._tileNameDraft = null;
        this._render();
      }
    });
    root.querySelector("[data-rename-input]")?.addEventListener("input", (event) => {
      this._tileNameDraft = event.target.value;
    });

    root.querySelector("[data-tile-save]")?.addEventListener("click", (event) => {
      event.stopPropagation();
      this._saveTile();
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
        if (this._mode !== element.dataset.mode) this._dirty = true;
        this._mode = element.dataset.mode;
        this._render();
      }),
    );
    root.getElementById("saveButton")?.addEventListener("click", () => this._save());
    root.getElementById("testButton")?.addEventListener("click", () => this._test());
    root.getElementById("quickBind")?.addEventListener("click", () => this._quickBind());
    root.getElementById("actionsJson")?.addEventListener("input", (event) => {
      try {
        const parsed = JSON.parse(event.target.value || "[]");
        if (!Array.isArray(parsed)) throw new Error("The root value must be an array");
        this._draftActions = parsed;
        this._dirty = true;
        this._jsonValid = true;
        event.target.classList.remove("invalid");
        const save = root.getElementById("saveButton");
        if (save) save.disabled = this._mode === "actions" && parsed.length === 0;
      } catch (_error) {
        this._dirty = true;
        this._jsonValid = false;
        event.target.classList.add("invalid");
        const save = root.getElementById("saveButton");
        if (save) save.disabled = true;
      }
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
    if (this._mountToken !== token || this._mode !== "actions") return;
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
      this._draftActions = structuredClone(event.detail?.value || []);
      this._dirty = true;
      this._jsonValid = true;
      const textarea = this.shadowRoot.getElementById("actionsJson");
      if (textarea) textarea.value = JSON.stringify(this._draftActions, null, 2);
      const save = this.shadowRoot.getElementById("saveButton");
      if (save) save.disabled = this._draftActions.length === 0;
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
      this._physicalStatus = result.status;
      this._physicalBackup = result.backup;
      this._lastIdentityMigrations = identityMigrations;
      this._physical = result.layout || this._physical;
      this._physicalBaseline = structuredClone(this._physical);
      this._resetPhysicalOrigins(this._physical);
      await this._load();
    } finally {
      this._physicalBusy = false;
      this._render();
    }
  }

  async _save() {
    const root = this.shadowRoot;
    const status = root.getElementById("saveStatus");
    const save = root.getElementById("saveButton");
    const button = this._button();
    const page = this._page();
    if (!button) return;
    if (this._mode === "actions" && !this._jsonValid) {
      if (status) status.textContent = "Fix the invalid JSON before saving";
      return;
    }
    const layoutChanges = this._physicalChanges();
    try {
      if (save) save.disabled = true;
      if (status) status.textContent = "Saving…";

      // The Home Assistant mapping. An empty custom-action list is not a valid mapping, so it
      // is skipped rather than rejected: the user may only have changed the layout or a name.
      if (!(this._mode === "actions" && !this._draftActions.length)) {
        const updated = await this._hass.callWS({
          type: `${DOMAIN}/studio/save_button_action`,
          entry_id: this._entryId,
          remote_id: this._remoteId,
          button_id: this._buttonId,
          mode: this._mode,
          actions: this._mode === "actions" ? this._draftActions : [],
        });
        this._replaceEntry(updated);
      }

      // Only touch the remote when its own layout actually differs.
      if (layoutChanges) {
        if (status) status.textContent = "Writing the layout to the remote…";
        await this._applyPhysical();
      }

      this._dirty = false;
      this._jsonValid = true;
      this._error = null;
      this._notify(layoutChanges ? this._physicalStatus || "Saved and written to the remote" : "Saved");
      // Keep the selection across the reload so the button just edited stays open.
      const keepPage = this._pageIndex;
      const keepButton = this._buttonId;
      if (!layoutChanges) await this._load();
      this._pageIndex = keepPage;
      this._buttonId = keepButton;
      this._normalizeSelection();
      this._render();
    } catch (error) {
      this._physicalBusy = false;
      if (status) status.textContent = error?.message || String(error);
      if (save) save.disabled = false;
      this._render();
    }
  }

  async _quickBind() {
    const entityId = this.shadowRoot.getElementById("lightSelect")?.value;
    if (!entityId) {
      this._notify("Choose a light first");
      return;
    }
    try {
      const updated = await this._hass.callWS({
        type: `${DOMAIN}/studio/quick_bind`,
        entry_id: this._entryId,
        remote_id: this._remoteId,
        entity_id: entityId,
      });
      this._replaceEntry(updated);
      const keepPage = this._pageIndex;
      const keepButton = this._buttonId;
      await this._load();
      this._pageIndex = keepPage;
      this._buttonId = keepButton;
      this._normalizeSelection();
      this._notify("Quick-bind light preset applied");
      this._render();
    } catch (error) {
      this._notify(error?.message || String(error));
    }
  }

  async _test() {
    try {
      await this._hass.callWS({
        type: `${DOMAIN}/studio/test_button`,
        entry_id: this._entryId,
        remote_id: this._remoteId,
        button_id: this._buttonId,
      });
      this._notify("Test press sent");
    } catch (error) {
      this._notify(error?.message || String(error));
    }
  }

  _replaceEntry(updated) {
    const index = this._entries().findIndex((item) => item.entry_id === updated.entry_id);
    if (index >= 0) this._data.entries[index] = updated;
  }

  _notify(message) {
    const event = new CustomEvent("hass-notification", {
      bubbles: true,
      composed: true,
      detail: { message },
    });
    this.dispatchEvent(event);
  }

  _styles() {
    return `
      .appearance{display:grid;gap:18px}.appearance-head{display:flex;align-items:flex-start;justify-content:space-between}.appearance-head>div{display:grid;gap:3px}.appearance-head b{font-size:22px;letter-spacing:-.03em}.appearance-head span,.appearance-part-body p,.appearance-note{font-size:12px;line-height:1.45;color:var(--secondary-text-color,#68727d)}
      .add-native-artwork{display:flex;align-items:center;gap:14px;padding:12px;border:1px solid var(--divider-color,#e2e5e8);border-radius:8px;background:var(--secondary-background-color,#f5f6f8)}.add-native-artwork p{line-height:1.5}.add-native-artwork .artwork-preview{width:86px;height:86px}.add-native-artwork .artwork-preview img{max-width:82px;max-height:82px}.ic-fallback{display:grid;place-items:center;flex:none;width:18px;height:18px;color:var(--secondary-text-color,#68727d)}
      .appearance-grid{display:grid;gap:12px}.appearance-part{display:flex;align-items:center;gap:16px;min-width:0;padding:14px;border:1px solid var(--divider-color,#e2e5e8);border-radius:16px;background:var(--secondary-background-color,#f5f6f8)}.appearance-part-body{flex:1;min-width:0}.appearance-part-body label{display:grid;gap:3px;font-size:12px;font-weight:700}.appearance-part-body select{margin-top:3px}.appearance-part-body p{margin:6px 0 0}.artwork-preview,.app-icon-preview{display:grid;place-items:center;flex:none;width:100px;height:100px;border-radius:14px;background:#171d24;color:#fff}.artwork-preview img{display:block;max-width:96px;max-height:96px;object-fit:contain}.app-icon-preview .ic-img{width:74px;height:74px;object-fit:contain}.appearance-profile-save{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:10px}.appearance-draft{font-size:11px;font-weight:700;color:var(--primary-color,#03a9f4)}
      .native-type-panel{display:grid;gap:10px;min-width:0}.native-type-heading{display:grid;gap:3px}.native-type-heading b{font-size:15px}.native-type-heading span{font-size:12px;color:var(--secondary-text-color,#68727d)}.native-type-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(96px,1fr));gap:8px}.native-type-choice{display:grid;grid-template-rows:60px auto auto;align-items:center;justify-items:center;gap:6px;min-width:0;min-height:112px;padding:8px 6px;border:1px solid var(--divider-color,#d9dee3);border-radius:8px;background:var(--card-background-color,#fff);color:var(--primary-text-color,#17202a);font:inherit;font-size:11px;font-weight:700;text-align:center;cursor:pointer}.native-type-choice:hover{border-color:var(--primary-color,#03a9f4)}.native-type-choice.selected{border-color:var(--primary-color,#03a9f4);box-shadow:inset 0 0 0 1px var(--primary-color,#03a9f4);background:color-mix(in srgb,var(--primary-color,#03a9f4) 8%,var(--card-background-color,#fff))}.native-type-choice:focus-visible{outline:2px solid var(--primary-color,#03a9f4);outline-offset:2px}.native-type-choice>span{overflow-wrap:anywhere}.native-type-choice .native-type-detail{font-size:9px;font-weight:500;line-height:1.2;color:var(--secondary-text-color,#68727d)}.native-type-art{display:grid;place-items:center;width:56px;height:56px;border-radius:6px;background:#171d24;color:#fff}.native-type-art img{max-width:54px;max-height:54px;object-fit:contain}.add-native-type-panel{margin:14px 0}
      .native-type-search{display:grid;gap:5px;font-size:12px;font-weight:700}.native-type-search input{height:38px;padding:0 10px;border:1px solid var(--divider-color,#dfe3e8);border-radius:8px;background:var(--card-background-color,#fff);color:inherit;font:inherit;font-weight:400}
      .appearance-editor{display:grid;gap:10px;padding-top:16px;border-top:1px solid var(--divider-color,#e2e5e8)}.appearance-editor label{display:grid;gap:6px;font-size:12px;font-weight:700}.appearance-editor input{height:42px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:10px;background:var(--card-background-color,#fff);color:inherit;font:inherit}.appearance-field-label{font-size:12px;font-weight:700}.appearance-icon-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(92px,1fr));gap:8px}.appearance-icon-choice{display:grid;justify-items:center;align-content:center;gap:5px;min-height:88px;padding:8px 5px;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--secondary-background-color,#f5f6f8);color:inherit;cursor:pointer}.appearance-icon-choice:hover{border-color:var(--primary-color,#03a9f4)}.appearance-icon-choice.selected{border:2px solid var(--primary-color,#03a9f4);background:color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff))}.appearance-icon-choice .ic-img{width:43px;height:43px;object-fit:contain;padding:4px;border-radius:8px;background:#171d24}.appearance-icon-choice span{font-size:10px;font-weight:700;text-align:center;line-height:1.15}.appearance-note{margin:0}.appearance-actions{display:flex;gap:8px;flex-wrap:wrap}.appearance-details{display:grid;gap:4px}.appearance-details span{display:block;font:11px/1.5 ui-monospace,monospace;color:var(--secondary-text-color,#68727d)}.appearance .native-profile-warnings{margin:0;padding:12px}
      .native-profile-warnings{display:grid;gap:10px;margin:16px 0 0;padding:14px 16px;border:1px solid var(--divider-color,#e2e5e8);border-radius:8px;background:var(--card-background-color,#fff)}
      .profile-capacity-warning{display:grid;gap:3px;margin-top:14px;padding:11px 13px;border-left:3px solid #bd6a0f;border-radius:5px;background:#bd6a0f12;font-size:12px}.profile-capacity-warning span{color:var(--secondary-text-color,#68727d)}
      .profile-conflicts{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px}.profile-conflict-heading{display:grid;gap:4px;margin-bottom:6px}.profile-conflict-heading span,.profile-conflict-row small{color:var(--secondary-text-color,#68727d);font-size:12px}
      .profile-conflict-row{display:grid;grid-template-columns:minmax(0,1fr) minmax(180px,260px);align-items:center;gap:12px;padding:10px 0;border-top:1px solid var(--divider-color,#e2e5e8)}.profile-conflict-row>span{display:grid;gap:3px}.profile-conflict-row label{display:grid;gap:3px;font-size:11px;font-weight:700;color:var(--secondary-text-color,#68727d)}.profile-conflict-row select{height:38px;margin:0;border-radius:7px}
      .physical-editor{margin-top:20px;padding:22px;background:var(--card-background-color,#fff);border-radius:20px}.physical-editor fieldset{border:0;padding:0;margin:0;min-width:0}.physical-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.physical-page{margin-top:20px;padding:18px;border:1px solid var(--divider-color,#ddd);border-radius:16px}.physical-key{display:grid;grid-template-columns:150px 160px minmax(180px,1fr) auto;gap:12px;align-items:center;padding:14px 0;border-bottom:1px solid var(--divider-color,#ddd)}.physical-key label{display:grid;gap:6px;font-size:12px}.physical-key input,.action-box input{width:100%;min-height:40px;padding:8px;background:var(--card-background-color,#fff);color:inherit;border:1px solid var(--divider-color,#ddd);border-radius:8px}.physical-status{padding:12px;background:var(--secondary-background-color,#eee);border-radius:10px;white-space:pre-wrap}@media(max-width:850px){.physical-key{grid-template-columns:1fr 1fr}.physical-toolbar button{height:auto;min-height:42px;padding:8px}.header-actions{flex-wrap:wrap}.layout-button{display:block!important}}
      @media(max-width:600px){.profile-conflict-row{grid-template-columns:1fr}}
      :host{display:block;min-height:100%;background:var(--primary-background-color,#f5f6f8);color:var(--primary-text-color,#17202a);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
      .apply-bar{flex-wrap:wrap}.apply-bar .profile-select{display:grid;gap:4px;min-width:min(100%,260px);font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.apply-bar .profile-select select{margin:0}.apply-bar>.small{flex:1 1 260px}
      *{box-sizing:border-box}button,select,textarea{font:inherit}main{max-width:1460px;margin:auto;padding:28px clamp(16px,3vw,44px) 64px}header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}h1{font-size:clamp(30px,4vw,48px);line-height:1;margin:5px 0 8px;letter-spacing:-.04em}header p{margin:0;color:var(--secondary-text-color,#68727d)}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.18em;color:var(--primary-color,#03a9f4)}.header-actions{display:flex;align-items:center;gap:10px}.battery,.live{height:40px;display:flex;align-items:center;gap:8px;padding:0 14px;border-radius:20px;background:var(--card-background-color,#fff);box-shadow:0 6px 18px #0000000a;font-weight:700}.live i{width:8px;height:8px;border-radius:50%;background:#26c281;box-shadow:0 0 0 5px #26c28122}.icon-button{width:40px;height:40px;border:0;border-radius:50%;background:var(--card-background-color,#fff);cursor:pointer;font-size:22px}.selectors{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:18px;background:var(--card-background-color,#fff);padding:20px 22px;border-radius:20px;box-shadow:0 12px 40px #0000000a}.selectors label{font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}select{width:100%;height:44px;margin-top:7px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.identity{display:grid;align-content:center;min-width:150px;padding-top:2px}.identity span,.identity small{font-size:11px;color:var(--secondary-text-color,#68727d)}.identity code{font-weight:800;font-size:14px;margin:3px 0}.quick-bind{display:grid;grid-template-columns:1fr minmax(220px,320px) auto;align-items:center;gap:16px;margin:18px 0;padding:18px 22px;background:color-mix(in srgb,var(--primary-color,#03a9f4) 8%,var(--card-background-color,#fff));border:1px solid color-mix(in srgb,var(--primary-color,#03a9f4) 24%,transparent);border-radius:16px}.quick-bind div{display:grid}.quick-bind span{font-size:12px;color:var(--secondary-text-color,#68727d);margin-top:3px}.quick-bind select{margin:0}.pages{display:flex;gap:8px;overflow:auto;margin:22px 0 16px;padding:5px}.pages button,.mode-tabs button{border:0;padding:10px 16px;border-radius:12px;background:transparent;color:var(--secondary-text-color,#68727d);font-weight:700;cursor:pointer;white-space:nowrap}.pages button.selected,.mode-tabs button.selected{background:var(--primary-color,#03a9f4);color:#fff;box-shadow:0 5px 14px color-mix(in srgb,var(--primary-color,#03a9f4) 30%,transparent)}.workspace{display:grid;grid-template-columns:minmax(340px,.9fr) minmax(400px,1.1fr);gap:26px;align-items:start}.remote-stage,.editor{background:var(--card-background-color,#fff);border-radius:24px;padding:26px 28px;box-shadow:0 14px 50px #0000000d}.remote-stage{display:grid;justify-items:center}.remote-shell{width:min(100%,420px);padding:18px;border-radius:42px;background:linear-gradient(145deg,#242a31,#0f1318);box-shadow:0 30px 55px #0005,inset 0 1px 1px #ffffff2b}.remote-top{height:62px;padding:4px 10px;color:#eaf0f4;display:flex;justify-content:space-between;align-items:center}.remote-top span{font-weight:800}.remote-top small{color:#8f9ba7}.screen{min-height:455px;padding:18px;border-radius:26px;background:linear-gradient(160deg,#edf2ed,#dce7df);color:#1f2924;box-shadow:inset 0 0 0 1px #ffffffaa,inset 0 8px 30px #8295891f}.screen-title{text-align:center;text-transform:uppercase;font-size:11px;letter-spacing:.16em;font-weight:900;color:#627168;margin-bottom:15px}.button-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.remote-button{position:relative;min-height:82px;padding:10px 5px 8px;border:1px solid #26392d14;border-radius:18px;background:#f7faf7;color:#27352d;display:grid;place-items:center;align-content:center;gap:4px;cursor:pointer;transition:transform .16s,box-shadow .16s,border-color .16s}.remote-button:hover{transform:translateY(-2px);box-shadow:0 8px 18px #354d3c1c}.remote-button.selected{border-color:#03a9f4;box-shadow:0 0 0 3px #03a9f429}.remote-button.pressed{animation:press .85s ease}.remote-button .glyph{font-size:23px;font-weight:500}.remote-button>span:not(.glyph){max-width:100%;font-size:9px;font-weight:800;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis}.remote-button i{position:absolute;top:8px;right:8px;width:7px;height:7px;border-radius:50%}.remote-button.preset i,.legend i.preset{background:#3c8cff}.remote-button.custom i,.legend i.custom{background:#25bd76}.remote-button.disabled i,.legend i.disabled{background:#ee5b66}.remote-button.none i,.legend i.none{background:#9aa4ad}.remote-footer{height:54px;display:flex;align-items:center;justify-content:center;gap:8px}.remote-footer span{width:5px;height:5px;border-radius:50%;background:#ffffff40}.legend{display:flex;flex-wrap:wrap;justify-content:center;gap:16px;margin-top:22px;color:var(--secondary-text-color,#68727d);font-size:11px}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:8px;height:8px;border-radius:50%}.editor{min-height:570px}.editor-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.editor h2{font-size:28px;margin:8px 0 2px;letter-spacing:-.025em}.status-pill{display:inline-flex;border-radius:10px;padding:5px 9px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.09em}.status-pill.preset{background:#3c8cff1c;color:#2373de}.status-pill.custom{background:#25bd761c;color:#15965a}.status-pill.disabled{background:#ee5b661c;color:#d93f4b}.status-pill.none{background:#9aa4ad22;color:#69747d}dl{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:20px 0;border:1px solid var(--divider-color,#e2e5e8);border-radius:14px;overflow:hidden}dl div{padding:12px 14px;border-bottom:1px solid var(--divider-color,#e2e5e8)}dl div:nth-last-child(-n+2){border-bottom:0}dt{font-size:10px;text-transform:uppercase;color:var(--secondary-text-color,#68727d);letter-spacing:.08em}dd{margin:4px 0 0;font-weight:700}.mode-tabs{display:flex;gap:4px;padding:4px;background:var(--secondary-background-color,#f1f3f5);border-radius:14px}.mode-tabs button{flex:1;font-size:12px;padding:10px}.mode-content{min-height:215px;margin-top:16px}.explanation{display:grid;gap:6px;padding:20px;border-radius:16px;background:#3c8cff12;border:1px solid #3c8cff33}.explanation span,.action-title span,.json-help{font-size:12px;color:var(--secondary-text-color,#68727d)}.explanation.danger{background:#ee5b6610;border-color:#ee5b6633}.action-box{display:grid;gap:14px}.action-title{display:flex;justify-content:space-between}#visualActionEditor{min-height:70px}.link-button{border:0;padding:0;background:none;color:var(--primary-color,#03a9f4);font-weight:800;cursor:pointer;text-decoration:underline}details{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px}summary{cursor:pointer;font-size:12px;color:var(--secondary-text-color,#68727d)}textarea{width:100%;min-height:160px;margin-top:10px;padding:12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--code-editor-background-color,#111820);color:var(--code-editor-text-color,#dce8ef);font:12px/1.5 ui-monospace,monospace;resize:vertical}textarea.invalid{border-color:#e74c3c;box-shadow:0 0 0 2px #e74c3c33}.save-row{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:20px}.save-row span{font-size:12px;color:#e74c3c}.primary,.secondary{height:42px;padding:0 18px;border:1px solid transparent;border-radius:12px;font-weight:700;white-space:nowrap;cursor:pointer;transition:background .15s,box-shadow .15s,transform .12s,border-color .15s}
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
      .action.danger:hover{background:#fdf2f3;border-color:#e4939b}.reachability{margin:10px 0;padding:10px 14px;border-radius:12px;font-size:13px;background:var(--secondary-background-color,#f1f3f5)}.reachability.full{background:#25bd7614}.reachability.conditional{background:#f0a52014}.reachability.none{background:#ee5b6614}.apply-bar{display:flex;align-items:center;gap:12px;margin:18px 0;padding:14px 18px;border-radius:14px;background:var(--card-background-color,#fff);box-shadow:0 6px 18px #0000000a;font-size:13px}.apply-bar.dirty{background:color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff));border:1px solid color-mix(in srgb,var(--primary-color,#03a9f4) 28%,transparent)}.apply-bar .spacer{flex:1}.key-editor{display:grid;gap:14px;margin:20px 0;padding:18px 20px;border-radius:16px;background:var(--secondary-background-color,#f1f3f5)}.key-editor label{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.key-editor select{margin:0}.key-editor textarea{min-height:70px;margin-top:4px}.key-editor details.catalog{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px;display:grid;gap:10px}.key-editor details.catalog>summary{font-weight:700}.key-editor input[type=search]{height:40px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.key-editor select[size]{height:auto;padding:4px}.key-editor .warning{color:#d73a46}.add-remote{display:grid;gap:12px;margin:14px 0;padding:18px;border-radius:18px;background:var(--card-background-color,#fff);box-shadow:0 12px 40px #0000000a}.add-remote label{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.add-remote label.inline{display:flex;align-items:center;gap:8px}.add-remote select{margin:0}.add-remote select[size]{height:auto;padding:4px}.add-remote input[type=text],.add-remote input[type=search]{height:44px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.add-remote .mode-tabs button:disabled{opacity:.4;cursor:default}.add-remote .small{margin:0}.add-remote .warning{color:#d73a46}.button-picks{display:flex;flex-wrap:wrap;gap:6px 14px}.button-picks label{font-weight:600;font-size:11px}.diagnostics code{font:11px/1.5 ui-monospace,monospace}.diagnostics table{margin-top:10px}.key-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:2px}.stage-actions{display:flex;flex-wrap:wrap;gap:10px;align-items:center;justify-content:center;margin-top:18px}@keyframes spin{to{transform:rotate(360deg)}}@keyframes press{0%,100%{transform:scale(1)}20%{transform:scale(.9);background:#c9f6dc;box-shadow:0 0 0 7px #25bd7630}}
      .device-wrap{width:min(100%,360px)}
      .device{width:100%;height:auto;filter:drop-shadow(0 14px 26px #0000002b)}
      .device .shell{stroke:#d2d5da;stroke-width:1.2}
      .device .glass{fill:#090a0c}
      .device .glass-edge{fill:none;stroke:#ffffff29;stroke-width:1.2;stroke-linecap:round}
      .scr-scroll{height:242px;overflow-y:auto;overscroll-behavior:contain;touch-action:pan-y;
        -webkit-overflow-scrolling:touch;padding:48px 13px 10px;scrollbar-width:thin;
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
      .menu-names{display:grid;gap:10px;margin-bottom:16px}
      .menu-names p{margin:0}
      .menu-name-form{display:flex;align-items:end;gap:8px}
      .menu-name-form label{display:grid;flex:1;min-width:0;gap:4px;font-size:12px;font-weight:700}
      .menu-name-form input{min-width:0;padding:8px;border:1px solid var(--divider-color,#dfe3e8);border-radius:8px;background:var(--card-background-color,#fff);color:inherit}
      .glyph-picker summary{cursor:pointer;line-height:32px}
      .glyph-picker summary .native-glyph{display:inline-block;vertical-align:middle;margin:0 8px 0 5px;padding:4px;background:#171c23;border-radius:6px}
      .glyph-picker[open] summary{margin-bottom:10px}
      .glyph-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(42px,1fr));gap:6px;max-height:238px;overflow:auto;margin-top:10px;padding:2px}
      .glyph-grid button{display:grid;place-items:center;min-height:42px;padding:4px;background:#171c23;border:1px solid #657181;border-radius:7px}
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
      .screen-keys{margin-top:16px}.sk-title{font-size:11px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--secondary-text-color,#68727d);margin-bottom:8px}
      .stage-actions{width:100%;justify-content:flex-start}.page-move{display:flex;align-items:center;gap:7px;margin-left:auto;color:var(--secondary-text-color,#68727d);font-size:12px;font-weight:700}.page-move select{width:auto;min-width:125px;height:36px;margin:0;border-radius:7px}.page-capacity{margin-left:auto}
      .row-order{display:flex;align-items:center;gap:6px}.row-order span{margin-right:auto;color:var(--secondary-text-color,#68727d);font-size:12px;font-weight:700}.row-order .secondary.compact{width:36px;padding:0;font-size:17px}
      .row-order .secondary.compact:disabled{opacity:.35}
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
