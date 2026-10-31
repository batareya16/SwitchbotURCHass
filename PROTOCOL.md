# SwitchBot Universal Remote (WoRWS) — protocol reference

Everything here is either read out of the firmware or measured on a live remote. Claims that
only came from emulation or from a single unverified observation are marked as such. Where an
earlier conclusion was later disproved, the correction is stated rather than quietly dropped.

Companion documents:

- `README.md` — the Home Assistant integration.
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

Read-only `0F 63 xx` queries are sent **unencrypted** as `57 00 00 00 0F 63 <sub>` and answered
unencrypted, so they work without a handshake. A successful query therefore proves nothing about
the encrypted path.

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
| `0F 62 0A …` | full order table — **not** registration, see below |
| `0F 62 0E 01 <hostMac11>` | HID-pair the remote to a host |
| `0F 63 07` | list installed devices |
| `0F 63 06` | free storage |
| `0F 63 04` | list scenes |
| `0F 41 02 …` | push AC state to the screen |

`0F 62 0A` sends a complete order table `[count] + count × [remoteIndex][devType][idKind][id11]`.
It may answer `01` while changing the ordering or visibility of existing remotes, and it plays no
part in a normal create. Do not send a one-entry table.

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

Key index is bounded by `cmp r6,#0x64` in `11d9c`: up to 100 keys per native profile.

The command a native key sends is plain target-device traffic such as `57 0F 49 01 01`, not the
`57 95 …` phone-control envelope, and no session handshake precedes it. A target must answer the
write with a notify whose first byte is `01`, `06` or `0E`; otherwise the firmware requeues the
command up to five times (`122f4`).

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
  and so takes the key away from any other profile on that address. The integration's
  `delete_remote` re-sends `0F 20 08` afterwards for this reason.

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
complete press this way, handshake through decrypted command and acknowledgement.

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

Pairing: `0F 62 0E 01 <hostMAC 11 reversed>`. The host must accept the incoming BLE-HID bond;
macOS refuses it, Linux/BlueZ can be configured for it. A create for a HID profile returns `11`
until the pairing exists.

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
| 22, 2101 | `0xcd` | Play / Pause |
| 25, 2103 | `0xb4` | Rewind |
| 26, 2102 | `0xb3` | Fast forward |
| 2000 | `0xe2` | Mute |
| 2105 | `0x40` | Menu |
| 2106 | `0x224` | AC Back |

`keyFun` 14, 17, 18, 19, 20 and 2100 map to index 0 and send nothing.

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
