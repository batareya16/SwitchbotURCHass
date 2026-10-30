const DOMAIN = "switchbot_urc";

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
    this._physicalSources = [];
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
    let importError = null;
    try {
      const result = await this._hass.callWS({
        type: `${DOMAIN}/studio/physical/import`, entry_id: this._entryId });
      adopted = result?.imported || 0;
    } catch (error) { importError = error?.message || String(error); }
    this._physical = null;
    this._physicalBusy = false;
    await this._load();
    if (importError && !this._error) this._error = importError;
    if (!importError && adopted) this._notify(`${adopted} remote(s) picked up from the device`);
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

  _page() {
    const remote = this._remote();
    return remote?.pages.find((item) => item.index === this._pageIndex) || remote?.pages[0] || null;
  }

  _button() {
    return this._page()?.buttons.find((item) => item.button_id === this._buttonId) || null;
  }

  _ensureLayout() {
    if (!this._entryId || !this._remoteId) return;
    if (!this._remote()?.layout_editable) return;
    if (this._physical && this._physicalFor === this._remoteId) return;
    this._physicalFor = this._remoteId;
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
    const pages = this._remote()?.pages || [];
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

  _buttonIcon(button) {
    const label = button.label.toUpperCase();
    if (label.includes("ON")) return "⏻";
    if (label.includes("OFF")) return "○";
    if (label.includes("BRIGHT") || label.includes("UP")) return "＋";
    if (label.includes("DARK") || label.includes("DOWN")) return "−";
    if (label.includes("WARM") || label.includes("LEFT")) return "‹";
    if (label.includes("COOL") || label.includes("RIGHT")) return "›";
    if (label.includes("COLOR")) return "●";
    if (label.includes("FAN") || label.includes("SPEED")) return "✣";
    if (label.includes("MUTE")) return "×";
    return button.label.replace(/^Button /i, "").slice(0, 3);
  }

  _renderStage(page) {
    const isMain = (page?.index ?? 0) === 0;
    return isMain ? this._renderFace(page) : this._renderGrid(page);
  }

  _renderGrid(page) {
    const buttons = page?.buttons || [];
    if (!buttons.length) return `<div class="empty small">No buttons on this page.</div>`;
    return `<div class="button-grid">${buttons.map((item) => {
      const [status, statusLabel] = this._status(item);
      return `<button class="remote-button ${status} ${item.button_id === this._buttonId ? "selected" : ""} ${this._isActiveButton(item) ? "pressed" : ""}" data-button="${escapeHtml(item.button_id)}" title="${escapeHtml(statusLabel)} · ${escapeHtml(item.label)}"><span class="glyph">${escapeHtml(this._buttonIcon(item))}</span><span>${escapeHtml(item.label)}</span><i></i></button>`;
    }).join("")}</div>`;
  }

  _faceSlot(byPos, tag, glyph, cls = "") {
    const button = byPos[tag];
    if (!button) {
      return `<div class="face-slot ghost ${cls}" title="${tag} — not used by this remote"><span class="fg">${glyph}</span></div>`;
    }
    const [status, statusLabel] = this._status(button);
    const selected = button.button_id === this._buttonId ? "selected" : "";
    const pressed = this._isActiveButton(button) ? "pressed" : "";
    return `<button class="face-slot ${status} ${cls} ${selected} ${pressed}" data-button="${escapeHtml(button.button_id)}" title="${escapeHtml(statusLabel)} · ${escapeHtml(button.label)}"><span class="fg">${glyph}</span><span class="cap">${escapeHtml(button.label)}</span><i></i></button>`;
  }

  _renderFace(page) {
    const byPos = {};
    (page?.buttons || []).forEach((item) => {
      byPos[String(item.position || "").toUpperCase()] = item;
    });
    const slot = (tag, glyph, cls) => this._faceSlot(byPos, tag, glyph, cls);
    const face = `
      <div class="face">
        <div class="prow">${slot("ON", "⏻", "pill")}${slot("OFF", "○", "pill")}</div>
        <div class="dpad">
          ${slot("UP", "▲", "dp up")}
          ${slot("LEFT", "◀", "dp left")}
          ${slot("OK", "OK", "dp ok")}
          ${slot("RIGHT", "▶", "dp right")}
          ${slot("DOWN", "▼", "dp down")}
        </div>
        <div class="prow trio">${slot("BACK", "↩", "round")}${slot("KATA", "⚡", "round red")}${slot("HOME", "⌂", "round")}</div>
        <div class="prow bottom">
          <div class="vstack">${slot("VOLADD", "＋", "wide")}${slot("VOLDEL", "−", "wide")}</div>
          ${slot("SOUNDOFF", "⊗", "round")}
          <div class="vstack">${slot("CHUP", "▲", "wide")}${slot("CHDOWN", "▼", "wide")}</div>
        </div>
      </div>`;
    const abcd = ["A", "B", "C", "D"].filter((tag) => byPos[tag]);
    const abcdRow = abcd.length
      ? `<div class="screen-keys"><div class="sk-title">Screen keys</div><div class="sk-grid">${abcd.map((tag) => slot(tag, tag, "sk")).join("")}</div></div>`
      : "";
    const known = new Set(["ON", "OFF", "UP", "DOWN", "LEFT", "RIGHT", "OK", "BACK", "HOME", "KATA", "SOUNDOFF", "VOLADD", "VOLDEL", "CHUP", "CHDOWN", "A", "B", "C", "D"]);
    const extras = (page?.buttons || []).filter((item) => !known.has(String(item.position || "").toUpperCase()));
    const extrasRow = extras.length
      ? `<div class="screen-keys"><div class="sk-title">Other buttons</div><div class="button-grid">${extras.map((item) => {
          const [status, statusLabel] = this._status(item);
          return `<button class="remote-button ${status} ${item.button_id === this._buttonId ? "selected" : ""} ${this._isActiveButton(item) ? "pressed" : ""}" data-button="${escapeHtml(item.button_id)}" title="${escapeHtml(statusLabel)} · ${escapeHtml(item.label)}"><span class="glyph">${escapeHtml(this._buttonIcon(item))}</span><span>${escapeHtml(item.label)}</span><i></i></button>`;
        }).join("")}</div></div>`
      : "";
    return face + abcdRow + extrasRow;
  }

  _render() {
    if (!this.shadowRoot) return;
    const entry = this._entry();
    const remote = this._remote();
    const page = this._page();
    const button = this._button();
    const entries = this._entries();
    const lights = Object.values(this._hass?.states || {})
      .filter((state) => state.entity_id.startsWith("light."))
      .sort((a, b) => (a.attributes.friendly_name || a.entity_id).localeCompare(b.attributes.friendly_name || b.entity_id));
    const boundLight = remote?.binding?.entity_id || "";

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
            ${entry?.battery != null ? `<div class="battery"><span>▰</span>${escapeHtml(entry.battery)}%</div>` : ""}
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
          ${this._renderApplyBar()}
          ${remote && !this._physical ? `
            <section class="quick-bind">
              <div><b>Quick bind</b><span>Apply a complete light preset; individual buttons can override it.</span></div>
              <select id="lightSelect"><option value="">Choose a light…</option>${lights.map((state) => `<option value="${escapeHtml(state.entity_id)}" ${state.entity_id === boundLight ? "selected" : ""}>${escapeHtml(state.attributes.friendly_name || state.entity_id)}</option>`).join("")}</select>
              <button class="secondary" id="quickBind">Apply preset</button>
            </section>
            <nav class="pages">${remote.pages.map((item) => `<button data-page="${item.index}" class="${item.index === page?.index ? "selected" : ""}">${escapeHtml(item.name)}</button>`).join("")}</nav>
            <div class="workspace">
              <section class="remote-stage">
                <div class="remote-shell">
                  <div class="remote-top"><span>${escapeHtml(remote.name)}</span><small>${escapeHtml(page?.name || "")}</small></div>
                  <div class="screen">
                    <div class="screen-title">${escapeHtml(page?.name || "Main")}</div>
                    ${this._renderStage(page)}
                  </div>
                  <div class="remote-footer"><span></span><span></span><span></span></div>
                </div>
                <div class="legend"><span><i class="preset"></i>Quick bind</span><span><i class="custom"></i>Custom</span><span><i class="disabled"></i>Disabled</span><span><i class="none"></i>Empty</span></div>
              </section>
              <aside class="editor">${button ? this._editor(button, remote) : `<div class="empty small">Choose a button.</div>`}</aside>
            </div>
          ` : this._physical ? "" : `<div class="empty"><b>No locally managed remotes.</b><br>Add a remote or import an existing HID remote.</div>`}
        ` : ""}
      </main>`;
    this._wireEvents();
    this._mountActionSelector();
    this._ensureLayout();
  }

  async _openPhysical() {
    clearTimeout(this._activeTimer);
    try {
      const result = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/get`,
        entry_id: this._entryId, remote_id: this._remoteId });
      this._physical = result.layout;
      this._physicalBackup = result.backup;
      this._physicalSources = result.ir_sources;
      this._physicalFunctions = result.functions || [];
      this._physicalBaseline = structuredClone(result.layout);
      this._physicalStatus = result.status || "";
      this._error = null;
    } catch (error) {
      // No editable layout for this remote: the Home Assistant mapping still works.
      this._physical = null;
      this._physicalBaseline = null;
    }
    // The remote's own table is read separately: it is diagnostic, so a failure here must not
    // keep the layout editor closed.
    try {
      this._deviceTable = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/table`,
        entry_id: this._entryId });
    } catch (error) { this._deviceTable = { error: error?.message || String(error) }; }
    this._render();
  }

  _renderDeviceTable() {
    const table = this._deviceTable;
    if (!table) return "";
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
    </div>`;
  }

  _physicalChanges() {
    // A cheap structural comparison is enough to know whether anything still has to be
    // written; the apply call sends the whole layout anyway.
    if (!this._physical || !this._physicalBaseline) return 0;
    const flat = (draft) => draft.pages.flatMap((page) => page.buttons.map(
      (key) => `${page.index}:${key.index}:${key.transport}:${key.function ?? ""}:${key.code_hex ?? ""}`));
    const before = flat(this._physicalBaseline);
    const after = flat(this._physical);
    const removed = before.filter((item) => !after.includes(item)).length;
    const added = after.filter((item) => !before.includes(item)).length;
    return Math.max(removed, added);
  }

  _wireKeyEditor(root) {
    const button = this._button();
    const found = button ? this._draftKey(button) : null;
    if (!found) return;
    const { page, key } = found;
    const kind = this._physical.kind;

    root.querySelector('[data-key-field="transport"]')?.addEventListener("change", (event) => {
      key.transport = event.target.value;
      this._render();
    });

    root.querySelector('[data-key-field="function"]')?.addEventListener("change", (event) => {
      if (event.target.value === "page") {
        // "Open a custom page" turns this Main key into the link for a new, empty page.
        const index = key.index + 1;
        this._physical.pages.push({ index, buttons: [] });
        this._physical.pages.sort((a, b) => a.index - b.index);
        page.buttons = page.buttons.filter((item) => item.index !== key.index);
        this._pageIndex = this._physical.pages.findIndex((item) => item.index === index);
        this._buttonId = null;
        this._physicalStatus = "";
        this._render();
        return;
      }
      key.function = Number(event.target.value);
      this._render();
    });

    root.querySelector('[data-key-field="ir_source"]')?.addEventListener("change", (event) => {
      if (event.target.value === "") return;
      key.code_hex = this._physicalSources[Number(event.target.value)].code_hex;
      this._render();
    });

    root.getElementById("removeKey")?.addEventListener("click", () => {
      page.buttons = page.buttons.filter((item) => item !== key);
      if (page.index && kind === "native") page.buttons.forEach((item, index) => { item.index = index; });
      this._buttonId = null;
      this._render();
    });

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
      }
      this._render();
    });

    root.getElementById("removePage")?.addEventListener("click", () => {
      this._physical.pages = this._physical.pages.filter((item) => item !== page);
      this._pageIndex = 0;
      this._buttonId = null;
      this._render();
    });
  }

  _wirePhysical() {
    const root = this.shadowRoot;
    this._wireKeyEditor(root);
    root.getElementById("physicalDiscard")?.addEventListener("click", () => {
      this._physical = structuredClone(this._physicalBaseline);
      this._physicalStatus = "";
      this._render();
    });
    root.getElementById("physicalRestore")?.addEventListener("click", () => {
      this._physical = structuredClone(this._physicalBackup.layout);
      this._physicalStatus = "Previous layout loaded. Apply it to restore the physical remote.";
      this._render();
    });
    const newKey = (index) => ({ index, transport: this._physical.kind === "native" ? "native" : this._physical.kind === "hid" ? "hid" : "ir", function: this._physical.kind === "native" ? 5 : 115, code_hex: "" });
  }

  _draftKey(button) {
    const page = this._physical?.pages?.find((item) => item.index === button.button_page);
    const key = page?.buttons?.find((item) => item.index === button.button_index);
    return key ? { page, key } : null;
  }

  _renderKeyEditor(button) {
    if (!this._physical) return "";
    const found = this._draftKey(button);
    if (!found) return "";
    const { key } = found;
    const kind = this._physical.kind;
    const transports = kind === "native" ? ["native"] : kind === "hid" ? ["hid", "ir"] : ["stored", "ir"];
    const label = { stored: "Original IR command", native: "Native / bridge", hid: "HID", ir: "IR" };
    const usedPages = this._physical.pages.filter((page) => page.index).map((page) => page.index);
    // Only a Main A-D position can open a page, and only if that page does not exist yet.
    const canOpenPage = button.button_page === 0 && key.index <= 3 && !usedPages.includes(key.index + 1);
    return `<div class="action-box key-editor">
      <div class="action-title"><b>On the remote</b><span>what this key is, not what Home Assistant does</span></div>
      ${transports.length > 1 ? `<label>Command type<select data-key-field="transport">${
        transports.map((item) => `<option value="${item}" ${key.transport === item ? "selected" : ""}>${label[item]}</option>`).join("")
      }</select></label>` : ""}
      ${["hid", "native"].includes(key.transport) ? `<label>Function<select data-key-field="function">${
        (this._physicalFunctions || []).map((item) => `<option value="${item.value}" ${key.function === item.value ? "selected" : ""}>${escapeHtml(item.label)}</option>`).join("")
      }${canOpenPage ? `<option value="page">Open a custom page…</option>` : ""}</select></label>` : ""}
      ${key.transport === "ir" ? `<label>IR code<select data-key-field="ir_source"><option value="">Choose a saved IR button…</option>${
        (this._physicalSources || []).map((source, index) => `<option value="${index}" ${key.code_hex === source.code_hex ? "selected" : ""}>${escapeHtml(source.label)}</option>`).join("")
      }</select></label>` : ""}
      <div class="key-actions">
        ${button.button_page ? `<button class="secondary compact" id="removePage">Delete this page</button>` : ""}
        <button class="secondary compact" id="addKey">Add a button to this page</button>
        <button class="secondary compact" id="removeKey">Remove this button</button>
      </div>
    </div>`;
  }

  _editor(button, remote) {
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
      <div class="action-box">
        <label>Page name in Home Assistant<input id="pageLabel" maxlength="80" value="${escapeHtml(this._page()?.name)}"></label>
        <label>Button name in Home Assistant<input id="buttonLabel" maxlength="80" value="${escapeHtml(button.label)}"></label>
      </div>
      <div class="mode-tabs">
        <button data-mode="preset" class="${this._mode === "preset" ? "selected" : ""}">Quick bind</button>
        <button data-mode="actions" class="${this._mode === "actions" ? "selected" : ""}">Custom actions</button>
        <button data-mode="disabled" class="${this._mode === "disabled" ? "selected" : ""}">Disabled</button>
      </div>
      <div class="mode-content">
        ${this._mode === "preset" ? `<div class="explanation"><b>Use the whole-remote preset.</b><span>${button.preset_action ? `This button will ${escapeHtml(button.preset_action.replaceAll("_", " "))}.` : "No Quick-bind action currently matches this button."}</span></div>` : ""}
        ${this._mode === "disabled" ? `<div class="explanation danger"><b>Ignore this button.</b><span>Physical presses will be received but no Home Assistant action will run.</span></div>` : ""}
        ${this._mode === "actions" ? `<div class="action-box"><div class="action-title"><b>Home Assistant actions</b><span>${escapeHtml(actionSummary)}</span></div><div id="visualActionEditor"></div><details><summary>Advanced JSON fallback</summary><textarea id="actionsJson" spellcheck="false">${escapeHtml(JSON.stringify(this._draftActions, null, 2))}</textarea><div class="json-help">This uses standard Home Assistant script action syntax.</div></details></div>` : ""}
      </div>
      <div class="save-row"><span id="saveStatus"></span><button class="primary" id="saveButton" ${
        this._mode === "actions" && !this._jsonValid ? "disabled" : ""}>${
        this._physicalChanges() ? "Save and write to remote" : "Save"}</button></div>`;
  }

  _wireEvents() {
    const root = this.shadowRoot;
    for (const id of ["entrySelect", "remoteSelect", "refresh", "editLayout"]) {
      const el = root.getElementById(id);
      if (el) el.disabled = this._physicalBusy;
    }
    if (root.getElementById("refresh") && this._physical) root.getElementById("refresh").disabled = true;
    root.getElementById("refresh")?.addEventListener("click", () => this._refresh());
    root.getElementById("editLayout")?.addEventListener("click", () => {
      if (!this._physicalBusy) this._openPhysical();
    });
    this._wirePhysical();
    root.getElementById("entrySelect")?.addEventListener("change", (event) => {
      this._entryId = event.target.value;
      this._physical = null;
      this._remoteId = null;
      this._buttonId = null;
      this._normalizeSelection();
      this._render();
    });
    root.getElementById("remoteSelect")?.addEventListener("change", (event) => {
      this._remoteId = event.target.value;
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
    root.querySelectorAll("[data-button]").forEach((element) =>
      element.addEventListener("click", () => {
        const button = this._page()?.buttons.find((item) => item.button_id === element.dataset.button);
        this._selectButton(button);
      }),
    );
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
    selector.value = structuredClone(this._draftActions);
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

      // Names first: they are local and cheap, and a later failure should not lose them.
      if (page) {
        const updated = await this._hass.callWS({
          type: `${DOMAIN}/studio/save_labels`, entry_id: this._entryId, remote_id: this._remoteId,
          labels: {
            [`page_${page.index}`]: root.getElementById("pageLabel")?.value ?? page.name,
            [button.button_id]: root.getElementById("buttonLabel")?.value ?? button.label,
          },
        });
        this._replaceEntry(updated);
      }

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
        this._physicalBusy = true;
        if (status) status.textContent = "Writing the layout to the remote…";
        this._render();
        const result = await this._hass.callWS({ type: `${DOMAIN}/studio/physical/apply`,
          entry_id: this._entryId, remote_id: this._remoteId, layout: this._physical });
        this._physicalStatus = result.status;
        this._physicalBackup = result.backup;
        this._physicalBaseline = structuredClone(this._physical);
        this._physicalBusy = false;
        await this._load();
      }

      this._dirty = false;
      this._jsonValid = true;
      this._error = null;
      this._notify(layoutChanges ? "Saved and written to the remote" : "Saved");
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
      .physical-editor{margin-top:20px;padding:22px;background:var(--card-background-color,#fff);border-radius:20px}.physical-editor fieldset{border:0;padding:0;margin:0;min-width:0}.physical-toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap}.physical-page{margin-top:20px;padding:18px;border:1px solid var(--divider-color,#ddd);border-radius:16px}.physical-key{display:grid;grid-template-columns:150px 160px minmax(180px,1fr) auto;gap:12px;align-items:center;padding:14px 0;border-bottom:1px solid var(--divider-color,#ddd)}.physical-key label{display:grid;gap:6px;font-size:12px}.physical-key input,.action-box input{width:100%;min-height:40px;padding:8px;background:var(--card-background-color,#fff);color:inherit;border:1px solid var(--divider-color,#ddd);border-radius:8px}.physical-status{padding:12px;background:var(--secondary-background-color,#eee);border-radius:10px;white-space:pre-wrap}@media(max-width:850px){.physical-key{grid-template-columns:1fr 1fr}.physical-toolbar button{height:auto;min-height:42px;padding:8px}.header-actions{flex-wrap:wrap}.layout-button{display:block!important}}
      :host{display:block;min-height:100%;background:var(--primary-background-color,#f5f6f8);color:var(--primary-text-color,#17202a);font-family:var(--paper-font-body1_-_font-family,system-ui,sans-serif)}
      *{box-sizing:border-box}button,select,textarea{font:inherit}main{max-width:1460px;margin:auto;padding:28px clamp(16px,3vw,44px) 64px}header{display:flex;align-items:flex-start;justify-content:space-between;gap:20px;margin-bottom:24px}h1{font-size:clamp(30px,4vw,48px);line-height:1;margin:5px 0 8px;letter-spacing:-.04em}header p{margin:0;color:var(--secondary-text-color,#68727d)}.eyebrow{font-size:11px;font-weight:800;letter-spacing:.18em;color:var(--primary-color,#03a9f4)}.header-actions{display:flex;align-items:center;gap:10px}.battery,.live{height:40px;display:flex;align-items:center;gap:8px;padding:0 14px;border-radius:20px;background:var(--card-background-color,#fff);box-shadow:0 6px 18px #0000000a;font-weight:700}.live i{width:8px;height:8px;border-radius:50%;background:#26c281;box-shadow:0 0 0 5px #26c28122}.icon-button{width:40px;height:40px;border:0;border-radius:50%;background:var(--card-background-color,#fff);cursor:pointer;font-size:22px}.selectors{display:grid;grid-template-columns:minmax(220px,1fr) minmax(220px,1fr) auto;gap:14px;background:var(--card-background-color,#fff);padding:18px;border-radius:20px;box-shadow:0 12px 40px #0000000a}.selectors label{font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}select{width:100%;height:44px;margin-top:7px;padding:0 12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:11px;background:var(--card-background-color,#fff);color:inherit}.identity{display:grid;align-content:center;min-width:150px}.identity span,.identity small{font-size:11px;color:var(--secondary-text-color,#68727d)}.identity code{font-weight:800;font-size:14px;margin:3px 0}.quick-bind{display:grid;grid-template-columns:1fr minmax(220px,320px) auto;align-items:center;gap:14px;margin:14px 0;padding:14px 18px;background:color-mix(in srgb,var(--primary-color,#03a9f4) 8%,var(--card-background-color,#fff));border:1px solid color-mix(in srgb,var(--primary-color,#03a9f4) 24%,transparent);border-radius:16px}.quick-bind div{display:grid}.quick-bind span{font-size:12px;color:var(--secondary-text-color,#68727d);margin-top:3px}.quick-bind select{margin:0}.pages{display:flex;gap:8px;overflow:auto;margin:20px 0 14px;padding:4px}.pages button,.mode-tabs button{border:0;padding:10px 16px;border-radius:12px;background:transparent;color:var(--secondary-text-color,#68727d);font-weight:700;cursor:pointer;white-space:nowrap}.pages button.selected,.mode-tabs button.selected{background:var(--primary-color,#03a9f4);color:#fff;box-shadow:0 5px 14px color-mix(in srgb,var(--primary-color,#03a9f4) 30%,transparent)}.workspace{display:grid;grid-template-columns:minmax(340px,.9fr) minmax(400px,1.1fr);gap:22px;align-items:start}.remote-stage,.editor{background:var(--card-background-color,#fff);border-radius:24px;padding:24px;box-shadow:0 14px 50px #0000000d}.remote-stage{display:grid;justify-items:center}.remote-shell{width:min(100%,420px);padding:18px;border-radius:42px;background:linear-gradient(145deg,#242a31,#0f1318);box-shadow:0 30px 55px #0005,inset 0 1px 1px #ffffff2b}.remote-top{height:62px;padding:4px 10px;color:#eaf0f4;display:flex;justify-content:space-between;align-items:center}.remote-top span{font-weight:800}.remote-top small{color:#8f9ba7}.screen{min-height:455px;padding:18px;border-radius:26px;background:linear-gradient(160deg,#edf2ed,#dce7df);color:#1f2924;box-shadow:inset 0 0 0 1px #ffffffaa,inset 0 8px 30px #8295891f}.screen-title{text-align:center;text-transform:uppercase;font-size:11px;letter-spacing:.16em;font-weight:900;color:#627168;margin-bottom:15px}.button-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.remote-button{position:relative;min-height:82px;padding:10px 5px 8px;border:1px solid #26392d14;border-radius:18px;background:#f7faf7;color:#27352d;display:grid;place-items:center;align-content:center;gap:4px;cursor:pointer;transition:transform .16s,box-shadow .16s,border-color .16s}.remote-button:hover{transform:translateY(-2px);box-shadow:0 8px 18px #354d3c1c}.remote-button.selected{border-color:#03a9f4;box-shadow:0 0 0 3px #03a9f429}.remote-button.pressed{animation:press .85s ease}.remote-button .glyph{font-size:23px;font-weight:500}.remote-button>span:not(.glyph){max-width:100%;font-size:9px;font-weight:800;text-transform:uppercase;overflow:hidden;text-overflow:ellipsis}.remote-button i{position:absolute;top:8px;right:8px;width:7px;height:7px;border-radius:50%}.remote-button.preset i,.legend i.preset{background:#3c8cff}.remote-button.custom i,.legend i.custom{background:#25bd76}.remote-button.disabled i,.legend i.disabled{background:#ee5b66}.remote-button.none i,.legend i.none{background:#9aa4ad}.remote-footer{height:54px;display:flex;align-items:center;justify-content:center;gap:8px}.remote-footer span{width:5px;height:5px;border-radius:50%;background:#ffffff40}.legend{display:flex;flex-wrap:wrap;justify-content:center;gap:14px;margin-top:18px;color:var(--secondary-text-color,#68727d);font-size:11px}.legend span{display:flex;align-items:center;gap:5px}.legend i{width:8px;height:8px;border-radius:50%}.editor{min-height:570px}.editor-head{display:flex;justify-content:space-between;gap:12px;align-items:flex-start}.editor h2{font-size:28px;margin:8px 0 2px;letter-spacing:-.025em}.status-pill{display:inline-flex;border-radius:10px;padding:5px 9px;font-size:10px;font-weight:900;text-transform:uppercase;letter-spacing:.09em}.status-pill.preset{background:#3c8cff1c;color:#2373de}.status-pill.custom{background:#25bd761c;color:#15965a}.status-pill.disabled{background:#ee5b661c;color:#d93f4b}.status-pill.none{background:#9aa4ad22;color:#69747d}dl{display:grid;grid-template-columns:1fr 1fr;gap:0;margin:20px 0;border:1px solid var(--divider-color,#e2e5e8);border-radius:14px;overflow:hidden}dl div{padding:12px 14px;border-bottom:1px solid var(--divider-color,#e2e5e8)}dl div:nth-last-child(-n+2){border-bottom:0}dt{font-size:10px;text-transform:uppercase;color:var(--secondary-text-color,#68727d);letter-spacing:.08em}dd{margin:4px 0 0;font-weight:700}.mode-tabs{display:flex;gap:4px;padding:4px;background:var(--secondary-background-color,#f1f3f5);border-radius:14px}.mode-tabs button{flex:1;font-size:12px;padding:10px}.mode-content{min-height:215px;margin-top:16px}.explanation{display:grid;gap:6px;padding:20px;border-radius:16px;background:#3c8cff12;border:1px solid #3c8cff33}.explanation span,.action-title span,.json-help{font-size:12px;color:var(--secondary-text-color,#68727d)}.explanation.danger{background:#ee5b6610;border-color:#ee5b6633}.action-box{display:grid;gap:14px}.action-title{display:flex;justify-content:space-between}#visualActionEditor{min-height:70px}.link-button{border:0;padding:0;background:none;color:var(--primary-color,#03a9f4);font-weight:800;cursor:pointer;text-decoration:underline}details{border-top:1px solid var(--divider-color,#e2e5e8);padding-top:10px}summary{cursor:pointer;font-size:12px;color:var(--secondary-text-color,#68727d)}textarea{width:100%;min-height:160px;margin-top:10px;padding:12px;border:1px solid var(--divider-color,#dfe3e8);border-radius:12px;background:var(--code-editor-background-color,#111820);color:var(--code-editor-text-color,#dce8ef);font:12px/1.5 ui-monospace,monospace;resize:vertical}textarea.invalid{border-color:#e74c3c;box-shadow:0 0 0 2px #e74c3c33}.save-row{display:flex;justify-content:flex-end;align-items:center;gap:12px;margin-top:20px}.save-row span{font-size:12px;color:#e74c3c}.primary,.secondary{height:42px;padding:0 18px;border:0;border-radius:12px;font-weight:800;cursor:pointer}.primary{background:var(--primary-color,#03a9f4);color:#fff}.secondary{background:var(--secondary-background-color,#edf0f3);color:var(--primary-text-color,#17202a)}.secondary.compact{height:36px}.primary:disabled{opacity:.5}.error,.loading,.empty{padding:22px;border-radius:16px;background:var(--card-background-color,#fff);margin:16px 0}.error{background:#ee5b6613;color:#d73a46}.loading{display:flex;gap:10px;align-items:center}.loading span{width:14px;height:14px;border:2px solid #ccc;border-top-color:var(--primary-color,#03a9f4);border-radius:50%;animation:spin .7s linear infinite}.empty{text-align:center;color:var(--secondary-text-color,#68727d);line-height:1.7}.empty.small{margin:120px 0}.device-table{margin:10px 0}.device-table table{width:100%;border-collapse:collapse;margin:8px 0;font-size:12px}.device-table th{text-align:left;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--secondary-text-color,#68727d);padding:4px 6px}.device-table td{padding:4px 6px;border-top:1px solid var(--divider-color,#e2e5e8)}.device-table .small{font-size:11px;color:var(--secondary-text-color,#68727d);margin:4px 0}.device-table .warning{color:#d73a46}.apply-bar{display:flex;align-items:center;gap:10px;margin:14px 0;padding:12px 16px;border-radius:14px;background:var(--card-background-color,#fff);box-shadow:0 6px 18px #0000000a;font-size:13px}.apply-bar.dirty{background:color-mix(in srgb,var(--primary-color,#03a9f4) 10%,var(--card-background-color,#fff));border:1px solid color-mix(in srgb,var(--primary-color,#03a9f4) 28%,transparent)}.apply-bar .spacer{flex:1}.key-editor{margin:16px 0;padding:16px;border-radius:16px;background:var(--secondary-background-color,#f1f3f5)}.key-editor label{display:grid;gap:4px;font-size:12px;font-weight:700;color:var(--secondary-text-color,#68727d)}.key-editor select{margin:0}.key-actions{display:flex;flex-wrap:wrap;gap:8px;margin-top:4px}@keyframes spin{to{transform:rotate(360deg)}}@keyframes press{0%,100%{transform:scale(1)}20%{transform:scale(.9);background:#c9f6dc;box-shadow:0 0 0 7px #25bd7630}}
      .face{display:grid;justify-items:center;gap:4px}.prow{display:flex;gap:10px;justify-content:center;width:100%;margin:8px 0}.prow.trio{gap:22px;margin:14px 0}.prow.bottom{align-items:center;justify-content:space-between;padding:0 14px}.vstack{display:flex;flex-direction:column;gap:6px}
      .face-slot{position:relative;border:1px solid #26392d18;border-radius:14px;background:#f7faf7;color:#27352d;display:grid;place-items:center;gap:2px;cursor:pointer;min-height:48px;transition:transform .16s,box-shadow .16s,border-color .16s}.face-slot:hover{transform:translateY(-2px);box-shadow:0 8px 18px #354d3c1c}.face-slot .fg{font-size:19px;line-height:1}.face-slot .cap{max-width:100%;font-size:8px;font-weight:800;text-transform:uppercase;letter-spacing:.02em;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
      .face-slot.pill{flex:1;border-radius:999px;min-height:42px}.face-slot.round{width:46px;height:46px;border-radius:50%}.face-slot.red{background:#ee5b6618;border-color:#ee5b6655;color:#d93f4b}.face-slot.wide{width:46px;height:30px;min-height:0;border-radius:15px}
      .dpad{display:grid;grid-template-columns:repeat(3,54px);grid-template-rows:repeat(3,54px);gap:6px;justify-content:center;margin:10px 0}.face-slot.up{grid-area:1/2}.face-slot.left{grid-area:2/1}.face-slot.ok{grid-area:2/2;border-radius:50%}.face-slot.right{grid-area:2/3}.face-slot.down{grid-area:3/2}
      .face-slot.ghost{background:#26392d08;border-style:dashed;border-color:#26392d1f;color:#26392d33;cursor:default}.face-slot.ghost:hover{transform:none;box-shadow:none}.face-slot.ghost .cap{display:none}
      .face-slot i{position:absolute;top:5px;right:5px;width:6px;height:6px;border-radius:50%}.face-slot.preset i{background:#3c8cff}.face-slot.custom i{background:#25bd76}.face-slot.disabled i{background:#ee5b66}.face-slot.none i{background:#9aa4ad}.face-slot.selected{border-color:#03a9f4;box-shadow:0 0 0 3px #03a9f429}.face-slot.pressed{animation:press .85s ease}
      .screen-keys{width:100%;margin-top:16px}.sk-title{font-size:9px;letter-spacing:.14em;text-transform:uppercase;color:#627168;text-align:center;margin-bottom:8px}.sk-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.face-slot.sk{min-height:56px}.face-slot.sk .fg{font-size:15px;font-weight:800}
      @media(max-width:850px){main{padding:20px 12px 50px}.selectors{grid-template-columns:1fr}.identity{display:none}.quick-bind{grid-template-columns:1fr}.workspace{grid-template-columns:1fr}.remote-stage,.editor{padding:16px}.editor{min-height:0}header p{display:none}.battery{display:none}.layout-button{display:none}}
      @media(max-width:430px){header{align-items:center}.live{padding:0 10px}.screen{min-height:400px;padding:13px}.remote-shell{padding:12px;border-radius:32px}.button-grid{gap:7px}.remote-button{min-height:72px;border-radius:15px}dl{grid-template-columns:1fr}dl div:nth-last-child(2){border-bottom:1px solid var(--divider-color,#e2e5e8)}}`;
  }
}

customElements.define("switchbot-urc-panel", SwitchBotUrcPanel);
