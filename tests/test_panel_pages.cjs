const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

let Panel;
const context = {
  HTMLElement: class {}, structuredClone, console, clearTimeout, TextEncoder,
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

test('scene editor uses the remote face, firmware icon choices and custom actions', async () => {
  const instance = panel();
  instance._pages = () => [];
  instance._nativeProfiles = [];
  const entry = {entry_id: 'entry', remotes: []};
  instance._entry = () => entry;
  const existing = {index: 4, name: 'Sleep', icon: 21, color: 6, actions: []};
  entry.remotes = [{...existing, kind: 'scene', remote_id: 'scene:4', scene_index: 4}];
  const newScene = {name: 'Movie', icon: 18, color: 6, actions: instance._draftActions};
  instance._scenePanel = {entryId: 'entry', rows: [existing], limit: 10,
    loaded: true, draft: newScene};
  let request;
  instance._hass = {states: {}, async callWS(message) {
    request = message;
    return {scenes: [{...newScene, index: 0}, existing]};
  }};
  const markup = instance._renderScenes();
  assert.match(markup, /viewBox="0 0 300 657"/);
  assert.match(markup, /data-remote="scene:4"/);
  assert.match(markup, /scene-18.png/);
  assert.match(markup, /id="visualActionEditor"/);
  instance._scenePanel.appearance = true;
  const appearance = instance._renderScenes();
  assert.match(appearance, /data-scene-icon="18"/);
  assert.match(appearance, /id="sceneName"/);
  assert.equal((appearance.match(/data-scene-icon=/g) || []).length, 25);
  assert.doesNotMatch(markup, /name="entity_id"/);
  await instance._saveScene(false);
  assert.equal(request.type, 'switchbot_urc/studio/scenes/save');
  assert.equal(request.expected[0].index, 4);
  assert.equal(request.expected[0].actions, undefined);
  assert.equal(request.actions[0].action, 'light.turn_on');
  assert.equal(request.index, undefined);
  assert.equal(instance._scenePanel.rows.length, 2);
  assert.equal(instance._scenePanel.draft.index, 0);
  assert.equal(entry.remotes[0].remote_id, 'scene:0');
});

test('scene workspace renders through the normal Studio entry point', () => {
  const instance = panel();
  instance._pages = () => [];
  instance._button = () => null;
  instance._page = () => ({index: 0, buttons: []});
  instance._nativeProfiles = [];
  instance._entry = () => ({entry_id: 'entry', remotes: [
    {remote_id: 'tv', name: 'TV', kind: 'ir', pages: []},
    {remote_id: 'scene:0', scene_index: 0, name: 'Movie', kind: 'scene', icon: 18, color: 5, pages: []},
  ]});
  instance._entries = () => [instance._entry()];
  instance._hass = {states: {}};
  instance._scenePanel = {entryId: 'entry', rows: [
    {index: 0, name: 'Movie', icon: 18, color: 5, actions: []},
  ], loaded: true, limit: 10, draft: null};
  instance._wireEvents = () => {};
  instance._wireScenes = () => {};
  instance._mountActionSelector = () => {};
  instance.shadowRoot = {innerHTML: '', querySelector() {return null;}, querySelectorAll() {return [];}, getElementById() {return null;}};
  instance._renderUnsafe();
  assert.match(instance.shadowRoot.innerHTML, /id="remoteSelect"/);
  assert.match(instance.shadowRoot.innerHTML, /data-remote="scene:0"/);
  assert.match(instance.shadowRoot.innerHTML, /viewBox="0 0 300 657"/);
  // The account / installed / diagnostics panels stay put while a scene is open.
  assert.match(instance.shadowRoot.innerHTML, /<summary>Diagnostics<\/summary>/);
  assert.doesNotMatch(instance.shadowRoot.innerHTML, /Back to remotes|sceneForm|sceneRemoteSelect|remote-screen-tabs/);
});

test('shared remote selection preserves scene actions without fetching a separate list', () => {
  const instance = panel();
  const scene = {remote_id: 'scene:0', scene_index: 0, kind: 'scene', name: 'Movie', icon: 18, color: 5, actions: []};
  const entry = {entry_id: 'entry', remotes: [{remote_id: 'vacuum', kind: 'native'}, scene]};
  instance._entry = () => entry;
  instance._remote = () => entry.remotes.find(row => row.remote_id === instance._remoteId);
  instance._button = () => null;
  instance._stashLayout = () => {};
  instance._hass = {callWS() {throw new Error('Selection must use the shared inventory');}};
  instance._pickRemote('scene:0');
  assert.equal(instance._scenePanel.draft.index, 0);
  assert.equal(instance._physical, null);
  instance._draftActions = [{action: 'script.movie'}];
  instance._pickRemote('vacuum');
  assert.equal(instance._scenePanel, null);
  instance._pickRemote('scene:0');
  assert.equal(instance._draftActions[0].action, 'script.movie');
});

test('scene deletion removes it from the common list and keeps ordinary remotes', async () => {
  const instance = panel();
  const scene = {index: 0, name: 'Movie', icon: 18, color: 5, actions: []};
  const entry = {entry_id: 'entry', remotes: [
    {remote_id: 'tv', kind: 'ir'}, {...scene, remote_id: 'scene:0', scene_index: 0, kind: 'scene'},
  ]};
  instance._entry = () => entry;
  instance._scenePanel = {entryId: 'entry', rows: [scene], draft: scene};
  instance._remoteId = 'scene:0';
  instance._hass = {async callWS(request) {
    assert.equal(request.delete, true);
    assert.equal(request.index, 0);
    return {scenes: []};
  }};
  await instance._saveScene(true);
  assert.equal(entry.remotes.length, 1);
  assert.equal(entry.remotes[0].remote_id, 'tv');
  assert.equal(instance._scenePanel, null);
});

test('remote settings reads the selected physical remote and saves only edited fields', async () => {
  const instance = panel();
  const values = {touch_wheel: false, key_sounds: true, lift_to_wake: true,
    auto_brightness: true, screen_brightness: 50, key_brightness: 30,
    screen_timeout: 15, temperature_unit: 0, language: 1, japan_model: false};
  const requests = [];
  instance._hass = {async callWS(request) {
    requests.push(request);
    return {settings: {...values, ...(request.changes || {})}};
  }};
  await instance._openDeviceSettings();
  assert.equal(requests[0].entry_id, 'entry');
  assert.equal(requests[0].changes, undefined);
  assert.match(instance._renderDeviceSettings(), /data-remote-setting="touch_wheel"/);
  assert.match(instance._renderDeviceSettings(), /data-remote-setting="screen_brightness"[^>]*disabled/);
  instance._deviceSettings.draft.touch_wheel = true;
  await instance._saveDeviceSettings();
  assert.deepEqual({...requests[1].changes}, {touch_wheel: true});
  assert.equal(instance._deviceSettings.status, 'Settings saved and verified.');
  assert.equal(Object.keys(instance._deviceSettingsChanges()).length, 0);
  instance._deviceSettings.draft.japan_model = true;
  assert.doesNotMatch(instance._renderDeviceSettings(), /data-remote-setting="temperature_unit"/);
});

test('remote settings reports read and verification failures without claiming success', async () => {
  const instance = panel();
  instance._hass = {async callWS() {throw new Error('Read failed');}};
  await instance._openDeviceSettings();
  assert.equal(instance._deviceSettings.values, null);
  assert.match(instance._renderDeviceSettings(), /Read failed/);
  assert.match(instance._renderDeviceSettings(), /id="retryDeviceSettings"/);
  instance._deviceSettings.values = {touch_wheel: false};
  instance._deviceSettings.draft = {touch_wheel: true};
  await instance._saveDeviceSettings();
  assert.equal(instance._deviceSettings.status, '');
  assert.equal(instance._deviceSettings.draft.touch_wheel, true);
  assert.equal(instance._deviceSettings.values.touch_wheel, false);
  const count = Object.keys(instance._deviceSettingsChanges()).length;
  instance._entryId = 'another-entry';
  await instance._saveDeviceSettings();
  assert.equal(Object.keys(instance._deviceSettingsChanges()).length, count);
});

test('remote settings ignores a closed read and preserves the editor drafts', async () => {
  const instance = panel();
  const physical = instance._physical;
  const actions = instance._draftActions;
  let finish;
  instance._hass = {callWS: () => new Promise(resolve => {finish = resolve;})};
  const opening = instance._openDeviceSettings();
  instance._deviceSettings = null;
  finish({settings: {touch_wheel: true}});
  await opening;
  assert.equal(instance._deviceSettings, null);
  assert.equal(instance._physical, physical);
  assert.equal(instance._draftActions, actions);
});

test('operation results and errors share one persistent dismissible Studio notice', () => {
  const instance = panel();
  instance._remote = () => ({name: 'Floor lamp'});
  let dismiss;
  const region = {innerHTML: ''};
  instance.shadowRoot = {getElementById(id) {
    if (id === 'studioFeedback') return region;
    if (id === 'dismissFeedback') return {addEventListener(_event, callback) {dismiss = callback;}};
    return null;
  }};
  instance._notify = Panel.prototype._notify;
  instance._error = 'An earlier failure';
  instance._notify('Changes saved.', 'success');
  assert.match(region.innerHTML, /studio-feedback success/);
  assert.match(region.innerHTML, /Floor lamp/);
  assert.doesNotMatch(region.innerHTML, /earlier failure/);
  instance._error = '<Save failed>';
  const failure = instance._renderStudioFeedback();
  assert.match(failure, /role="alert"/);
  assert.match(failure, /&lt;Save failed&gt;/);
  assert.doesNotMatch(failure, /Changes saved/);
  dismiss();
  assert.equal(instance._error, null);
  assert.equal(region.innerHTML, '');
  instance._notify('Changes saved.', 'success');
  instance._entryId = 'another-remote';
  assert.equal(instance._renderStudioFeedback(), '');
});

test('saved device acknowledgements are not duplicated above the remote or in page editing', () => {
  const instance = panel();
  instance._physicalStatus = 'Device acknowledged all pages.';
  instance._physicalChanges = () => 0;
  assert.equal(instance._renderApplyBar(), '');
  const page = instance._pages().find(item => item.index === 1);
  assert.doesNotMatch(instance._renderPageEditor(page, null, instance._remote()), /Device acknowledged all pages/);
});

test('scene selection preserves draft names and actions between rows', () => {
  const instance = panel();
  instance._button = () => null;
  const first = {index: 0, name: 'Movie', icon: 18, color: 5, actions: []};
  const second = {index: 1, name: 'Morning', icon: 1, color: 2, actions: []};
  instance._scenePanel = {rows: [first, second], draft: null};
  instance._selectSceneDraft(structuredClone(first));
  instance._scenePanel.draft.name = 'Movie night';
  instance._draftActions = [{action: 'light.turn_off', target: {entity_id: 'light.hall'}}];
  instance._rememberMapping();
  instance._selectSceneDraft(structuredClone(second));
  instance._selectSceneDraft(structuredClone(first));
  assert.equal(instance._scenePanel.draft.name, 'Movie night');
  assert.equal(instance._draftActions[0].action, 'light.turn_off');
});

test('scene refresh preserves other drafts and invalidates externally changed scenes', async () => {
  const instance = panel();
  instance._button = () => null;
  const first = {index: 0, name: 'Movie', icon: 18, color: 5, actions: []};
  const second = {index: 1, name: 'Morning', icon: 1, color: 2, actions: []};
  instance._scenePanel = {entryId: 'entry', rows: [first, second], drafts: new Map(), draft: null};
  instance._scenePanels = new Map([['entry', instance._scenePanel]]);
  const entry = {entry_id: 'entry', remotes: []};
  instance._entry = () => entry;
  const updateRows = rows => {entry.remotes = rows.map(row => ({...row, kind: 'scene', scene_index: row.index}));};
  updateRows([first, second]);
  instance._selectSceneDraft(structuredClone(first));
  instance._scenePanel.draft.name = 'Movie night';
  instance._draftActions = [{action: 'light.turn_off', target: {entity_id: 'light.hall'}}];
  instance._rememberMapping();
  instance._selectSceneDraft(structuredClone(second));
  instance._hass = {async callWS() {throw new Error('Selecting a scene must use the common inventory');}};
  await instance._openScenes();
  instance._selectSceneDraft(structuredClone(first));
  assert.equal(instance._scenePanel.draft.name, 'Movie night');
  assert.equal(instance._draftActions[0].action, 'light.turn_off');
  instance._selectSceneDraft(structuredClone(second));
  const changed = {...first, name: 'Changed on the remote'};
  updateRows([changed, second]);
  await instance._openScenes();
  instance._selectSceneDraft(structuredClone(changed));
  assert.equal(instance._scenePanel.draft.name, changed.name);
  assert.equal(instance._draftActions.length, 0);
});

test('IR keys inside HID expose firmware icons while HID commands retain their function', () => {
  const instance = panel();
  instance._catalog = {available: false};
  const button = {button_id: 'p1_k0', button_page: 1, button_index: 0};
  instance._physical = {kind: 'hid', pages: [
    {index: 0, buttons: []},
    {index: 1, buttons: [{index: 0, transport: 'ir', code_hex: 'aabb', glyph: 105}]},
  ]};
  assert.match(instance._renderKeyEditor(button), /data-glyph-field="glyph"/);
  assert.match(instance._renderKeyEditor(button), /keyfun-0069.png/);
  instance._physical.pages[1].buttons[0] = {index: 0, transport: 'hid', function: 25};
  assert.doesNotMatch(instance._renderKeyEditor(button), /data-glyph-field="glyph"/);
});

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
  const entry = {scene_limit: 10, remotes: [
    {kind: 'native'}, {kind: 'scene', scene_index: 0}, {kind: 'scene', scene_index: 4},
  ]};
  instance._entry = () => entry;
  instance._sources = {remote_capacity: {
    ir: {available: 7, total: 10},
    native: {available: 1, total: 4},
    hid: {available: 2, total: 3},
  }};
  assert.match(instance._renderRemoteCapacity(), /IR remotes available <b>7\/10/);
  assert.match(instance._renderRemoteCapacity(), /Bridge remotes available <b>1\/4/);
  assert.match(instance._renderRemoteCapacity(), /HID remotes available <b>2\/3/);
  assert.match(instance._renderRemoteCapacity(), /HID remotes available[\s\S]*Scenes available <b>8\/10/);
  assert.doesNotMatch(instance._renderRemoteCapacity(), /Check availability/);
  entry.remotes = Array.from({length: 10}, (_, scene_index) => ({kind: 'scene', scene_index}));
  assert.match(instance._renderRemoteCapacity(), /Scenes available <b>0\/10/);
  entry.scene_error = 'Remote asleep';
  assert.match(instance._renderRemoteCapacity(), /Scenes available <b>—\/10/);


  instance._sources.remote_capacity.hid.available = null;
  assert.match(instance._renderRemoteCapacity(), /HID remotes available <b>—\/3/);
  assert.match(instance._renderRemoteCapacity(), /Check availability/);
});

test('a full category blocks only that type', () => {
  const instance = panel();
  instance._sources = {remote_capacity: {
    ir: {available: 0, total: 10},
    native: {available: 0, total: 4},
    hid: {available: 1, total: 3},
  }};
  assert.match(instance._installCapacityError({kind: 'native'}), /No more Bridge remotes/);
  assert.equal(instance._installCapacityError({kind: 'hid'}), '');
  assert.match(instance._installCapacityError({kind: 'cloud'}), /No more IR remotes.*Delete one first/);
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

test('text remote captions are validated in bytes and saved with the appearance draft', async () => {
  const instance = panel();
  const remote = {remote_id: 'mt', name: 'Hall', matter: {captions: ['A', 'B', 'C', 'D'], max_bytes: 31}};
  assert.equal(instance._captionsChanged(remote, {captions: ['A', 'B', 'C', 'D']}), false);
  assert.equal(instance._captionsChanged(remote, {captions: ['A', 'B ', 'C', 'X']}), true);
  assert.match(instance._captionsProblem(remote, {captions: ['A', '', 'C', 'D']}), /button B/);
  assert.match(instance._captionsProblem(remote, {captions: ['A', 'B', 'C', 'я'.repeat(16)]}), /longer than 31/);
  assert.equal(instance._captionsProblem(remote, {captions: ['A', 'B', 'C', 'я'.repeat(15)]}), '');

  const calls = [];
  instance._remote = () => remote;
  instance._draftScope = () => 'mt';
  instance._appearanceDraftsByRemote = new Map([['mt', {name: 'Hall panel', icon: undefined, captions: ['Lamp', 'B', 'C', 'D']}]]);
  instance._hass = {callWS: async (msg) => { calls.push(msg.type.split('/').slice(-2).join('/')); return {}; }};
  await instance._saveAppearance();
  assert.deepEqual(calls, ['matter/save', 'remote/rename']);
  assert.deepEqual(remote.matter.captions, ['Lamp', 'B', 'C', 'D']);
});

test('a text remote icon is saved with its captions in one write and updates the list picture', async () => {
  const instance = panel();
  const remote = {remote_id: 'mt', name: 'Hall', icon: 'device',
    matter: {captions: ['A', 'B', 'C', 'D'], max_bytes: 31}};
  const sent = [];
  instance._remote = () => remote;
  instance._draftScope = () => 'mt';
  instance._entry = () => ({icon_artwork: {washer: 0x28}});
  instance._appearanceDraftsByRemote = new Map([['mt', {name: 'Hall', icon: 'washer', captions: ['A', 'B', 'C', 'D']}]]);
  instance._hass = {callWS: async (msg) => { sent.push(msg); return {}; }};
  await instance._saveAppearance();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].icon, 'washer');
  assert.deepEqual(sent[0].captions, ['A', 'B', 'C', 'D']);
  assert.equal(remote.icon, 'washer');
  assert.equal(remote.artwork_id, 0x28);
  assert.equal(instance._firmwareIconSrc('washer'), '/switchbot_urc_static/artwork/profile-28.png');
  assert.equal(instance._firmwareIconSrc('device'), '');
});

test('native and text remotes offer firmware illustrations as icons, HID and IR keep theirs', () => {
  const instance = panel();
  instance._entry = () => ({icons: ['light', 'bathtub', 'washer'], icon_artwork: {light: 0x0c, bathtub: 0x11, washer: 0x28}});
  instance._draftScope = () => 'r';
  instance._appearanceDraftsByRemote = new Map();
  instance._iconPickerFor = 'r';
  instance._physical = null;
  instance._nativeProfiles = [];
  const render = (remote) => instance._renderAppearance({remote_id: 'r', name: 'R', icon: 'device', ...remote});

  const matter = render({device_type: 'MATTER_TEXT', matter: {captions: ['A', 'B', 'C', 'D'], max_bytes: 31}});
  assert.match(matter, /data-pick-icon="device"/);
  assert.match(matter, /profile-28\.png/);
  assert.match(matter, /data-pick-icon="washer"/);
  assert.doesNotMatch(matter, /cannot be changed/);

  const native = render({device_type: 'STRIP', can_test_native_icon: true});
  assert.match(native, /data-pick-icon="bathtub"/);
  assert.match(native, /profile-11\.png/);
  assert.match(native, /Type default/);

  for (const device_type of ['APPLE_TV', 'IR_24']) {
    const page = render({device_type});
    assert.match(page, /data-pick-icon="washer"/);
    assert.match(page, /profile-28\.png/);
    assert.match(page, /Original/);
  }
  assert.match(render({device_type: 'IR_24'}), /Confirmed on real HID and IR remotes/);
});

test('HID and IR icon changes are written by resending their saved pages', async () => {
  for (const [device_type, expected] of [['APPLE_TV', 'washer'], ['IR_24', 'device']]) {
    const instance = panel();
    const remote = {remote_id: 'r', name: 'R', icon: expected === 'device' ? 'washer' : 'device', device_type, artwork_id: 0x15};
    const sent = [];
    instance._remote = () => remote;
    instance._draftScope = () => 'r';
    instance._entry = () => ({icon_artwork: {washer: 0x28}});
    instance._appearanceDraftsByRemote = new Map([['r', {name: 'R', icon: expected}]]);
    instance._hass = {callWS: async (msg) => { sent.push(msg); return {}; }};
    await instance._saveAppearance();
    assert.equal(sent.length, 1);
    assert.match(sent[0].type, /studio\/remote\/update_page_icon$/);
    assert.equal(sent[0].icon, expected);
    assert.equal(remote.icon, expected);
    assert.equal(remote.artwork_id, expected === 'washer' ? 0x28 : null);
  }
});

test('the Add dialog offers firmware illustrations for every installable kind except scenes', () => {
  const instance = panel();
  instance._entry = () => ({icons: ['light', 'washer'], icon_artwork: {light: 0x0c, washer: 0x28}});
  for (const kind of ['native', 'catalog', 'cloud', 'hid', 'matter']) {
    const html = instance._renderAddIconPicker({kind, icon: 'washer'});
    assert.match(html, /data-add-icon="device"/);
    assert.match(html, /data-add-icon="washer"[^>]*aria-label="[^"]*"[^>]*aria-pressed="true"/);
    assert.match(html, /profile-28\.png/);
  }
  assert.match(instance._renderAddIconPicker({kind: 'catalog'}), /data-add-icon="device"[^>]*aria-pressed="true"/);
  assert.match(instance._renderAddIconPicker({kind: 'catalog'}), /picture of the IR model/);
});

test('every row of the installed table can be deleted, whether or not Studio knows it', async () => {
  const instance = panel();
  instance._physicalBusy = false;
  instance._deviceTable = {rows: [{slot: 6, kind: 'native', device_type: '0x02', control_type: 0,
    device_id: '100e0e0000020000000000', target_mac: '02:00:00:0E:0E:10'}], next_free_slot: 7};
  const html = instance._renderDeviceTable();
  assert.match(html, /data-delete-row="6"[^>]*data-row-type="0x02"[^>]*data-row-control="0"[^>]*data-row-id="100e0e0000020000000000"/);

  const sent = [];
  instance._hass = {callWS: async (msg) => { sent.push(msg); return msg.type.endsWith('/table') ? {rows: []} : {}; }};
  instance._render = () => {};
  instance._load = async () => {};
  instance._notify = () => {};
  instance._entryId = 'entry';
  context.confirm = () => true;
  await instance._deleteTableRow({deleteRow: '6'});
  const request = sent.find((msg) => msg.type.endsWith('/physical/delete_row'));
  assert.deepEqual([request.slot, request.device_type, request.control_type, request.device_id],
    [6, 2, 0, '100e0e0000020000000000']);
  context.confirm = () => false;
  sent.length = 0;
  instance._deviceTable = {rows: [{slot: 6, kind: 'native', device_type: '0x02', control_type: 0, device_id: 'aa', target_mac: 'x'}]};
  await instance._deleteTableRow({deleteRow: '6'});
  assert.equal(sent.length, 0);
});

test('a templated caption has no byte limit, shows what is on the remote and saves with its interval', async () => {
  const instance = panel();
  const remote = {remote_id: 'mt', name: 'Hall', icon: 'device', matter: {
    captions: ['A', 'Battery 80%', 'C', 'D'], fields: ['A', "Battery {{ states('x') }}%", 'C', 'D'],
    max_bytes: 31, min_interval: 60, interval_range: [0, 3600]}};
  // The editor shows the template, the counter shows the text now on the remote.
  assert.match(instance._renderMatterCaptionFields(remote.matter.fields, 31, remote.matter.captions),
    /template · now on the remote: Battery 80%/);
  assert.equal(instance._captionsChanged(remote, {captions: remote.matter.fields}), false);
  const long = "Battery {{ states('sensor.a_very_long_entity_name_that_does_not_matter') }} percent";
  assert.equal(instance._captionsProblem(remote, {captions: ['A', long, 'C', 'D']}), '');
  assert.match(instance._captionsProblem(remote, {captions: ['A', 'x'.repeat(40), 'C', 'D']}), /longer than 31/);
  assert.match(instance._captionsProblem(remote, {interval: '-1'}), /between 0 and 3600/);
  assert.match(instance._captionsProblem(remote, {interval: '4000'}), /between 0 and 3600/);
  assert.equal(instance._captionsProblem(remote, {interval: '0'}), '');
  assert.equal(instance._captionsProblem(remote, {interval: '90'}), '');
  assert.match(instance._renderMatterInterval(90, [0, 3600]), /data-matter-interval="1" min="0" max="3600"[^>]*value="90"/);

  const sent = [];
  instance._remote = () => remote;
  instance._draftScope = () => 'mt';
  instance._entry = () => ({icon_artwork: {}});
  instance._appearanceDraftsByRemote = new Map([['mt', {name: 'Hall', icon: 'device',
    captions: remote.matter.fields, interval: '120'}]]);
  instance._hass = {callWS: async (msg) => { sent.push(msg); return {}; }};
  assert.equal(instance._hasAppearanceChanges(), true);  // only the interval changed
  await instance._saveAppearance();
  assert.equal(sent.length, 1);
  assert.equal(sent[0].min_interval, 120);
  assert.deepEqual(sent[0].captions, remote.matter.fields);  // the template travels, not its text
  assert.equal(remote.matter.min_interval, 120);
  assert.equal(remote.matter.captions[1], 'Battery 80%');  // unchanged until it is rendered again
});

test('Type default counts as a change from any nonzero icon, compared by wire code', () => {
  const instance = panel();
  instance._entry = () => ({icon_codes: {device: 0, tv: 10, washer: 14}});
  instance._draftScope = () => 'r';
  const check = (remote, icon) => {
    instance._remote = () => remote;
    instance._appearanceDraftsByRemote = new Map([['r', {name: remote.name, icon}]]);
    return instance._hasAppearanceChanges();
  };
  // The name can be a placeholder; the byte is what the remote carries.
  assert.equal(check({remote_id: 'r', name: 'TV', icon: 'device', icon_code: 10}, 'device'), true);
  assert.equal(check({remote_id: 'r', name: 'TV', icon: 'tv', icon_code: 10}, 'tv'), false);
  assert.equal(check({remote_id: 'r', name: 'TV', icon: 'washer', icon_code: 14}, 'device'), true);
  assert.equal(check({remote_id: 'r', name: 'TV', icon: 'device', icon_code: 0}, 'device'), false);
});

test('an IR remote imported from the account does not offer an icon it cannot write safely', () => {
  const instance = panel();
  instance._entry = () => ({icons: ['light', 'washer'], icon_artwork: {washer: 0x28}});
  instance._draftScope = () => 'r';
  instance._appearanceDraftsByRemote = new Map();
  instance._iconPickerFor = 'r';
  instance._physical = null;
  instance._nativeProfiles = [];
  const html = instance._renderAppearance({remote_id: 'r', name: 'TV', icon: 'tv', device_type: 'IR_2', icon_editable: false});
  assert.doesNotMatch(html, /data-pick-icon/);
  assert.match(html, /imported from the SwitchBot account/);
  const own = instance._renderAppearance({remote_id: 'r', name: 'TV', icon: 'tv', device_type: 'IR_2', icon_editable: true});
  assert.match(own, /data-pick-icon="washer"/);
});

test('Type default and Original show the picture they give back', () => {
  const instance = panel();
  instance._entry = () => ({icons: ['light', 'washer'], icon_artwork: {light: 0x0c, washer: 0x28}});
  instance._draftScope = () => 'r';
  instance._appearanceDraftsByRemote = new Map();
  instance._iconPickerFor = 'r';
  instance._physical = null;
  instance._nativeProfiles = [];
  const render = (remote) => instance._renderAppearance({remote_id: 'r', name: 'R', icon: 'washer', ...remote});
  // native: the picture the device type has; HID/IR: the picture of the remembered original icon
  const native = render({device_type: 'STRIP', can_test_native_icon: true, default_artwork_id: 0x16});
  assert.match(native, /data-pick-icon="device"[^>]*>\s*<img class="ic-art" src="[^"]*profile-16\.png"/);
  const hid = render({device_type: 'APPLE_TV', default_artwork_id: 0x0c});
  assert.match(hid, /data-pick-icon="device"[^>]*>\s*<img class="ic-art" src="[^"]*profile-0c\.png"/);
  // nothing known: the placeholder stays
  const unknown = render({device_type: 'IR_24'});
  assert.match(unknown, /data-pick-icon="device"[^>]*>\s*<span class="ic-art ic-art-default"/);
  // Add dialog: native type default and the text remote's own picture
  instance._sources = {native_options: {screen_profiles: []}};
  const matter = instance._renderAddIconPicker({kind: 'matter', icon: 'device'});
  assert.match(matter, /data-add-icon="device"[^>]*>\s*<img class="ic-art" src="[^"]*profile-1b\.png"/);
  // IR from the catalog or the account: the picture of the chosen remote type (2 = TV)
  instance._catalog = {remoteType: 2};
  assert.match(instance._renderAddIconPicker({kind: 'catalog', icon: 'device'}),
    /data-add-icon="device"[^>]*>\s*<img class="ic-art" src="[^"]*profile-18\.png"/);
  instance._sources = {cloud_remotes: [{remote_id: 'a', name: 'TV', device_type: 2}]};
  assert.match(instance._renderAddIconPicker({kind: 'cloud', icon: 'device', remoteId: 'a'}),
    /data-add-icon="device"[^>]*>\s*<img class="ic-art" src="[^"]*profile-18\.png"/);
});

test('tiles dragged on the remote screen are sent as one order, with unknown rows kept in place', async () => {
  const instance = panel();
  const rows = [
    {slot: 0, kind: 'ir', device_type: '0x18', control_type: 1, device_id: 'aa', target_mac: 'x', name: 'TV'},
    {slot: 1, kind: 'native', device_type: '0x72', control_type: 0, device_id: 'bb', target_mac: 'y', name: 'Strip'},
    {slot: 2, kind: 'hid', device_type: '0xF2', control_type: 4, device_id: 'cc', target_mac: 'z', name: ''},
    {slot: 3, kind: 'ir', device_type: '0x02', control_type: 1, device_id: 'dd', target_mac: 'w', name: 'Lamp'},
  ];
  // Studio knows slots 0, 1 and 3 (and a scene); slot 2 is a row it has no record of.
  const remotes = [
    {remote_id: 'tv', kind: 'ir', remote_slot: 0, name: 'TV', device_type: 'IR_2'},
    {remote_id: 'scene:1', kind: 'scene', scene_index: 1, name: 'Movie', color: 1, icon: 1},
    {remote_id: 'strip', kind: 'native', remote_slot: 1, name: 'Strip', device_type: '0x72'},
    {remote_id: 'lamp', kind: 'ir', remote_slot: 3, name: 'Lamp', device_type: 'IR_14'},
  ];
  instance._entry = () => ({entry_id: 'entry', remotes});
  instance._physicalBusy = false;
  instance._render = () => {};
  instance._entryId = 'entry';
  instance._remoteId = 'tv';
  instance._screenOrder = null;
  assert.equal(instance._screenOrderChanged(), false);
  assert.equal(instance._renderScreenOrderBar(), '');
  assert.match(instance._renderScreen({index: 0}), /data-screen-grip="3"/);
  assert.doesNotMatch(instance._renderScreen({index: 0}), /data-screen-grip="[^"]*"[^>]*>[^<]*<\/span>\s*<button[^>]*scene/);

  instance._screenOrder = [3, 0, 1];      // the lamp is dragged to the top
  assert.equal(instance._screenOrderChanged(), true);
  assert.deepEqual(instance._screenRemotes().map((item) => item.remote_id),
    ['lamp', 'scene:1', 'tv', 'strip']);  // the scene keeps its place
  const screen = instance._renderScreen({index: 0});
  const bar = instance._renderScreenOrderBar();                      // above the remote, not inside its screen
  assert.match(bar, /id="applyScreenOrder"/);
  assert.match(bar, /id="resetScreenOrder"/);
  assert.doesNotMatch(screen, /id="applyScreenOrder"/);
  assert.ok(screen.indexOf('data-screen-slot="3"') < screen.indexOf('data-screen-slot="0"'));
  assert.doesNotMatch(screen, /data-screen-grip="[^"]*"[^>]*>[^<]*<\/span>\s*<button class="k pick-remote" type="button" data-remote="scene/);

  const sent = [];
  instance._hass = {callWS: async (msg) => { sent.push(msg); return {rows}; }};
  instance._load = async () => {};
  instance._notify = () => {};
  instance._readDeviceTable = async () => { instance._deviceTable = {rows, order: rows.map((row) => row.slot), open: true}; };
  context.confirm = () => false;
  await instance._applyScreenOrder();
  assert.equal(sent.length, 0);           // not confirmed: nothing is sent, the pending order stays
  assert.deepEqual(instance._screenOrder, [3, 0, 1]);
  context.confirm = () => true;
  await instance._applyScreenOrder();
  const request = sent.find((msg) => msg.type.endsWith('/physical/reorder'));
  // The screen lists rows from the highest slot down, so the dragged order is reversed for the table;
  // the unknown row (slot 2) stays where it was.
  assert.deepEqual(request.order, [1, 0, 2, 3]);
  assert.deepEqual(request.expected.map((item) => [item.slot, item.device_type, item.control_type]),
    [[0, 0x18, 1], [1, 0x72, 0], [2, 0xF2, 4], [3, 0x02, 1]]);
  assert.equal(instance._screenOrder, null);       // applied: the pending order is gone
});

test('dropping a row next to another gives the same order the buttons would', () => {
  const instance = panel();
  assert.deepEqual(instance._reorderSlots([0, 1, 2, 3], 3, 0, false), [3, 0, 1, 2]);  // above the first
  assert.deepEqual(instance._reorderSlots([0, 1, 2, 3], 0, 3, true), [1, 2, 3, 0]);   // below the last
  assert.deepEqual(instance._reorderSlots([0, 1, 2, 3], 1, 2, true), [0, 2, 1, 3]);   // after a neighbour
  assert.deepEqual(instance._reorderSlots([0, 1, 2, 3], 2, 2, true), [0, 1, 2, 3]);   // onto itself: unchanged
  assert.deepEqual(instance._reorderSlots([0, 1, 2], 9, 1, true), [0, 1, 2]);         // unknown slot: unchanged
  instance._deviceTable = {rows: [{slot: 0, kind: 'ir', device_type: '0x18', control_type: 1, device_id: 'a', target_mac: 'x'},
    {slot: 1, kind: 'ir', device_type: '0x02', control_type: 1, device_id: 'b', target_mac: 'y'}], order: [0, 1]};
  instance._physicalBusy = false;
  const html = instance._renderDeviceTable();
  assert.doesNotMatch(html, /data-drag-handle|data-move-row/);  // the order is set on the remote's screen
  assert.match(html, /<tr data-row-slot="1">/);
});

test('adding a scene is checked against the scene limit like any other install', () => {
  const instance = panel();
  const scenes = Array.from({length: 10}, (_, index) => ({kind: 'scene', scene_index: index}));
  instance._entry = () => ({remotes: scenes, scene_limit: 10});
  assert.match(instance._installCapacityError({kind: 'scene'}), /ten scenes/);
  instance._entry = () => ({remotes: scenes.slice(1), scene_limit: 10});
  assert.equal(instance._installCapacityError({kind: 'scene'}), '');
});

test('capacity row counts the single text remote', () => {
  const instance = panel();
  instance._sources = null;
  instance._entry = () => ({remotes: [{kind: 'native'}], scene_limit: 10});
  assert.match(instance._renderRemoteCapacity(), /Text remotes available <b>1\/1<\/b>/);
  instance._entry = () => ({remotes: [{kind: 'native', matter: {captions: []}}], scene_limit: 10});
  assert.match(instance._renderRemoteCapacity(), /Text remotes available <b>0\/1<\/b>/);
  instance._entry = () => ({remotes: [], scene_limit: 10});
  instance._sources = {matter: {installed: true}};
  assert.match(instance._renderRemoteCapacity(), /Text remotes available <b>0\/1<\/b>/);
});

test('the catalog brand search keeps its text and filter while a brand or model is chosen', () => {
  const instance = panel();
  instance._entry = () => ({icons: []});
  instance._sources = {catalog: true, cloud: true, cloud_remotes: [], native_options: {screen_profiles: []}, remote_capacity: {}};
  instance._catalog = {available: true, types: [{value: 2, label: 'TV'}], remoteType: 2,
    brands: ['Samsung', 'Sony', 'LG', 'Sanyo'], brand: 'Sony', search: 'so', models: [{hxd_index: 'a', label: 'Bravia'}],
    hxd: '', buttons: [], busy: '', error: ''};
  instance._add = {kind: 'catalog', icon: 'device', name: ''};
  const html = instance._renderAddRemote();
  assert.match(html, /data-catalog="search"[^>]*value="so"/);
  const list = html.slice(html.indexOf('data-catalog="brand"'), html.indexOf('data-catalog="model"'));
  assert.match(list, /Sony/);
  assert.doesNotMatch(list, /Samsung|Sanyo|LG/);
  assert.deepEqual(instance._catalogBrands(), ['Sony']);
  instance._catalog.search = '';
  assert.equal(instance._catalogBrands().length, 4);
});

test('the IR ways to add a remote sit in one IR tab, with an empty remote among them', () => {
  const instance = panel();
  instance._entry = () => ({entry_id: 'entry', remotes: [], icons: []});
  instance._sources = {native: true, catalog: true, cloud: true, cloud_remotes: [], hid: {device_types: ['APPLE_TV']},
    matter: {installed: false}, remote_capacity: {ir: {available: 5}}};
  instance._catalog = {available: true, types: [{value: 2, label: 'TV'}], remoteType: 2, brands: [], brand: '',
    search: '', models: [], hxd: '', buttons: []};
  instance._add = {kind: 'native', name: '', icon: 'device', deviceType: ''};
  let html = instance._renderAddRemote();
  assert.equal((html.match(/data-add-group="ir"/g) || []).length, 1);
  assert.doesNotMatch(html, /data-add-kind="(catalog|cloud|blank)"/);       // no sub-tabs outside the IR tab
  instance._add = {kind: 'blank', name: '', icon: 'device', blankType: 6};
  html = instance._renderAddRemote();
  for (const kind of ['catalog', 'cloud', 'blank']) assert.match(html, new RegExp(`data-add-kind="${kind}"`));
  assert.match(html, /data-add-field="blank_type"/);
  assert.match(html, /<option value="6" selected>Fan<\/option>/);
  assert.match(html, /profile-09\.png/);                                       // the fan's own picture
  instance._sources.remote_capacity.ir.available = 0;
  assert.match(instance._installCapacityError(instance._add), /IR remotes/);   // an empty one counts as IR
});

test('a removed main-page key is empty on the face, not drawn with the stock profile picture', () => {
  const instance = panel();
  instance._remote = () => ({remote_id: 'strip', pages: [], device_type: 'STRIP'});
  instance._nativeProfile = () => ({main_positions: [0, 1, 2, 3, 4, 5],
    main_keys: [{index: 2, function: 322}, {index: 0, function: 321}], subpages: []});
  // Key C (index 2) was removed from the layout; key A (index 0) is still there.
  instance._physical = {kind: 'native', template: 'STRIP', pages: [
    {index: 0, buttons: [{index: 0, transport: 'native', function: 321}, {index: 4, transport: 'native', function: 5}]}]};
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._physicalOrigins = {};
  instance._profileFunctionLabel = () => 'Function';
  instance._layoutState = () => 'unchanged';
  const main = instance._pages().find((page) => page.index === 0).buttons;
  assert.equal(main.find((item) => item.button_index === 2).layout_empty, true);
  assert.equal(main.find((item) => item.button_index === 0).layout_empty, false);
  // the stock function is still known (to assign something), but it is not what the face draws
  assert.equal(main.find((item) => item.button_index === 2).button_function, 322);
});

test('a submenu row is captioned like the remote does, from the picture it carries', () => {
  const instance = panel();
  instance._remote = () => ({remote_id: 'strip', pages: [], device_type: 'STRIP'});
  instance._nativeProfile = () => ({main_positions: [0, 1, 2, 3, 4, 5], main_keys: [], subpages: []});
  instance._physical = {kind: 'native', template: 'STRIP', pages: [
    {index: 0, buttons: []},
    {index: 4, buttons: [
      {index: 0, transport: 'native', function: 333, glyph: 331},   // picture of "Color 1"
      {index: 1, transport: 'native', function: 21, glyph: 332},
      {index: 2, transport: 'native', function: 22},                  // no picture of its own
      {index: 3, transport: 'native', function: 22, glyph: 332, title: 'Mine'}]}]};
  instance._physicalBaseline = structuredClone(instance._physical);
  instance._physicalOrigins = {};
  instance._profileFunctionLabel = (fn) => `Function ${fn}`;
  instance._layoutState = () => 'unchanged';
  const rows = instance._pages().find((page) => page.index === 4).buttons.map((item) => item.label);
  assert.deepEqual(rows, ['Color 1', 'Color 2', 'Function 22', 'Mine']);
});
