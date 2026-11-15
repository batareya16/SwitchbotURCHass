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
  for (const label of ['Add row', 'id="saveButton"', '>Save</button>', 'Delete menu', 'Menu icon']) {
    assert.ok(html.includes(label));
  }
  assert.ok(!html.includes('Row name'));
  assert.ok(!html.includes('Menu name'));
  assert.ok(!html.includes('Row command and HA actions'));
  instance._pageEditing = false;
  html = instance._renderPageEditor(instance._page(), instance._button(), instance._remote());
  assert.ok(!html.includes('Row name'));
  assert.ok(html.includes('Row command and HA actions'));
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
