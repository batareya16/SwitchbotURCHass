# SwitchBot Universal Remote (WoRWS) — protocol reference

Everything here is either read out of the firmware or measured on a live remote. Claims that
only came from emulation or from a single unverified observation are marked as such. Where an
earlier conclusion was later disproved, the correction is stated rather than quietly dropped.

Companion documents:

- `README.md` — the Home Assistant integration.
- [`docs/native-screen-capabilities.md`](docs/native-screen-capabilities.md) — V48 screen,
  page, glyph, and Remote Studio constraints, with unresolved device experiments.
- [switchbot-urc-addon](https://github.com/batareya16/switchbot-urc-addon) — the
  fake-target bridge add-on, published separately.

Function-level firmware evidence, including the emulation fixtures and their reproduction
commands, is kept with the firmware images outside this repository.

## Disclaimer

This project is not affiliated with, endorsed by, or supported by SwitchBot. SwitchBot and
related names are trademarks of their respective owners.

It talks to the remote over an undocumented BLE protocol recovered by analysing the device's
own firmware and the vendor's app. Nothing here is sanctioned by the vendor: a firmware or app
update can break it at any time, and misuse can leave a remote in a state that needs
re-pairing. Use it at your own risk, on hardware you own.

## The device

- WoRWS Universal Remote, BLE name `FR5080_BLE`, chip FR5080 (Freqchip): an ARM Cortex-M0 host
  plus an Xtensa DSP. BLE only — no WiFi, no direct cloud path.
- GATT: service `cba20d00-224d-11e6-9fb8-0002a5d5c51b`, write `cba20002`, notify `cba20003`.
- Firmware images referenced throughout are V48 `ARM.bin` and `DSP.bin`; DSP instruction
  addresses are `0x20000000 + file offset`.

## Transport and crypto

Commands are AES-128-CTR. One frame:

```
57 <keyId> <iv[0:2]> <AES-CTR(plaintext)>
```

The plaintext omits the leading `0x57`. The session IV comes from a handshake, written with
**write-with-response**:

```
write  cba20002:  57 00 00 00 0F 21 03 <keyId>
notify cba20003:  01 00 00 00 <16-byte IV>        -> IV = reply[4:20]
```

Using write-without-response here can lose the first packet right after notification setup and
looks like a handshake timeout. The IV is fixed for the session and used for both directions.

Inventory reads such as `0F 63 07` are sent **unencrypted** as `57 00 00 00 0F 63 <sub>` and
answered unencrypted. The app sends its HID pairing status request via the encrypted channel on
V48.

**The communication key rotates.** `keyId` is a byte in the frame (`95` on this unit). When every
command starts returning `04`, the key has rotated; re-capture it from the app
(`Custom IR CRYPTO ENC key=` hook) or from the cloud key API,
`POST /wonder/keys/v1/communicate` with `{groupID, keyType:"user", device_mac}` and a bearer
token, which returns `{keyType, keyId, key}`. Keys are per-device secrets and are not recorded in
this repository.

### Response codes

| Code | Meaning |
| --- | --- |
| `01` | ok |
| `02` | value or operation error |
| `04` | format / parse error, or the session could not decrypt the command |
| `05` | duplicate device id on create |
| `11` | HIDNoPairError |

### Session health

A session can reject its **first** command with `04` even when that command is the one-byte
status poll that succeeds a minute later. Codes from such a session say nothing about the
command. Any measurement must start with `02` as step 0 and be discarded unless it answers `01`.
Several conclusions during the 2026-10-30 session were drawn from sessions that failed this check
and had to be withdrawn.

## Command map

| Plaintext | Meaning |
| --- | --- |
| `02` | status poll; the notify carries a status record |
| `0F 21 03 <keyId>` | get-random handshake (unencrypted envelope) |
| `0F 20 09 <keyId> <key16>` | store a target device's AES key |
| `0F 20 08 <keyId> <id11>` | associate that key with a target id |
| `0F 62 06 …` | create / write one page of a remote |
| `0F 62 04 02 <idx> <devType> <ctrl> <id11>` | delete a remote |
| `0F 62 07 …` | rename a remote |
| `0F 62 09 …` | replace the scene list |
| `0F 62 0A …` | full order table — **not** registration, see below |
| `0F 62 0E 01 <hostMac11>` | HID-pair the remote to a host |
| `0F 63 07` | list installed devices |
| `0F 63 06` | free storage |
| `0F 63 04` | list scenes |
| `0F 41 02 …` | push AC state to the screen |

`0F 62 0A` sends a complete order table `[count] + count × [remoteIndex][devType][idKind][id11]`.
It may answer `01` while changing the ordering or visibility of existing remotes, and it plays no
part in a normal create. Do not send a one-entry table.

## Scenes on WoRWS V48

The firmware trace for persistent title updates and incoming Native replies is in
[live-display-state.md](../firmware-worws/evidence/mixed-v48/live-display-state.md).

The remote stores a separate scene list with up to ten entries. Each entry holds its index,
display name, icon and color. Home Assistant can keep the mapping from a physical remote and
scene index to a Home Assistant action.

### Reading and writing the list

```
Read plaintext:  0F 63 04
Read response:   01 <length16 BE> <crc16 BE> <count> <records...>
Write plaintext: 0F 62 09 <length16 BE> <crc16-MODBUS BE> <count> <records...>
Record:          <index> <name: 64 bytes, NUL-padded> <icon> <color>
```

- The record is 67 bytes. Use unique indices from 0 to 9 and terminate names within the 64-byte
  field. The body length is `1 + 67 × count`. The write CRC covers the full body, including count.
- A write replaces the whole list. Unspecified indices are cleared, and count zero clears the
  list. Read the current list before merging changes and read it back after writing.
- V48's read path calls CRC16-MODBUS with the same length but starts at the first record, one byte
  after count. This includes a byte beyond the transmitted records. The SwitchBot app checks the
  count against the received length. Capture real replies before enforcing a read CRC.
- ARM references in V48 are `0x2e7e` for read, `0x3868` for write dispatch, and `0x4dec` for
  storing the list. The write path forwards it to the DSP over IPC type `0x0a`.

### Receiving a scene activation

The DSP scene path calls `0x200345ec`, then `0x20004b70`. It sends ARM IPC type `0x0e`,
subtype `0x03`, with the scene index at byte 1. The ARM receiver at `0x1c8f8` sends this
index to `0xd4fc`, which sets BLE advertisement event type `0x02`. The manufacturer data
builder at `0x211e0` serializes it as follows, with offsets relative to the manufacturer
payload after company ID `0x0969`.

| Offset | Size | Field |
| --- | ---: | --- |
| 0 | 6 | Physical WoRWS address bytes |
| 6 | 1 | Nonzero rolling event sequence |
| 7 | 1 | Status bits |
| 8 | 1 | Scene index, 0–9 |
| 9 | 1 | Zero in the V48 builder |
| 10 | 1 | Event type, `0x02` for scene |
| 11–12 | 2 | Key state (high 3 bits) and counter (low 5 bits), one pair per byte |
| 13–16 | 4 | Other packed event state and counters |

ARM `0xd288` forwards qualifying key events to `0xd86c`, which increments the sequence,
skips zero on wraparound, and refreshes the advertisement through `0x20994`. On this path
only masks `0x10` and `0x200` trigger a counter increment and refresh, updating byte 11 or 12
respectively. Other ARM paths also call `0xd86c`, so a change to byte 6 alone cannot establish
that the scene was pressed again.

One DSP call site, `0x2002f401`, passes a fixed key code from `0x2000d370`. The key table
maps this code (`0x100000`) to bit 14, which only latches the scene index on this ARM path.
The other site, `0x2002f4d4`, passes the incoming key code and can take the immediate refresh
path. Capture each way of activating a scene to establish when its advertisement is emitted.

The DSP and ARM paths above are static firmware evidence. Capture activation of two different
indices, repeated presses of the same scene, and unrelated key presses after a scene. Use those
captures to confirm which counter identifies a fresh activation and how it behaves on restart.
The battery sensor already uses passive Bluetooth callbacks for the physical remote's address.

## Creating a remote (`0F 62 06`)

```
0F 62 06 <len16 BE> <crc16-MODBUS BE>
  [remoteIndex][devType][controlType][controlMode][icon]
  [deviceID: 11 bytes]
  [name: 64, NUL-padded, byte 63 = 0]
  [0x00, pageIndex, keyCount]
  per key: [keyIndex][keyFun 2B BE][keyType][field 32]
```

- `len16` and the CRC cover the body after the CRC field.
- `deviceID` is the six-byte MAC **reversed**, padded to eleven bytes. Only the first six are
  transmitted by the remote; see "Multiple native profiles" for what the padding does.
- `field` is either a device command (20 bytes plus a length byte, padded to 32) or the key's
  function number padded to 32.
- `remoteIndex` must equal the current row count of the `0F 63 07` table. The firmware compacts
  the table on delete, so the next free index is always `len(table)`.
- Pages are written one per command, `pageIndex` 0–4.

`controlType` selects the transport and `devType` selects the on-screen profile, but the two are
not freely combinable — see "Mixed profiles".

| controlType | transport |
| --- | --- |
| 0 | native: connect out over BLE to the target address |
| 1 | IR: transmit from the remote |
| 3 | Matter |
| 4 | HID: act as a BLE-HID keyboard toward a paired host |

## Installed-device table (`0F 63 07`)

The reply body is a count followed by one record per remote:
`[remoteIndex][devType 1 or 4 bytes][controlType][deviceID 11]`. A four-byte device type begins
with `00`, which is how the two widths are told apart.

This table is the only reliable source for the slot index, and the slot — not the device id — is
what identifies a row. The integration exposes it as `switchbot_urc.dump_device_table`.

V48 also has a read-only details query, `0F 63 05`. ARM `0x2f70..0x3062` emits a count followed
by 80-byte records `[slot][type][controlType][controlMode][icon][id:11][name:64]`. The response
uses the same envelope as `0F 63 07` and can span several notifications. Studio checks the
native rows against `0F 63 07` and uses the reported mode and icon for appearance.

## Native targets

A native remote drives a real SwitchBot device by connecting **out** to it. The firmware path,
read from `ARM.bin` V48:

1. `0F 20 09` (`118cc`, case 9) stores a 16-byte key by key id.
2. `0F 20 08` (case 8) writes a `0x28`-byte association record: key, six-byte address, key id and
   type. 65 slots, persisted in a `0xA28`-byte block.
3. A DSP button event reaches `11d9c(remote_index, key_index, pressed)`. It requires the model's
   control type at `+2` to be zero, reads the six-byte target from `+0x59`/`+0x5d` and up to 20
   command bytes, looks up the key (`c614`) and key id (`c66a`), then queues the work.
4. `11f7c` is the BLE-central state machine; `1200c` opens the connection to the saved address.
   After discovery it writes the queued data.
5. The GATT UUIDs above are present in `ARM.bin` and match the bridge exactly.

The `cmp r6,#0x64` in `11d9c` bounds the remote index (`r0`, copied to `r6`),
not the key index (`r1`, copied to `r5`). The DSP key-record lookup `2002238c`
separately accepts key indexes `0..99`. The earlier attribution of the key bound
to the ARM comparison was incorrect.

Bridge remotes are installed without a target key association. The lookup leaves the queued key
zero, so the firmware skips the get-random exchange and sends the stored command over ATT
unchanged. The bridge acknowledges the button command with a `01` notification. The firmware
requeues commands without an accepted acknowledgement up to five times (`122f4`).

### Multiple native profiles on one address — measured 2026-10-30

Installable, not usable.

- The bind validator (`5b88`) compares **all eleven** id bytes. Two loops: a row at the requested
  index must carry the same id, and no other index may carry it. Writing the row stores
  `model+0x59` into the slot table at `+8` (`5e7e..5e94`).
- Everything on the send path reads only the first six bytes: `11d9c`, the work enqueue `20154`,
  the GATT write machine at `12100`, the key lookup `c614`, the key removal `c724` and the key-id
  lookup `ce08`.
- So an id with a distinct tail installs a second profile against the same address: sending
  `reversed MAC + 01 00 00 00 00` was accepted with `01`, while the plain id was refused `05`.
- **The tail is then discarded.** The table reports `id_tail 0000000000` for the new row while IR
  rows in the same table keep non-zero tails, so the report is not truncating it.
- With both rows storing the same id, a press on the second tile is delivered using the **first**
  profile's key record — observed as the original tile's `remote_id` and slot byte arriving at the
  bridge.

Therefore separate tiles need separate BLE addresses, not a crafted id. An earlier note claiming
that a non-zero tail "breaks the WoRWS connect after service discovery" is wrong: the same
connect/discover/disconnect churn happens for a tile that works.

Two further consequences:

- Such rows can only be deleted **by slot index**; by device id they are indistinguishable.
- Deleting a native row calls `c724`, which clears the key entry matched on the six-byte address
  and so takes the key away from any other profile on that address.

### Inventory reads through the user-channel bridge — hardware validation pending

Add-on 0.30.0 implements a central ATT client alongside its peripheral server. For an isolated
`0F6307` query it opens a public-address LE connection, exchanges MTU, discovers characteristics
and the notification descriptor, enables notifications, and sends the unencrypted query. It
does not establish a crypto session or change installed profiles. Existing peripheral links
remain in the event loop. Since 0.30.1, a failed read returns its raw-HCI error without falling
back to BlueZ or pausing the bridge. Protocol errors and confirmed physical disconnections are
tracked separately; a new inventory attempt cannot replace a connection still being closed.
Since 0.31.0 the multi-address bridge also runs all encrypted management steps over this ATT
client: handshake, key association, bind pages, delete, rename and mixed query/write sequences.
The get-random frame uses Write Command, matching the existing working management path; its
16-byte IV encrypts subsequent frames with AES-CTR. Commands are chunked at ATT MTU minus three,
and acknowledgements must match the key ID and IV prefix. Periodic status records are filtered
unless the command itself is a status poll. Transactions with accepted response codes stop on
rejection. Failure after any command write is classified as a command failure, even if a later
query or disconnect fails, so the integration cannot treat it as a safe pre-command retry.
There is no BlueZ fallback in this multi-address management path. The older single-address
transport remains separate.

This implementation has scripted ATT/HCI tests; simultaneous central/peripheral behaviour on
the user's controller is not yet verified. HCI connection parameter layout follows
[BlueZ's public HCI definitions](https://github.com/bluez/bluez/blob/master/lib/bluetooth/hci.h).

### Several addresses from one controller

"Separate addresses" does not have to mean separate adapters. Proven on hardware with one
Bluetooth 5.1 controller (4 advertising sets, extended advertising on all three PHYs):

- BlueZ cannot do it. None of the kernel's advertising commands — `Add Advertising` (0x003E) or
  `Add Extended Advertising Parameters` (0x0054) — carries an address field, so every
  advertising instance goes out as the controller's identity address.
- The controller can. On the HCI user channel, `LE Set Advertising Set Random Address` (0x2035)
  gives each advertising set its own address, and `LE Advertising Set Terminated` (subevent
  `0x12`) names the set a connection arrived on. That subevent is masked off by the usual
  `LE Set Event Mask` values: it needs bit 17.
- The controller's own public address cannot be assigned to a set. Keep it by giving that one set
  `Own_Address_Type = 0x00`; the others carry static random addresses, whose top two bits must
  be `11` (first octet `C0` or higher).
- Taking the user channel detaches the kernel's stack, so ACL, L2CAP and ATT have to be served in
  userspace. ATT is the only hard part and already exists: `FastAttProtocol` is a transport-free
  `handle(pdu) -> bytes | None`. L2CAP needs nothing but B-frame framing on the fixed ATT CID
  `0x0004`, and there is no LE pairing anywhere in this path — the remote encrypts at the
  application layer instead.

`tools/spike_multi_address.py` proves the advertising half; `tools/hci_multi_bridge.py` serves a
complete press this way, handshake through decrypted command and acknowledgement. The add-on
does it in `hci_multi.py` behind its `addresses` option.

Confirmed on hardware with two tiles on one controller, both reaching Home Assistant:

```
037200921fe01b888a  slot 3  target 8A:88:1B:E0:1F:92   (the controller's own public address)
047200921fe01671da  slot 4  target DA:71:16:E0:1F:92   (an extended advertising set)
```

One caveat surfaced there. Bytes 2-3 of an encrypted frame are the first two bytes of the IV it
was encrypted with, so they name the session. The remote sometimes sends a frame belonging to
another session on an open connection; decrypting it with the current IV yields noise, which
used to be published as an `UNKNOWN` button event. The add-on now drops a frame whose nonce does
not match the session's IV.

## Mixed profiles

| Combination | Status |
| --- | --- |
| IR or HID key type inside a native screen | closed: the native sender ignores key type and queues BLE regardless |
| Native or HID key type inside an IR screen | closed: the IR loader `20004070` rejects types 0 and 6 with `ff` |
| IR screen (`devType 5`) + native transport | closed on hardware: accepted `01`, then stored and drawn as `0x72` |
| HID screen (`devType 0xF2`) + native transport | closed on hardware: refused `02` |
| HID screen + named IR keys (record type `2`) | **untested**: the branch exists — `2003455c` dispatches type 2 to the IR sender `200046dc` |

Only the last row is open. Testing it means rewriting an installed HID profile's key page, which
costs that profile's current key set.

## HID remotes

The remote becomes a BLE-HID keyboard bonded to a host and sends standard HID reports straight to
it; nothing passes through the app or a hub. To capture presses, the host must be a machine you
control.

| Type | devType | controlType | keyType |
| --- | --- | --- | --- |
| AppleTV | `0xF0` | 4 | 6 |
| FireTV | `0xF1` | 4 | 6 |
| UniversalBLE | `0xF2` | 4 | 6 |
| GoogleTV | `0xF3` | 4 | 6 |

Use UniversalBLE for a host you control: standard keyboard and consumer usages, no platform
quirks. HID keys carry only their function number in the 32-byte field, with no device command.

Create the HID profile first. `0F 62 0E 01 <profile id11>` starts pairing for the installed
profile, then the user selects WoRWS in the host's Bluetooth settings. The start response
`01` acknowledges the request. `0F 63 0E <profile id11>` reports `01` idle, `02` waiting,
`03` paired or `04` expired. V48 reports the current attempt globally and consumes the final
result when it is read. Creating a second HID profile before an earlier one is paired can
return `11`.

UniversalBLE usage map, button → `[usage_page_selector, usage]`:

```
A[8,55] B[8,53] C[8,54] D[8,57]  ON/OFF[0,105]  UP[0,9] DOWN[0,10]
LEFT[0,7] RIGHT[0,8] OK[0,11] BACK[0,12] HOME[8,56] SOUNDOFF[8,52]
VOL+[0,15] VOL-[0,16] CH+[0,15] CH-[0,16]
```

HID device ids are generated as `<base><typeDigit><unixSeconds>`, with the type digit 0/1/2/3 for
Apple/Fire/Universal/Google.

### What a HID key can actually send — V48

A press reaches ARM as IPC subtype 6, which `1c934` posts as event `0x15` carrying the key index.
The dispatcher at `bb6e` calls the HID executor `19580`, which reads the key's `keyFun`, turns it
into an internal index through `15190`, and looks that index up in a 21-entry table (flash
`0x33a4a`, RAM `0x20008e96`) of `[index][report id 2][usage16]`. Report 2 is the Consumer page,
which the report descriptor at `0x338f2` declares with usages 1..0x3FF.

| keyFun | usage | meaning |
| --- | --- | --- |
| 5, 105 | `0x30` | Power |
| 6 | `0x32` | Sleep |
| 7 / 8 | `0x44` / `0x45` | Left / Right |
| 9 / 10 | `0x42` / `0x43` | Up / Down |
| 11 | `0x41` | OK |
| 12, 2002 | `0x46` | Back |
| 13, 2104 | `0x223` | AC Home |
| 15 / 16 | `0xe9` / `0xea` | Volume up / down |
| 21, 22, 2001, 2101 | `0xcd` | Play / Pause |
| 25, 2103 | `0xb4` | Rewind |
| 26, 2102 | `0xb3` | Fast forward |
| 19, 2000, 2100 | `0xe2` | Mute |
| 2105 | `0x40` | Menu |
| 2106 | `0x224` | AC Back |

`keyFun` 14, 17, 18, 20 and 2003 map to index 0 and send no action.

**Next Track (`0xb5`) and Previous Track (`0xb6`) are in the table but unreachable.** `15190` never
returns their indexes, and the only other caller of the lookup passes the fixed release index, so
no key function selects them on this firmware. The table is also read-only at runtime: its base
appears in exactly one literal in the whole image, at the read in `1957c`, and it is filled by the
startup copy from flash. So there is no route to those two entries short of changing the firmware.

For a media key that must reach a player, use a native bridge button instead: its press arrives in
Home Assistant as an event, where `media_player.media_previous_track` and anything else is
available. That path is both reachable and more capable than the HID one.

The HID profile table lives separately from the remote table: the validator keeps at most three
HID entries in a `0x12`-byte-per-entry block, and returns `0x11` when that is exceeded.

## Button function numbers (WORWSTAG)

```
A=0 B=1 C=2 D=3 ON=4 OFF=5 LEFT=6 RIGHT=7 UP=8 DOWN=9 OK=10 BACK=11
HOME=12 KATA=13 SOUNDOFF=14 VOL+=15 VOL-=16 CH+=17 CH-=18
```

`keyIndex` is the on-screen position and is reused across profiles; `keyFun` and the stored
command vary by device type. For example WoStrip ON is index 4, keyFun 5, command
`57 0F 49 01 01`; Bot uses `57 01 xx`; another light handler uses `57 0F 54 …`.

## Firmware notes

- `DSP.bin` instruction addresses are `0x20000000 + file offset`, confirmed by hundreds of
  absolute function pointers. An earlier single-base `0x135a40` mapping is wrong and makes RAM
  structures look like debug strings.
- Startup `FUN_2001e764` copies file `64c48..65073` to `183000..18342b` and `65074..6ffa3` to
  `9b000..a5f2f`; these matter for indirect calls.
- Generic Ghidra does not decode this firmware's FLIX configuration. Truncated decompilation is
  not negative proof, and the `*-linear.txt` aids in the evidence directory are not a recovered
  control-flow graph.
- Emulation of real instructions with mocked IO has repeatedly agreed with hardware on
  *behaviour* while being wrong about *response codes*: it predicted `02` for a duplicate id
  where the device returns `05`. Treat emulated code mappings as leads, not as facts.

## Where the app's logic came from

The URC React Native bundle is downloadable without authentication and is readable JavaScript,
not Hermes bytecode: `https://publish-artifact.switchbot.net/RN/Urc_v1.0.41.0_android.zip` →
`bundle.zip` → `index.android.bundle`. Sending goes through `sendCmdMsgBle` →
`NativeComModuleHelper.sendCmd`, where the native layer encrypts with the communication key and
writes to `cba20002`. Page assembly is `assembleKeysByPage`; per-device key lists come from the
handlers in `BleKeyHandlerFactory`.

Useful app hooks for re-capturing values: `Custom IR CRYPTO ENC/DEC key= iv= in= out=` for the
AES inputs and outputs, `Custom IR TAP sendDeviceData/F` for outgoing commands.
