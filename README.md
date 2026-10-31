# SwitchBot Universal Remote — Home Assistant (Work in progress, contain bugs)

<img width="2800" height="3142" alt="image" src="https://github.com/user-attachments/assets/873e0168-d907-4101-bd9c-f072dde912e0" />


Two local pieces, no SwitchBot hub and no cloud dependency for anything on the BLE path:

- a custom integration that configures the WoRWS remote over its encrypted BLE protocol;
- an add-on that presents a fake native SwitchBot device, accepts the remote's button commands
  over GATT and publishes them to MQTT.

Protocol details and what has actually been verified on hardware are in `PROTOCOL.md`.

## Disclaimer

This project is not affiliated with, endorsed by, or supported by SwitchBot. SwitchBot and
related names are trademarks of their respective owners.

It talks to the remote over an undocumented BLE protocol recovered by analysing the device's
own firmware and the vendor's app. Nothing here is sanctioned by the vendor: a firmware or app
update can break it at any time, and misuse can leave a remote in a state that needs
re-pairing. Use it at your own risk, on hardware you own.

## Requirements

- Home Assistant OS or Supervised.
- Two BLE controllers. One stays with Home Assistant to talk to the WoRWS; the other is handed
  entirely to the add-on as a BLE peripheral. The second adapter must not also be used by Home
  Assistant as a scanner — disable it under Settings → Connectivity → Bluetooth → Adapters.
- A SwitchBot account, or the WoRWS communication key and key id if you would rather not
  connect one. The key rotates, and the account is where it comes from.
- A separate 16-byte AES key of your choosing for the fake device. The same value goes in the
  add-on configuration and in `bind_native`.

## Install

1. Copy `custom_components/switchbot_urc/` to `/config/custom_components/switchbot_urc/` and
   restart Home Assistant.
2. Add the **SwitchBot Universal Remote (WoRWS)** integration. Home Assistant normally
   discovers the remote over Bluetooth and fills in its address. Leave the key and key ID empty
   and sign in to your SwitchBot account on the next screen: the communication key is fetched
   from the account, which is where it comes from anyway and which is also where it rotates.
   Entering the key by hand still works if you do not want to connect an account.
3. Install the bridge add-on from
   [switchbot-urc-addon](https://github.com/batareya16/switchbot-urc-addon): add that repository
   under Settings → Add-ons → Add-on Store → ⋮ → Repositories, install **SwitchBot URC Bridge**,
   assign it the spare BLE adapter, set `device_key`, and start it.
4. Check the add-on log for the GATT server and advertising, and note its adapter MAC. The add-on
   must be running during bind — the remote may check that the target answers.

## Creating a native bridge remote

Settings → Devices & Services → SwitchBot Universal Remote → **Configure** →
**Add remote → Add native remote**. Enter the add-on adapter's MAC and the same `device_key` the
add-on uses. The form reads the device table first, picks the required sequential index itself,
runs all three commands and, on failure, shows which stage failed and what the device answered.

If that MAC already belongs to a remote, the form requires **Replace existing target**, deletes
the exact match and re-checks the table before binding.

The target-key id is fixed by the protocol (`01`) and is not the remote's own communication
`key_id`. Native control mode is likewise fixed at `00`: other values can bind successfully and
then never connect to the target on a press.

The service runs three commands in one BLE session:

1. `0F 20 09` — store the target's key;
2. `0F 20 08` — associate that key with the target address;
3. `0F 62 06` — write the native page(s).

Each stage must return `01`, and each result is also fired as a `switchbot_urc_native_bind` event.
`62 0A` is deliberately not used: it is a full device-order table, not a registration, and a
partial one can hide remotes that already exist.

Everything runs as one transaction — new connection, handshake, commands, disconnect. Each stage
gets up to 35 seconds and up to three retries, each in a fresh connection with a fresh IV. An
explicit error reply (`02`, `04`, …) is never retried.

### As an action

```yaml
action: switchbot_urc.bind_native
data:
  name: HASS Bridge
  device_id: "AA:BB:CC:DD:EE:FF"
  device_type: STRIP
  icon: strip
  target_key: "00112233445566778899aabbccddeeff"
  replace_existing: false
```

`device_id` is the add-on adapter's MAC, not the remote's. `target_key` is the fake device's key,
not the remote's. `remote_index` is no longer needed: the service reads the table and uses its
length, exactly as the official app does.

### Editing the layout afterwards

The native type chosen at creation is only a starting template. Any native remote can be opened
through **Manage existing remote → Edit pages and buttons** to change Main, pages A–D and the
function of each physical position. A native remote created before this existed gets an editable
copy of its stock profile the first time the editor opens.

Applying a physical layout uses a delete/recreate transaction, but the stable `remote_id`, Quick
Bind and the individual Home Assistant actions survive it. Remote Studio's **Edit layout** button
leads to the same editor.

## IR remotes

**Remote manager → Add IR remote** offers three paths:

- install a remote already saved in the SwitchBot cloud (`code`, `keyMap`, AC fast-binaries and
  custom key details via `queryIrRemote`);
- add from the IR catalog (`custom_components/switchbot_urc/ir_catalog.db`): type → brand →
  model, with the code bank fetched through the official `querymodel` and a cloud record created
  after BLE install;
- use the captured fallback TV profile, offline.

The integration unpacks the base64/zlib code bank the way the app does, checks every `keyMap`
offset, builds up to five `0F 62 06` pages and runs a full sync. Slot, remote count, CRC and
packet fragmentation are computed automatically. If the local install succeeds but the cloud save
fails, re-submitting the form retries only the cloud part.

### About the IR catalog file

`ir_catalog.db` holds only IR **metadata** — device type, brand, model and the `hxd_index` used
to request a code bank. No IR codes are in it; those come from SwitchBot's cloud with your own
account. It is derived from `assets/IRLibarayDb.pack` in the SwitchBot Android app, which is a
gzip-compressed SQLite database, and the data in it belongs to SwitchBot.

The file is **optional**. If it is absent, the catalog path is simply not offered and the other
two IR paths work unchanged. To build your own from an app APK you already have:

```bash
python3 tools/build_ir_catalog.py --apk /path/to/switchbot_assets.apk \
    --output custom_components/switchbot_urc/ir_catalog.db
```

Nothing is downloaded and nothing leaves the machine. In a split install the asset usually lives
in `switchbot_assets.apk`; the script prints which entry it used and the library version.

These buttons transmit IR from the WoRWS itself — the bridge add-on and MQTT are not involved.

## HID remotes

A HID remote turns the WoRWS into a BLE-HID keyboard bonded to a host, and presses go straight to
that host as HID reports. Pair first (`hid_pair`), then create the profile; a create before the
pairing exists returns `11`. The host must accept an incoming BLE-HID bond — macOS refuses, Linux
with BlueZ can be configured for it. Usage maps and device types are in `PROTOCOL.md`.

## Remote manager and the cloud account

**Configure → Remote manager** reads the real `0F 63 07` table every time it opens, matches it
against locally created and cloud remotes by stable id, and shows one list. Add, rename and delete
do not take a slot number: the current index is resolved immediately before the command, and the
firmware's table compaction after a delete is accounted for.

Connecting a SwitchBot cloud account is optional and can be done later through **Configure**. It
needs only the account email and password; the integration follows the app's login flow, resolves
the region and home itself, and does not store the password. Accounts created solely through
Google/Apple/Amazon sign-in need a different auth flow and will not work with password login. The
cloud is used only for IR and HID lists and names — every BLE operation against the WoRWS stays
local.

**Refresh all remotes from device + cloud** re-reads both sides, merges them by stable id and
saves a cleaned snapshot with a timestamp. Opening the Remote manager does the same automatically.

### Adding and removing remotes from Studio

The remote selector has **Add native remote** and **Delete remote**. Creating reuses the bridge
credentials captured when the first native remote was installed, so it only asks for a name;
IR and HID remotes still need the integration settings, because one needs a catalogue choice and
the other a pairing step. Deleting reads the device table, proves the row is there, performs the
single destructive write in that same session and then re-reads the table before dropping the
local record.

### Whether a press reaches Home Assistant

Each remote says so, because offering an action for a press that never arrives is the most
confusing thing the panel can do:

- **native** — presses go to the bridge add-on and arrive as Home Assistant events;
- **HID** — presses go to the host the remote is paired with, and reach Home Assistant only when
  that host is this machine and it is connected;
- **IR** — the remote transmits to the appliance and nothing comes back. For these the Home
  Assistant mapping is not offered at all; the key itself stays editable.

## Diagnostics and maintenance

**Configure → Diagnostics and maintenance** groups the checks that are only needed when
something is wrong: a connectivity test that reaches the fake target from Home Assistant's other
adapter (so an add-on problem can be told apart from a remote problem), a read-only sweep of the
`0F 63` query namespace, and HID pairing to a host.

**Update WoRWS communication key** stays in the main menu on purpose: the key rotates, every
command starts failing with `04` when it does, and that is not the moment to go hunting through
submenus.

## Remote Studio

The integration registers an admin page **Remote Studio** in the sidebar. It shows any locally
managed remote, switches between its Main/A/B/C/D pages, displays the stable id and slot, applies
Quick bind to a light, and lets each physical button be selected on a graphical mock-up. The dot
colour shows where the action comes from: blue Quick bind, green a per-button Home Assistant
action, red disabled, grey none. **Test** sends a normalized press through the same dispatcher,
and real presses light up live over WebSocket. The action editor uses the standard `ha-selector`
with a JSON fallback, and the backend validates with the standard Script validator before saving.

Remotes created in the SwitchBot app do not appear in Studio by themselves: the integration
sees them in the device table but has no record of what their buttons do. **Refresh** picks them
up, each kind by the only means available:

- IR — `queryIrRemote` returns the same code bank and key map the app installed, and the pages
  are rebuilt from it;
- HID — `getButtonData` returns the saved button list;
- native — nothing needs downloading: the app installs one of the stock profiles, and Studio
  renders those from the device type alone.

Nothing is written to the remote by any of this. An IR or HID remote with no saved cloud record
cannot be rebuilt, and a native remote of an unrecognised type is skipped; both are reported.

Every button is edited in one place. Selecting it on the mock-up shows both what the key *is*
on the remote — its command type, function, or IR code — and what Home Assistant does when it is
pressed. There is no separate layout mode.

One **Save** stores everything for that button: the names, the Home Assistant mapping, and —
only when the key itself changed — the layout on the remote. The button says "Save and write to
remote" when a device write is part of it, and a bar above counts the outstanding changes.
Nothing is written to the remote unless its layout actually differs, because for a native
remote any such change is a full delete and recreate.

Giving a Main A–D key the function **Open a custom page** creates a new, empty page tab and
turns that key into its link. Buttons are added to it the same way as anywhere else.

The button editor also shows **Installed on the remote**: the device table read from the remote
itself — slot, kind, type, target address and the next free slot. It is read-only and a failure to
read it does not block the editor. When several native profiles share one target address, the
block says so: the firmware stores the same id for all of them, presses are served by the first,
and the others' buttons do nothing.

A table row is identified by its slot, not by its device id. When several rows carry the same id,
the editor picks the row whose slot matches the stored one.

## Custom native remotes and bindings

The **Custom Native Remote Builder** creates a main screen plus the chosen A–D sub-pages, links
the pages, keeps readable page names in Home Assistant, and writes a bridge event on every active
button carrying `device_type=CUSTOM`, the page, index and a semantic function. The screen template
is the native Fan profile — the one recovered handler that opens all four sub-pages.

Only icons built into the WoRWS firmware are sent to the screen. Arbitrary images and general
screen-state synchronisation are not confirmed in the protocol and are deliberately not faked.

**Remote bindings** in the integration options has **Quick bind**, which binds a whole logical
remote to a light by its stable `remote_id` (ON/OFF for power, brightness in 10% steps,
LEFT/RIGHT for colour temperature), and **Edit mappings** for changing the light, disabling the
binding or assigning an action per button group. Changing a mapping does not rewrite the WoRWS and
does not depend on the physical slot.

A diagnostic **Battery** sensor is created for the remote. It updates passively from the FD3D
advertisement and never wakes the remote with an extra connection.

## Verifying presses

Leave `diagnostic_scan: false`, open the new remote on the WoRWS and press a few buttons. The
add-on log should show `connected=True`, `notify sub=True`, `REMOTE wrote`, then the decoded
command. The add-on publishes to `switchbot_urc/button` and the integration re-fires it:

```yaml
event_type: switchbot_urc_button
event_data:
  source: mqtt
  button: ON
```

Each active button sends a short bridge event. The MQTT JSON carries `device_type`, `remote_id`,
`remote_slot`, `button_page`, `button_index`, `button_function`, a stable `button_id` and
`button_icon`.

Repeated connect / discovery / disconnect lines before a delivered press are normal for this
remote and bridge, and happen for a tile that works.

## Actions

- `switchbot_urc.bind_native` — the full native provisioning sequence above.
- `switchbot_urc.create_remote` — send one `0F 62 06` page; for a new native target `bind_native`
  is easier and safer.
- `switchbot_urc.delete_remote` — delete a remote (`0F 62 04 02`). For a native remote it then
  re-sends `0F 20 08` automatically if another native profile still targets the same address: the
  firmware's key entry is keyed on the address, not on the profile, so the survivor would
  otherwise be left without a key.
- `switchbot_urc.dump_device_table` — read the remote's device table (`0F 63 07`) and return slot,
  type, control type, the eleven-byte id, the target MAC and the id tail. Read-only.
- `switchbot_urc.send_command` — raw plaintext hex, without the `57` transport magic.
- `switchbot_urc.send_command_sequence` — several raw commands in **one** session, as binding
  does, with a response per step. Needed for commands the firmware only accepts after an earlier
  command in the same connection, and for diagnostics: send `02` as step 0 and discard the run
  unless it answers `01`.
- `switchbot_urc.poll_status` — status poll (`02`).
- `switchbot_urc.hid_pair` — HID-pair the remote to a host.
- `switchbot_urc.set_state_ac` — push AC state to the screen.

Command replies are logged: `01` ok, `02` value error, `04` format error or an unusable session,
`05` duplicate device id, `11` HID not paired.

## Known limits

- **Several native tiles on one adapter MAC do not work.** They can be installed — the bind check
  reads eleven id bytes and a distinct tail passes it — but the firmware stores only the six-byte
  address, so the rows become indistinguishable and presses on the second tile are served by the
  first profile's data. Separate tiles need separate BLE addresses. Measured on hardware; the full
  evidence is in `PROTOCOL.md`.
- **Button count is not the limit.** A native profile allows 18 buttons per page across Main and
  A–D, about 91 positions against the firmware's ceiling of 100 keys.
- **Mixed profiles**: a key's type cannot be changed to cross transports, and the screen type
  cannot be chosen independently of the transport. The one untested combination is a HID screen
  with named IR keys.

## Credentials and what is stored

- The SwitchBot account password is sent only to SwitchBot's own account endpoint and is never
  stored. Only the renewable tokens it returns are kept, in the config entry — Home Assistant's
  normal credential store.
- The WoRWS communication key, the fake target's key and the account tokens are never written to
  the log. The cloud module logs only the resolved region, the endpoint and how many homes were
  returned.
- The Remote Studio panel receives remote metadata and the device address over its WebSocket API,
  and no key material. Every one of its commands requires an admin user.
- Key fields in the configuration forms are masked.
- The integration ships no diagnostics handler, so nothing is bundled into a downloadable
  diagnostics file.

## Troubleshooting

**Bind reports that the encrypted reply could not be decoded.** The remote's communication key
has rotated or is wrong. Open **Configure → Update WoRWS communication key**, enter a fresh
`key_id` and key, wait for the reload and retry. This is not the add-on's `device_key` — the
remote and the fake device have different credentials.

**`0x04` during `set_key`.** The integration first tries to fetch a fresh communication key
through the configured SwitchBot cloud, saves it and reloads; retry the bind once afterwards. If
no cloud account is configured, or it returned the same key, update the key manually.

**A command fails for no apparent reason.** A session can reject its first command with `04` even
when that command is a one-byte status poll that works a minute later. The client now retries the
whole step list once with a new connection and handshake in that case. When testing by hand, send
`02` first and discard any run where it does not answer `01`.

## License

Apache License 2.0 — see `LICENSE`. Section 7 ("Disclaimer of Warranty") and section 8
("Limitation of Liability") of that licence apply to everything in this repository.
