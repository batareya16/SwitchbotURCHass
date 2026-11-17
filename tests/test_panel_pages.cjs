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

test('IR softkeys use the recorded glyph including a menu link, with empty keys blank', () => {
  const instance = panel();
  instance._physical = {kind: 'ir', pages: [
    {index: 0, buttons: [{index: 1, transport: 'stored', function: 25}]},
    {index: 1, buttons: [], link_record: '0000d204' + '00'.repeat(32)},
  ]};
  instance._pageIndex = 0;
  instance._renderScreen = () => '';
  const html = instance._renderFace(instance._page());
  const softkeys = html.split('class="screen-softkeys"')[1].split('translate(0 -23)')[0];
  assert.match(softkeys, /data-page-link="1">[\s\S]*?keyfun-00d2\.png/);
  assert.match(softkeys, /data-button="p0_k1">[\s\S]*?keyfun-0019\.png/);
  assert.equal((softkeys.match(/<image /g) || []).length, 2);
  assert.doesNotMatch(softkeys, /keyfun-0000\.png/);
});

test('an imported TV shows the stock softkeys and translates catalog tags inside menus', () => {
  const instance = panel();
  instance._remote = () => ({
    remote_id: 'tv', device_type: 'IR_2', pages: [],
    ir_screen_preview: {softkeys: [39, 20, 210, 100], catalog_glyphs: {40: 22}},
  });
  instance._physical = {kind: 'ir', pages: [
    {index: 0, buttons: [{index: 2, transport: 'stored', function: 40}]},
    {index: 1, buttons: [{index: 0, transport: 'stored', function: 40}]},
  ]};
  const page = instance._page();
  const softkeys = instance._renderFace(page)
    .split('class="screen-softkeys"')[1].split('translate(0 -23)')[0];
  const glyphs = [...softkeys.matchAll(/keyfun-([\da-f]+)\.png/g)].map((match) => match[1]);
  assert.deepEqual(glyphs, ['0027', '0014', '00d2', '0064']);
  const submenu = instance._renderScreen(page);
  assert.match(submenu, /keyfun-0016\.png/);
  assert.doesNotMatch(submenu, /keyfun-0028\.png/);
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
  assert.equal(instance._mode, 'actions');
  const first = instance._button();
  assert.equal(first.button_function, 22);

  instance._addKeyToCurrentPage();
  assert.equal(instance._buttonId, 'p1_k1');
  assert.equal(instance._button().button_function, first.button_function);
});

test('native menu rows show the glyph picker without exposing the command selector', () => {
  const instance = panel();
  const button = instance._button();
  const html = instance._renderKeyEditor(button);
  assert.match(html, /Button icon/);
  assert.doesNotMatch(html, /On the remote|This key sends|data-key-field/);

  instance._physical.kind = 'hid';
  instance._physical.pages[1].buttons[0].transport = 'hid';
  assert.match(instance._renderKeyEditor(button), /This key sends/);
});

test('HID Rewind aliases share a label while keeping the saved button code', () => {
  const instance = panel();
  instance._physicalFunctions = [
    {value: 25, label: 'Rewind', aliases: [2103]},
    {value: 26, label: 'Fast forward', aliases: [2102]},
  ];
  assert.match(instance._hidFunctionOptions(2103), /value="2103"\s+selected>Rewind/);
  assert.equal(instance._hidFunctionOptions(2103).match(/>Rewind</g).length, 1);
  assert.match(instance._hidFunctionOptions(2003), /value="2003" selected>No HID action \(0x07D3\)/);
  assert.match(instance._hidFunctionOptions(2003), /value="25"\s*>Rewind/);
});

test('Native A–D keys keep icon and menu controls without exposing the saved command', () => {
  const instance = panel();
  instance._pageIndex = 0;
  instance._buttonId = 'p0_k1';
  const key = {index: 1, transport: 'native', function: 323};
  instance._physical.pages[0].buttons.push(key);
  const html = instance._editor(instance._button(), instance._remote());
  assert.match(html, /Button icon/);
  assert.match(html, /Turn key B into a page/);
  assert.doesNotMatch(html, /On the remote|This key sends|data-key-field|<dt>Function<\/dt>/);
  assert.equal(key.function, 323);
});

test('a Native key outside the stock layout can get HA actions while KATA stays reserved', () => {
  const instance = panel();
  instance._nativeProfile = () => ({
    main_positions: Array.from({length: 19}, (_, index) => index).filter(index => index !== 13),
    main_keys: [{index: 4, actionable: true, function: 5}],
    subpages: [{index: 1, link_index: 0}],
  });
  instance._pageIndex = 0;
  instance._buttonId = 'p0_k15';
  assert.equal(instance._button().position, 'VOLADD');
  assert.ok(!instance._page().buttons.some(button => button.position === 'KATA'));
  const emptyEditor = instance._editor(instance._button(), instance._remote());
  assert.match(emptyEditor, /Assign an action/);
  assert.doesNotMatch(emptyEditor, /On the remote|This key sends/);
  assert.match(instance._key({}, 'KATA', ''), /Reserved for the Universal Remote/);

  let assign;
  instance._wireKeyEditor({
    querySelectorAll: () => [],
    getElementById(id) {
      return id === 'addKeyHere' ? {addEventListener(_event, handler) {assign = handler;}} : null;
    },
  });
  assign();
  assert.equal(instance._button().button_id, 'p0_k15');
  assert.equal(instance._button().button_function, 22);
  assert.equal(instance._mode, 'actions');
  assert.doesNotMatch(instance._renderKeyEditor(instance._button()), /On the remote|This key sends/);
  assert.equal(instance._nativeProfileConflicts(instance._nativeProfile()).length, 0);
});

test('KATA cannot be selected on HID or IR remotes even with an old command', () => {
  for (const kind of ['hid', 'ir']) {
    const instance = panel();
    instance._physical.kind = kind;
    instance._physical.pages[0].buttons.push({index: 13, function: 5});
    instance._pageIndex = 0;
    instance._buttonId = 'p0_k13';
    assert.equal(instance._button(), null);
    const html = instance._key({KATA: {button_id: 'p0_k13'}}, 'KATA', '');
    assert.match(html, /Reserved for the Universal Remote/);
    assert.doesNotMatch(html, /data-button|role="button"/);
  }
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

test('a select action checks the options of its actual entity', () => {
  const instance = panel();
  instance._hass = {states: {
    'select.vacuum_room_4_order': {state: '1', attributes: {options: ['1', '2']}},
    'select.vacuum_room_4_cleaning_mode': {state: 'mopping', attributes: {options: ['sweeping', 'mopping']}},
  }};
  const step = {action: 'select.select_option', target: {entity_id: 'select.vacuum_room_4_order'},
    data: {option: 'sweeping'}};
  instance._draftActions = [step];
  assert.match(instance._selectOptionWarning(), /room_4_order currently offers 1, 2/);
  step.target.entity_id = 'select.vacuum_room_4_cleaning_mode';
  assert.equal(instance._selectOptionWarning(), '');
  step.data.option = '{{ mode }}';
  assert.equal(instance._selectOptionWarning(), '');
});


test('automatic Bridge installation needs no device key', async () => {
  const instance = panel();
  instance._add = {kind: 'native', name: 'Lamp', nativeType: 'STRIP'};
  instance._sources = {native: true, bridges: [{target_id: 'DA:71:16:E0:1F:93'}]};
  const requests = [];
  instance._hass = {async callWS(request) {requests.push(request); return {slot: 1};}};
  await instance._installRemote();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].type, 'switchbot_urc/studio/remote/create');
  assert.equal(requests[0].auto_address, true);
  assert.equal(Object.hasOwn(requests[0], 'target_key'), false);
});


test('capacity shows one available/total count for each remote type', () => {
  const instance = panel();
  instance._sources = {remote_capacity: {
    ir: {available: 7, total: 10},
    native: {available: 1, total: 4},
    hid: {available: 2, total: 3},
  }};
  assert.match(instance._renderRemoteCapacity(), /IR remotes available <b>7\/10/);
  assert.match(instance._renderRemoteCapacity(), /Bridge remotes available <b>1\/4/);
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
  assert.match(instance._installCapacityError({kind: 'native'}), /No more Bridge remotes/);
  assert.equal(instance._installCapacityError({kind: 'hid'}), '');
  assert.match(instance._installCapacityError({kind: 'cloud'}), /replace/);
  assert.equal(instance._installCapacityError({kind: 'cloud', replace: true}), '');
});

test('HID creation opens its settings without requesting a MAC or manual button list', async () => {
  const instance = panel();
  instance._add = {kind: 'hid', name: 'TV', deviceType: 'UNIVERSAL_BLE',
    icon: 'tv'};
  const requests = [];
  instance._hass = {async callWS(request) {requests.push(request); return {slot: 1, remote_id: 'tv'};}};
  await instance._installRemote();
  assert.equal(requests.length, 1);
  assert.equal(requests[0].type, 'switchbot_urc/studio/remote/create_hid');
  assert.equal(requests[0].device_type, 'UNIVERSAL_BLE');
  assert.equal(Object.hasOwn(requests[0], 'buttons'), false);
  assert.equal(Object.hasOwn(requests[0], 'device_id'), false);
  assert.equal(instance._add, null);
  assert.equal(instance._iconPickerFor, 'tv');
});

test('HID settings report pairing only after the device confirms it', async () => {
  const instance = panel();
  instance._hidPairingByRemote = new Map();
  let request;
  let complete;
  instance._hass = {callWS(value) {
    request = value;
    return new Promise(resolve => {complete = resolve;});
  }};
  const pairing = instance._enterHidPairMode();
  const state = instance._hidPairingByRemote.get(instance._draftScope());
  assert.equal(request.type, 'switchbot_urc/studio/remote/pair_hid');
  assert.equal(request.remote_id, instance._remoteId);
  assert.equal(state.busy, true);
  assert.match(state.message, /Open Bluetooth settings/);
  complete({status: 'paired'});
  await pairing;
  assert.equal(state.busy, false);
  assert.equal(state.message, 'Pairing complete.');
});
