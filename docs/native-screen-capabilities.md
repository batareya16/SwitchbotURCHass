# WoRWS V48 screen and layout capabilities

This note records what the V48 firmware and the current write protocol establish about native
remote screens. It is intended to guide Remote Studio work. Firmware facts, protocol limits,
implementation limits, and unverified device behaviour are kept separate.

## Firmware image and analysis method

The analysed image is `firmware-worws/v48/DSP.bin`, SHA-256
`e9d4916fbe8c2cc5d20327be1ad730238af4f3839816b30cbd817734e6698032`. DSP RAM addresses use
base `0x20000000 + file offset`. The older saved Ghidra project at base `0x00135a40` is incorrect
for these callbacks; reports from it must not be used as firmware evidence. The callbacks below
were inspected in a temporary read-only Ghidra project imported at the correct base.

Ghidra 12.1.4 does not decode this target's Xtensa FLIX instructions. The instruction-level
branches and loops cited below are visible, but some surrounding functions decompile only
partially. A missing path in those decompilations is not proof that the firmware lacks it.

## Findings

### Screen profile and tile icon are separate

The DSP model registry selects screen callbacks by device type. The native BLE model uses
`20028b28` for screen events and `200283dc` for key events; HID uses `2002e848` and `2002e33c`.
The create record separately carries `devType`, `controlType`, and a one-byte tile `icon`. Thus,
the tile icon does not select the button-screen profile. Transport and screen profile are also
not freely interchangeable; see the hardware results in `firmware-worws/evidence/mixed-v48/README.md`.

### Pages are records; the profile supplies the screen behaviour

The known `0F 62 06` record writes one page at a time and carries:

```text
[remoteIndex][devType][controlType][controlMode][tileIcon]
[deviceId:11][remoteName:64][0][pageIndex][keyCount]
repeated: [keyIndex][keyFun:16-bit BE][keyType][field:32]
```

The documented page indexes are `0..4`: main plus four subpages. The native sender independently
bounds a key index at 100. Neither fact establishes how many controls are visible at once.

The native screen path (`200288e4`) asks the model/profile lookup (`200236b0`) for screen-key
metadata, then loops over four positions and passes each position's `keyFun` to the drawing path
(`200279bc`). The HID screen path (`2002e720`) has a similar four-position loop and its own drawing
helper (`2002dd98`). This proves four positions are processed per drawing pass. It does **not** yet
prove that four is the total page capacity; the surrounding FLIX-dependent list/scroll behaviour
has not been recovered.

The screen callback's model-specific lookup and the per-page key records together govern what is
shown. FAN's stock Main/A-D navigation is therefore a firmware profile, while the contents written
for those page indexes are records. Reusing pages A-D for different commands is supported by the
record format. Removing a link, creating a page link outside the stock profile, or changing the
navigation shell has not yet been confirmed on hardware.

The lookup at `200236b0` searches a 50-entry, `0x24`-byte descriptor table at `0x20059b40`. This is
evidence that screen layouts are selected from firmware-resident descriptors, not assembled from
an arbitrary layout description in the create packet. The 50 records should not be read as 50
user-configurable profiles: some entries may be aliases, defaults, or internal modes.

### Button glyphs use built-in firmware resources

The drawing helper `20023ac0` maps a 16-bit `keyFun` through a firmware-resident lookup table at
`0x2005d110` to a glyph/resource descriptor. The lookup scans 219 records with a `0x14`-byte
stride; it also has special handling for numeric ranges `0x641..0x6a3` and `0x6a5..0x707`. These
are 219 function records, not necessarily 219 unique drawings: records may share the same graphic
resources. The known page record has a `keyFun` field but no separate bitmap, vector, or image
upload field. The evidence supports choosing from glyphs already understood by the firmware; it
does not show a way to upload arbitrary per-button artwork.

Because `keyFun` is distinct in the record from `keyType` and the 32-byte command field, it may be
possible to change the displayed glyph without changing a native command. That independence is a
promising lead, not yet a device-verified contract: some function values may also drive profile
navigation or other UI behaviour.

The page record includes the remote name, but no documented per-page title or per-button label
field. Custom page titles have not been established.

## Three limits Remote Studio must not conflate

| Limit | Evidence | What it means |
| --- | --- | --- |
| Five page indexes (`0..4`) | `0F 62 06` record path documented in `PROTOCOL.md` | Main and at most four encoded subpages are currently known |
| Up to 100 native key indexes | ARM sender `11d9c`, compare against `0x64` | Command storage/dispatch bound; not a visible-button count |
| Four screen positions per draw pass | DSP paths `200288e4` and `2002e720` | Visible controls processed in that pass; total page/list capacity remains unknown |

The current integration's validation limits (for example 18 buttons on a native page) are software
rules, not firmware findings. They should stay labelled as product constraints until tested against
the screen/list path.

## Remote Studio implications

1. Keep the selected screen profile explicit and independent from the tile icon and HA action
   mappings.
2. Preserve all page/key records in the draft when changing profiles. Validate against that
   profile's known page indexes and Main-page navigation positions, and show conflicts before
   writing.
3. Model `keyFun` as a firmware glyph/function selector, separate in the editor from the native
   command bytes. The firmware has a 219-entry function/glyph table, but the editor should not
   expose every raw value until we label the entries and validate their behaviour. Do not promise
   arbitrary image upload or unrestricted glyph/function decoupling.
4. Represent the firmware facts (`0..4`, native key index `<100`, four positions per render pass)
   separately from current editor limits. Do not infer a four-button page maximum from the render
   loop alone.
5. Treat removing stock submenu links, custom page titles, extra page indexes, and custom artwork
   as unsupported/unknown until their device behaviour is measured.

## Safe device experiments to close the gaps

Use a disposable remote slot/profile and save a `0F 63 07` inventory plus the original page
packets before each experiment. Do not overwrite the only working remote.

| Question | Controlled change | Evidence to record |
| --- | --- | --- |
| Can a submenu link be hidden? | Remove exactly one A-D link from Main; leave its page record untouched | Screen redraw, tap behaviour, whether the page remains reachable |
| Can page contents be changed? | Replace one page's key records, keep page index and link constant | Rendered glyphs, order, tap events and command bytes |
| Can glyph be changed independently? | Change only one key's `keyFun`; keep key index/type/command fixed | Rendered glyph and resulting tap command/event |
| Are there more than four visible controls? | Put 5, then 9 controls on a supported page | Visible rows, scrolling/swiping, key indexes emitted |
| Can titles change? | Change only the 64-byte name on one page write | Tile name and subpage title before/after |
| Are indexes above 4 accepted? | On a disposable profile only, try page index 5 after confirming backup/restore path | Ack code, `0F 63 07`, screen navigation, ability to restore |

Do not treat an acknowledgement alone as proof that a page or icon was stored or rendered. Read the
device table where applicable and inspect the actual screen and button events.

## Evidence pointers

- Protocol layout and native key-index bound: [`PROTOCOL.md`](../PROTOCOL.md), sections
  “Creating a remote” and “Native targets”.
- Profile callbacks, native/HID transport behaviour, image identity, and Xtensa decoder limits:
  [`firmware-worws/evidence/mixed-v48/README.md`](../../firmware-worws/evidence/mixed-v48/README.md)
  in the adjacent firmware workspace.

To reproduce the screen callback inspection, create a temporary project with the correct DSP RAM
base, then run the existing read-only script:

```sh
rtk /opt/homebrew/Cellar/ghidra/12.1.4/libexec/support/analyzeHeadless \
  /private/tmp worws_screen_v48 \
  -import /Users/batareya16/Downloads/switchbot/firmware-worws/v48/DSP.bin \
  -processor Xtensa:LE:32:default -loader BinaryLoader -loader-baseAddr 0x20000000 \
  -noanalysis \
  -scriptPath /Users/batareya16/Downloads/switchbot/firmware-worws/scripts \
  -postScript InspectDspDispatch.java /private/tmp/worws_screen_callbacks.txt \
  20028b28 2002e848 200288e4 2002e720 200236b0 2002363c \
  200279bc 2002dd98 20023ac0
```

The output and project are temporary analysis artifacts, not canonical firmware evidence.
