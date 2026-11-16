const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

let Panel;
const context = {
  HTMLElement: class {}, structuredClone, console,
  customElements: {get() {}, define(_name, implementation) {Panel = implementation;}},
};
vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,
  '../custom_components/switchbot_urc/frontend/switchbot-urc-panel.js'), 'utf8'), context);

function panel() {
  const instance = Object.create(Panel.prototype);
  instance._entryId = 'entry';
  instance._remoteId = 'vacuum';
  instance._pageIndex = 1;
  instance._buttonId = 'p1_k0';
  instance._mode = 'actions';
  instance._dirty = true;
  instance._draftActions = [{action: 'light.turn_on', target: {entity_id: 'light.desk'}}];
  instance._jsonValid = true;
  instance._physical = {kind: 'native', template: 'VACUUM', pages: [
    {index: 0, buttons: [{index: 4, transport: 'native', function: 5}]},
    {index: 1, title: 'Lighting', buttons: [{index: 0, transport: 'native', function: 5}]},
  ]};
  instance._physicalOrigins = {};
  instance._physicalFunctions = [{value: 5, label: 'On'}];
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._physicalBaseline.pages.pop();
  instance._remote = () => ({remote_id: 'vacuum', pages: []});
  instance._nativeProfile = () => ({main_positions: [0, 1, 2, 3, 4, 5],
    main_keys: [], subpages: [1, 2, 3, 4].map(index => ({index, link_index: index - 1}))});
  instance.shadowRoot = {getElementById() {return null;}};
  instance._render = () => {};
  instance._notify = () => {};
  instance._replaceEntry = () => {};
  instance._normalizeSelection = () => {};
  instance._load = async () => {};
  return instance;
}

test('one-row page is written before its HA action, preserving action editor values', async () => {
  const instance = panel();
  instance._rememberMapping();
  const requests = [];
  instance._hass = {async callWS(request) {
    requests.push(request);
    if (request.type.endsWith('/physical/apply')) return {layout: instance._physical, status: 'Saved'};
    return {};
  }};
  instance._load = async () => {
    // A reload normally selects a saved button and replaces these editing values.
    instance._mode = 'preset';
    instance._draftActions = [];
  };
  await instance._save();
  assert.equal(requests.length, 2);
  assert.equal(requests[0].type, 'switchbot_urc/studio/physical/apply');
  assert.equal(requests[0].layout.pages[1].buttons.length, 1);
  assert.equal(requests[1].type, 'switchbot_urc/studio/save_button_action');
  assert.equal(requests[1].button_id, 'p1_k0');
  assert.equal(requests[1].mode, 'actions');
  assert.equal(requests[1].actions[0].action, 'light.turn_on');
  assert.equal(instance._error, null);
});

test('failed page write is visible and does not save a nonexistent HA button', async () => {
  const instance = panel();
  instance._rememberMapping();
  let calls = 0;
  instance._hass = {async callWS() {calls++; throw new Error('Native write failed');}};
  await instance._save();
  assert.equal(calls, 1);
  assert.equal(instance._error, 'Native write failed');
  assert.equal(instance._physicalChanges(), 1);
  assert.equal(instance._draftActions[0].action, 'light.turn_on');
});

test('saving an existing HA mapping does not rewrite an unchanged physical page', async () => {
  const instance = panel();
  instance._rememberMapping();
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._resetPhysicalOrigins(instance._physical);
  const requests = [];
  instance._hass = {async callWS(request) {requests.push(request); return {};}};
  await instance._save();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].type, 'switchbot_urc/studio/save_button_action');
});

test('menu and row settings omit custom name fields and share page controls', () => {
  const instance = panel();
  instance._editor = () => '<div>Row command and HA actions</div>';
  instance._renderMenuIcon = () => '<div>Menu icon</div>';
  instance._pageEditing = true;
  let html = instance._renderPageEditor(instance._page(), instance._button(), instance._remote());
  for (const label of ['Add row', 'Delete menu', 'Menu icon']) {
    assert.ok(html.includes(label));
  }
  assert.ok(!html.includes('id="saveButton"'));
  assert.ok(!html.includes('Row name'));
  assert.ok(!html.includes('Menu name'));
  assert.ok(!html.includes('Row command and HA actions'));
  instance._pageEditing = false;
  html = instance._renderPageEditor(instance._page(), instance._button(), instance._remote());
  assert.ok(!html.includes('Row name'));
  assert.ok(html.includes('Row command and HA actions'));
  assert.ok(html.indexOf('Delete last row and menu') < html.indexOf('Row command and HA actions'));
  assert.ok(!html.includes('Menu name'));
  assert.ok(!html.includes('Menu icon'));
});

test('ordinary Save writes a one-row menu with no selected row or HA edits', async () => {
  const instance = panel();
  instance._pageEditing = true;
  instance._buttonId = null;
  instance._dirty = false;
  const requests = [];
  instance._hass = {async callWS(request) {
    requests.push(request);
    return {layout: instance._physical, status: 'Saved'};
  }};
  await instance._save();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].type, 'switchbot_urc/studio/physical/apply');
  assert.equal(requests[0].layout.pages[1].buttons.length, 1);
});

test('the icon picker shows the firmware caption alongside the icon', () => {
  const instance = panel();
  const html = instance._renderGlyphPicker({glyph: 321}, 'glyph', 'Button icon', 5);
  assert.match(html, /<summary>.*White<\/span><\/summary>/);
  assert.match(html, /data-glyph-code="321"\s+aria-label="White \(0x0141\)" aria-pressed="true">\s*<img [^>]*keyfun-0141\.png[^>]*><span>White<\/span>/);
  assert.match(html, /data-glyph-code="0"\s+aria-label="No caption \(0x0000\)"/);
});

test('adding the first row selects its editor and gives it a new physical identity', () => {
  const instance = panel();
  instance._physical.pages[1].buttons = [];
  instance._pageEditing = true;
  instance._addKeyToCurrentPage();
  assert.equal(instance._buttonId, 'p1_k0');
  assert.equal(instance._pageEditing, false);
  assert.equal(instance._button().draft_only, true);
  assert.equal(instance._physical.pages[1].buttons.length, 1);
});


test('deleting a row compacts saved identities and keeps the surviving action draft', async () => {
  const instance = panel();
  const page = instance._physical.pages[1];
  page.buttons.push({index: 1, transport: 'native', function: 6});
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._resetPhysicalOrigins(instance._physical);
  instance._selectButton(instance._page().buttons[1], false);
  instance._mode = 'actions';
  instance._dirty = true;
  instance._draftActions = [{action: 'script.turn_on', target: {entity_id: 'script.test'}}];
  instance._rememberMapping();
  instance._removeMenuRow(page, page.buttons[0]);
  const requests = [];
  instance._hass = {async callWS(request) {
    requests.push(request);
    return {layout: instance._physical, status: 'Saved'};
  }};
  await instance._save();
  assert.equal(requests[0].layout.pages[1].buttons[0].function, 6);
  assert.equal(JSON.stringify(requests[0].identity_migrations), '[{"from":"p1_k1","to":"p1_k0"}]');
  assert.equal(JSON.stringify(requests[0].identity_removals), '["p1_k0"]');
  assert.equal(requests[1].button_id, 'p1_k0');
  assert.equal(requests[1].actions[0].target.entity_id, 'script.test');
});

test('deleting the only row saves a layout without the menu or any action for that row', async () => {
  const instance = panel();
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._resetPhysicalOrigins(instance._physical);
  instance._rememberMapping();
  const page = instance._physical.pages[1];
  instance._removeMenuRow(page, page.buttons[0]);
  const requests = [];
  instance._hass = {async callWS(request) {
    requests.push(request);
    return {layout: instance._physical, status: 'Saved'};
  }};
  await instance._save();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].layout.pages.length, 1);
  assert.equal(JSON.stringify(requests[0].identity_removals), '["p1_k0"]');
});

test('Save applies reordered rows and retries only the per-button edits that failed', async () => {
  const instance = panel();
  const page = instance._physical.pages[1];
  page.buttons.push({index: 1, transport: 'native', function: 6});
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._resetPhysicalOrigins(instance._physical);
  instance._rememberMapping();
  instance._selectButton(instance._page().buttons[1], false);
  instance._mode = 'disabled';
  instance._dirty = true;
  instance._rememberMapping();
  instance._movePageKey(1, 1, -1);
  const requests = [];
  let fail = true;
  instance._hass = {async callWS(request) {
    requests.push(request);
    if (request.button_id === 'p1_k1' && fail) throw new Error('Cannot save action');
    return {layout: instance._physical, status: 'Saved'};
  }};
  await instance._save();
  assert.equal(instance._error, 'Cannot save action');
  assert.equal(requests[0].layout.pages[1].buttons[0].function, 6);
  assert.equal(requests[1].button_id, 'p1_k0');
  assert.equal(requests[1].mode, 'disabled');
  assert.equal(requests[2].button_id, 'p1_k1');
  fail = false;
  await instance._save();
  assert.equal(requests.length, 4);
  assert.equal(requests[3].button_id, 'p1_k1');
  assert.equal(requests[3].mode, 'actions');
  assert.equal(instance._mappingDrafts().size, 0);
});

test('the visual action selector gets its new value and refreshes the count immediately', async () => {
  const instance = panel();
  instance._ensureActionSelector = async () => true;
  const summary = {};
  const textarea = {classList: {remove() {}}};
  const selector = {isConnected: true, addEventListener(_name, callback) {this.change = callback;}};
  const host = {isConnected: true, append() {}};
  const ids = {visualActionEditor: host, actionSummary: summary, actionsJson: textarea};
  instance.shadowRoot.getElementById = (id) => ids[id];
  context.document = {createElement() {return selector;}};
  try {
    await instance._mountActionSelector();
    const values = [{action: 'light.toggle'}, {action: 'script.test'}];
    selector.change({detail: {value: values}});
    assert.equal(JSON.stringify(selector.value), JSON.stringify(values));
    assert.equal(JSON.parse(textarea.value)[1].action, 'script.test');
    assert.equal(summary.textContent, '2 actions');
    assert.equal(instance._mappingDrafts().get('p1_k0').actions.length, 2);
  } finally {
    delete context.document;
  }
});


test('automatic bridge setup reuses a stored key and only prompts for an unconfigured bridge', () => {
  const instance = panel();
  instance._sources = {bridges: [
    {target_id: '8A:88:1B:E0:1F:92', has_key: true},
    {target_id: 'DA:71:16:E0:1F:93', has_key: false},
  ]};
  assert.equal(instance._needsBridgeKey({}), false);
  assert.equal(instance._needsBridgeKey({targetId: 'DA:71:16:E0:1F:93'}), true);
  instance._sources.bridges.shift();
  assert.equal(instance._needsBridgeKey({}), true);
});


test('capacity shows one available/total count for each remote type', () => {
  const instance = panel();
  instance._sources = {remote_capacity: {
    ir: {available: 7, total: 10},
    native: {available: 1, total: 4},
    hid: {available: 2, total: 3},
  }};
  assert.match(instance._renderRemoteCapacity(), /IR remotes available <b>7\/10/);
  assert.match(instance._renderRemoteCapacity(), /Native remotes available <b>1\/4/);
  assert.match(instance._renderRemoteCapacity(), /HID remotes available <b>2\/3/);
  assert.doesNotMatch(instance._renderRemoteCapacity(), /Check availability/);

  instance._sources.remote_capacity.hid.available = null;
  assert.match(instance._renderRemoteCapacity(), /HID remotes available <b>—\/3/);
  assert.match(instance._renderRemoteCapacity(), /Check availability/);
});

test('a full category blocks only that type and leaves IR replacement available', () => {
  const instance = panel();
  instance._sources = {remote_capacity: {
    ir: {available: 0, total: 10},
    native: {available: 0, total: 4},
    hid: {available: 1, total: 3},
  }};
  assert.match(instance._installCapacityError({kind: 'native'}), /No more Native remotes/);
  assert.equal(instance._installCapacityError({kind: 'hid'}), '');
  assert.match(instance._installCapacityError({kind: 'cloud'}), /replace/);
  assert.equal(instance._installCapacityError({kind: 'cloud', replace: true}), '');
});
