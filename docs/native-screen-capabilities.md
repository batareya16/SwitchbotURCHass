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

### Screen profile, control mode, and icon byte are separate fields

The DSP model registry selects screen callbacks by device type. The native BLE model uses
`20028b28` for screen events and `200283dc` for key events; HID uses `2002e848` and `2002e33c`.
The create record separately carries `devType`, `controlType`, `controlMode`, and `icon`. The
screen-artwork lookup uses the wire `icon` to select the illustration profile. Icon zero
falls back to `devType`, with `controlMode` selecting Curtain subtypes. The renderer receives
a published DSP row whose base is one byte after the source-table row. Ignoring that
publication shift previously caused the fields to be misidentified. Transport and screen
profile are also not freely interchangeable; see the hardware results in
`firmware-worws/evidence/mixed-v48/README.md`.

### Pages are records; the profile supplies the screen behaviour

The known `0F 62 06` record writes one page at a time and carries:

```text
[remoteIndex][devType][controlType][controlMode][icon]
[deviceId:11][remoteName:64][0][pageIndex][keyCount]
repeated: [keyIndex][keyFun:16-bit BE][keyType][field:32]
```

The documented page indexes are `0..4`: main plus four subpages. The DSP key-record lookup
`2002238c` independently bounds a key index at 100. Neither fact establishes how many controls
are visible at once.

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
The table also contains two sets of image descriptors for each profile: a large illustration and
32x32/24x24 variants, with an alternate set on some rows. All 398 non-null resource references in
the [profile artwork index](native-profile-artwork-index.csv) resolve to images validated by the
resource scanner. The [variant comparison atlas](native-control-mode-variants.png) shows both large
illustrations for each of the 20 wire icon codes. Every one of those 20 profiles has different
normal and alternate large-image resource references. Many pairs look like illuminated/unlit or
other visual states, but the image appearance alone does not establish the runtime state meaning.
The separate control-mode and icon-variant selection stages are described below.

The [complete profile atlas](native-all-profile-artwork.png) previews all 50 descriptor rows with
correct RGB565/A8 colors. Two pairs share the same normal artwork, leaving 48 distinct normal
image references. The known selectors reach 47 profile IDs: 20 nonzero wire icon values and 77
`devType` fallback rows (32 distinct profile IDs), with overlap. Profiles `0x02`, `0x04`, and
`0xfe` are present in the descriptor table but have no route through either known selector.
These counts describe firmware artwork, not 50 independently writable `icon` values.

### Button glyphs use built-in firmware resources

The drawing helper `20023ac0` maps a 16-bit `keyFun` through a firmware-resident lookup table at
`0x2005d110` to a glyph/resource descriptor. The lookup scans 219 records with a `0x14`-byte
stride; it also has special handling for numeric ranges `0x641..0x6a3` and `0x6a5..0x707`. These
are 219 function records, not necessarily 219 unique drawings: records may share the same graphic
resources. The known page record has a `keyFun` field but no separate bitmap, vector, or image
upload field. The evidence supports choosing from glyphs already understood by the firmware; it
does not show a way to upload arbitrary per-button artwork.

The table entries contain a function number and two resource descriptor slots. The current drawing
helper `20023ac0` selects the first slot; its code reads the descriptor pointer at row offset `+4`
and the adjacent byte at `+8`, but does not read the second pointer at `+12`. Of 219 rows, 212 have
a non-null second slot; 172 pair a 32x32 primary with a 24x24 secondary, and 25 rows point both
slots at the same resource. This suggests multiple resource variants are stored, but the second
slot's consumer and selection rule remain unknown. Each descriptor points into the companion
`RES.bin` and contains display width/height metadata (commonly 32x32; some are 24x24 or 33x33).
Across all 424 non-null descriptor references, the resource object's data pointer is exactly 12
bytes after its start. The first four bytes decode as an LVGL image header:

```text
[cf:5][always_zero:3][reserved:2][width:11][height:11] (packed LE, 32 bits)
[payload bytes:32-bit LE][payload address:32-bit LE]
[payload starts immediately here]
```

The decoded width and height match the DSP descriptor for all 424 references. `cf` is `5` in every
indexed image; `reserved=1` and `always_zero=0` also hold across all 330 distinct objects. The
payload address points to `object + 12`, and the payload-size field ends at the next resource
object (with 4-byte alignment) for most adjacent objects. The raw header words seen so far are
`0x04008105`, `0x03006105`, `0x03206105`, and `0x04008505`; their packed dimensions account for
the earlier apparent `32 * height` field. That earlier interpretation as a row stride was
incorrect. The uniformly set reserved bit is a candidate vendor marker, but its meaning has not
been recovered.

The firmware's own pixel-size table at `0x2004a0b0` maps `cf=5` to 24 bits per pixel (it also maps
`cf=4` and `cf=6` to 16, and indexed formats `cf=7..10` to 1/2/4/8). In upstream LVGL 6.1,
numeric CF5 is named true-color-with-alpha, but this firmware's bpp table does not match that
format's usual 32-bit pixels; the target has a customized LVGL build and its own table is the
relevant evidence. The uncompressed 32x32 size at the firmware's 24 bpp would be 3072 bytes;
observed glyph payloads are 76-2220 bytes. This rules out a plain 24-bit pixel array, but does not
by itself identify the encoding. The payload codec is identified below. See the [upstream LVGL image format table](https://lvgl.io/docs/open/6.1/overview/image)
for upstream naming only, not as a decoder specification for WoRWS.

The DSP contains LVGL build strings for `lv_canvas.c`, `lv_img.c`, `lv_img_set_src`, and
`lv_canvas_set_buffer`. The native glyph drawing path resolves a `keyFun` resource, then passes it
to the common display backend. This confirms the glyphs enter the LVGL-backed rendering stack, and
the resource header matches LVGL's packed `lv_img_header_t` layout. The image-info path at
`2003e4e8` walks a linked list of decoder callbacks and stops when one reports that it handled the
source. The list includes a vendor callback at `2003e678` before the generic LVGL callback at
`2003e7ac`. The vendor callback checks the LVGL source kind, then enters FLIX-dependent logic. In the
generic callback, the direct-resource path for `cf=4/5/6` is visibly gated on a zero `reserved`
byte. All indexed glyph objects have `reserved=1`, so they do not follow that ordinary direct-
resource path; the vendor callback is a strong candidate for their handling, but its FLIX block has
not yet proven that it accepts or decodes them.

The draw dispatch at `2003e9fc` routes `cf=4/5/6` to function `0xA504C`, `cf=7..10` to `0xA5354`,
and `cf=11..14` to `0xA50EC`. These functions are inside the startup-copied code range
`0x9B000..0xA5F2F`. Its source mapping is `DSP.bin[0x65074 + (runtime_address - 0x9B000)]`, so
`0xA504C` maps to file offset `0x6F0C0`, `0xA50EC` to `0x6F160`, and `0xA5354` to `0x6F3C8`.

The `cf=5` renderer calls the bpp lookup `2003c85c`, then reaches FLIX bundles at `0xA5065` and
`0xA5071`, followed by a direct call to `0xA6BCC`. The `cf=11..14` renderer at `0xA50EC` visibly
reads a 16-bit value at `param_1+8` and writes its two bytes into a 3-byte-per-pixel output buffer
before its FLIX path. This is evidence about palette/pixel conversion in the draw backend, not yet
about how the source payload is compressed. `0xA6BCC` lies beyond this startup-copied range; its
mapping and role remain unresolved. The payload algorithm is therefore still hidden behind FLIX and
an unresolved helper at the instruction level, though the payload byte grammar has now been
recovered independently from the resource corpus.

The startup copy routine's literal pool at `0x2001e728..0x2001e760` was checked against all copy
loops: it copies data from file offset `0x64c48` to runtime `0x183000` (size `0x42c`) and code from
`0x65074` to `0x9b000` (size `0xaf30`). It contains no third copy that would map `0xA6BCC`; mapping
that runtime address with the renderer's source formula lands past the end of `DSP.bin`. Thus the
call target is in an address region not represented by this supplied DSP image (for example a
platform ROM or separately loaded code; which one is not established). This explains why another
Ghidra pass over `DSP.bin` cannot decompile that callee.

The generic image-info callback at `2003e7ac` confirms a separate decode setup for indexed formats
`cf=7..10`: it gets the format's bpp, allocates decoder state and two scratch buffers, then enters
the format-specific path. For `cf=4..6`, the generic callback only exposes the source pointers when
the reserved header field is zero. Since the indexed glyph resources have `cf=5` and reserved=1,
their vendor decoder path is still the relevant one. Its FLIX-dependent callback at `2003e678`
cannot be followed past its first FLIX bundle with the installed Ghidra language.

### Resource payload codec and rendered glyphs

The resource payload is a byte-controlled stream of three-byte pixels. Each control byte has this
meaning:

```text
count = control & 0x7f
control & 0x80: read one pixel triple and repeat it count times
otherwise:      read count consecutive pixel triples
```

Each expanded triple is **big-endian RGB565 plus 8-bit alpha**: `[color_hi, color_lo, alpha]`.
Treating it as RGB888 produced the earlier pink/cyan/yellow preview with the alpha byte displayed
as blue. RGB565/A8 yields expected white UI glyphs and the plausible device colors in the full
[profile artwork atlas](native-all-profile-artwork.png). The alpha is composited over the atlas
background. This is a decoding correction for the preview assets; it does not change bytes sent
to the remote.

Counts are literal (`N`, not `N+1`). The decoder consumes exactly the declared payload length for
all 330 distinct glyph resources. It produces exactly `width * height` pixels for 326; four produce
2 or 4 extra pixels at the end. Those are `keyFun=0x009a` primary (+4), `0x0029` secondary (+2),
`0x0031` secondary (+2), and `0x0834` secondary (+2). The extra bytes are not uniformly black, so
their exact role is not established. The extraction script clips to the dimensions in the resource
header; the device's handling of those tails has not been traced.
This corpus-wide boundary test plus recognizable rendered artwork establishes the payload grammar;
it does not establish how the firmware handles the four excess-pixel tails internally.

The [primary atlas](native-glyph-atlas-primary.png) and
[secondary atlas](native-glyph-atlas-secondary.png) render all 212 table rows with non-null
descriptors, including repeated references; each variant has 173 distinct resources. Seven table
rows have no image descriptor. The primary atlas visually identifies power, navigation, fan,
lighting, numeric, and color controls. The secondary atlas has smaller variants for many glyphs.
Regenerate either with [`decode_glyph_resources.py`](../../firmware-worws/scripts/decode_glyph_resources.py).

Remote Studio uses the primary firmware glyph directly by `button_function`/`keyFun`; it does not
infer an icon from a translated button label. Its transparent PNG assets are generated from the
same indexed `RES.bin` resources:

```sh
rtk python3 hass/tools/export_native_glyphs.py \
  --res firmware-worws/v48/RES.bin \
  --index hass/docs/native-glyph-resource-index.csv \
  --output-dir hass/custom_components/switchbot_urc/frontend/native-glyphs
```

The filenames use the four-digit `keyFun` value, for example `keyfun-014b.png`. Functions without
a primary resource remain without a glyph in the editor; Studio does not substitute a guessed icon.

A scan of all 4-byte-aligned `RES.bin` positions for a matching LVGL header, self-pointing payload
address, complete RGB token stream, and decoded size within eight pixels of declared dimensions
found 987 objects of this format. Of these, 330 are the distinct resources referenced by the
`keyFun` table and 657 are not. The unindexed set includes 151 images of 32x32, 135 of 24x24,
113 of 96x66, 113 of 96x30, 62 of 240x26, and 26 of 160x40, plus smaller groups.
[`native-all-resource-index.csv`](native-all-resource-index.csv) records their offsets and sizes;
[`scan_res_images.py`](../../firmware-worws/scripts/scan_res_images.py) reproduces the scan.

All 113 96x66 objects are immediately followed by a 96x30 object (allowing 0–3 alignment bytes).
Stacking each pair vertically yields a coherent 96x96 device illustration. The
[device illustration atlas](native-tile-atlas.png) shows those 113 composed illustrations, including lamps, fans,
curtains, switches, and appliances. The [unindexed 32x32 atlas](native-unindexed-32x32.png) also
shows device and UI symbols. These images establish that the firmware resource bank contains the
artwork.

Earlier guesses based on fixed four-byte runs, PackBits, zlib/raw-DEFLATE, gzip, LZMA, bzip2, raw
LZ4, and headerless QOI failed to explain the full corpus. The recovered stream is simpler than
those candidates: only repeated-color and literal-color blocks are needed.

A complete machine-readable index of all 219 table rows, both descriptors, resource
addresses, dimensions, and raw header values is in
[`native-glyph-resource-index.csv`](native-glyph-resource-index.csv). It contains 173 distinct
non-null primary resource addresses; that is a resource count, not a count of unique visible icons,
because separate resources may render alike and the table also has missing/duplicate rows.

The current protocol sender serializes `keyFun` as a 16-bit big-endian value, for example
`keyFun=5` becomes `00 05`. This value is not the tile icon byte. The glyph table row has an
additional packed 32-bit word at offset `+16`: its high 16 bits select a firmware `uiLabelId`, and
its low 16 bits are `3` on 212 rows and `0` on seven rows (the low-half meaning is not yet known).
`uiLabelId=211` is a no-label sentinel. Function `20023de0` resolves IDs `0..210` through a
211-entry, three-language table at `0x2005e230`, using the language selected by `20023cf8`.

This provides a direct firmware `keyFun -> uiLabel` mapping. Examples include `5 -> ON`, `6 -> OFF`,
`60 -> Temp+`, `300 -> Brighter`, `303 -> Whiter`, `321 -> White`, `322 -> Warmer`, `323 -> Cooler`,
and `331..345 -> Color 1..15`. Across 219 rows there are 214 distinct `keyFun` values; five values
are duplicate table rows. The index has labels on 182 rows (160 distinct label IDs); 37 use the
no-label sentinel. All rows, including Chinese, English, Japanese, the ID, and the low half of the
packed word, are in [`native-glyph-resource-index.csv`](native-glyph-resource-index.csv).

The extractor's `integration_catalog_name` column is a name from the integration's current action
catalog, not a firmware-derived semantic. A comparison with the firmware's English UI strings shows
many mismatches: e.g. `303` is catalogued as `COOLER` but labelled `Whiter`; `312` as `DAY` but
labelled `All`; `318` as `FLASH` but its label is `+/- is valid only in Cool/Heat mode.`; and IDs
`129..132` are catalogued `LEVEL_3`, `LEVEL_2`, `LEVEL_1`, `MUTE` while labelled `Level 4` through
`Level 1`. Other labels such as `Normal`, `Nightlight Dim`, `V. Swing 30°`, `Fully open`, and
`Close Down` are more descriptive than the current catalog names. These are confirmed text
differences, not proof that the transmitted command behavior is wrong: button captions can describe
a mode or context rather than the action. Do not rename runtime commands from labels alone; compare
the native press dispatch and device behavior separately. The decoded atlases now show the glyph
artwork, while device captures are still needed to verify which variant and label appear on each
physical screen.

The bundled Android app's `getDeviceIconCode` maps these named selections to the packet's
`icon` byte. A missing or unknown name maps to `00`. Studio previews firmware artwork for
supported IR, HID, and native screen profiles and retains their saved icon codes; the app's
list is not proof of 18 distinct V48 illustrations.
The [18 app icon previews](native-app-icon-catalog.png) were extracted from the bundled
SwitchBot 10.5 APK's `res/drawable-mdpi-v4/src_common_src_assets_urc_images_icon_32pt_*_highlight.webp`
resources. They show what the phone app draws for each choice; they are not decoded images from
the remote's screen. Their colors are unchanged from the APK.

For HID and IR, the recovered screen callbacks pass the same published-row offsets
to the artwork selector. Icon zero selects the type-specific fallback. A nonzero
icon uses the 20-entry illustration table. The fallback mappings for HID remain
`F0 -> 1D`, `F1 -> 1E`, `F2 -> 20`, and `F3 -> 1F`. Whether an installed HID or
IR tile redraws immediately after a write still requires its update path to be checked.

| App icon name | Byte | Studio name |
| --- | ---: | --- |
| light | `01` | light |
| desklamp | `02` | desklamp |
| floorlamp | `03` | floorlamp |
| ceilinglamp | `04` | ceilinglamp |
| lightstrip | `05` | strip |
| switch | `06` | switch |
| bathtub | `07` | bathtub |
| coffeemachine | `08` | coffeemachine |
| socket | `09` | socket |
| television | `0A` | tv |
| boiler | `0B` | boiler |
| heater | `0C` | heater |
| cooler | `0D` | cooler |
| washer | `0E` | washer |
| fridge | `0F` | fridge |
| cookware | `10` | cookware |
| pool | `11` | pool |
| ventilator | `12` | ventilator |
| (no app name) | `13` | blinds: roller blinds, profile `0x2d` |
| (no app name) | `14` | garage: garage, profile `0x2e` |

ARM's create parser stores the packet's `controlType`, `controlMode`, and `icon` at
model `+2`, `+3`, and `+4`. Sender `0x7848` places them in IPC bytes `+0x13`,
`+0x14`, and `+0x15`. The DSP constructor stores these at source-table row
`+0x55`, `+0x56`, and `+0x57`.

**The source-table row and the UI row have different bases.** Slot lookup `2002262c`
returns `source_row + 1`. Publication `200248a4` copies `0x898` bytes from
`source_table + 1` to UI table `0x001c9650`. Consequently the renderer's
`row+0x56` is the wire **icon**, and `row+0x55` is the wire **controlMode**.
The fourth selector argument, `row+0x57`, follows the stored icon and is a separate
runtime byte. Its complete state semantics have not been established.

For icons `1..20`, `2002363c` uses the 20-byte table at `0x20047150`.
The [icon map](native-icon-map.csv) resolves those codes to artwork. For icon zero,
the helper uses the [device-type mapping](native-default-artwork-map.csv).
For Curtain types `0x63` and `0x7b`, modes `3/4/5` select profiles `2/3/4`
on this fallback path.

The local V48 parser consumes exactly one device-type byte. Floor lamp therefore
uses the Strip layout type `0x72`, native control type zero, control mode zero,
and icon `0x03`. Its appearance does not require the extended product code.

| Wire type / mode / icon | Render arguments after publication | Resource |
| --- | --- | --- |
| `72 / 03 / 01` | `72 / 01 / 03 / 00` | Bulb, descriptor `2005a9a0` |
| `72 / 00 / 03` | `72 / 03 / 00 / 00` | Floor lamp, descriptor `2005a820` |

These results execute decoded DSP field-copy, row-lookup, publication, renderer-load,
and selector instructions. ARM parser/sender execution produced matching 124-byte IPC
messages for both Main and D. The fixtures mock storage, the already-valid model gate,
and memcpy boundaries. They supply the constructor's row index at a decoded block
and do not execute the surrounding opaque FLIX gates or a complete UI event loop.
The previous direct-selector fixture injected an unshifted row and did not prove
the wire-field mapping. The shifted-row fixture reproduces the user's observed Bulb.

The runtime byte chooses ordinary normal/alternate descriptors. Blind Tilt has additional
branches for runtime values `2` and `3`; these values are not extra wire-icon choices.
Roller Shade's variant branch remains opaque. An independently writable on/off runtime
state field has not been established.

The prior washer experiment changed mode to `0x0e` while retaining icon `1`.
This still selects Bulb artwork. That experiment therefore supplies no evidence
that an artwork change requires deleting the tile or adding transport retries.
The corrected Floor lamp write has been checked in the bounded firmware fixtures,
and still needs its first physical-device check.

## Remaining firmware work

The icon investigation is not complete. The resource table now maps `keyFun` values to rendered
firmware artwork and labels, and the wire-icon map resolves all 20 supported nonzero values to
their illustrations. The
firmware callback `20023ac0` reads the first descriptor pointer at
table-row offset `+4` and the byte at `+8`; it never loads the second pointer at `+12`. Search of the
indexed callback's code therefore confirms that the second descriptor is not selected on this
path, but its use by another consumer remains unknown. Other open questions are the vendor
decoder's FLIX branch, the four excess-pixel tails, the `0x2c` alternate-artwork branch,
complete profile/layout descriptors, and the exact firmware
treatment of a glyph selector that differs from the command function. LVGL `cf=5` is image metadata,
not the one-byte remote icon field and not evidence of an image-upload command.

The next static step for the *firmware decoder implementation* is to obtain a FRBT/HiFi3 FLIX
decoder or the separately loaded code for the `0xA6BCC` address region, then recover the bundles at
`0xA5065`, `0xA5071`, and the vendor image-info callback at `2003e678`. Ghidra's installed Xtensa
FLIX decoder truncates those paths. A controlled device capture can verify which decoded glyph and
variant are displayed for selected `keyFun` values: change one key on a disposable profile,
photograph the screen, and retain the exact page write and `0F 63 07` readback. That would verify
the display mapping, but would not prove arbitrary-image upload support.

Because `keyFun` is distinct in the record from `keyType` and the 32-byte command field, it may be
possible to change the displayed glyph without changing a native command. That independence is a
promising lead, not yet a device-verified contract: some function values may also drive profile
navigation or other UI behaviour.

The page record includes the remote name, but no documented per-page title or per-button label
field. Custom page titles have not been established.

Regenerate the resource index for this firmware pair with:

```sh
rtk python3 firmware-worws/scripts/extract_glyph_resources.py \
  --dsp firmware-worws/v48/DSP.bin \
  --res firmware-worws/v48/RES.bin \
  --output hass/docs/native-glyph-resource-index.csv
rtk python3 firmware-worws/scripts/decode_glyph_resources.py \
  --index hass/docs/native-glyph-resource-index.csv \
  --res firmware-worws/v48/RES.bin \
  --variant primary \
  --output hass/docs/native-glyph-atlas-primary.png
rtk python3 firmware-worws/scripts/decode_glyph_resources.py \
  --index hass/docs/native-glyph-resource-index.csv \
  --res firmware-worws/v48/RES.bin \
  --variant secondary \
  --output hass/docs/native-glyph-atlas-secondary.png
rtk python3 firmware-worws/scripts/scan_res_images.py \
  --index hass/docs/native-glyph-resource-index.csv \
  --dsp firmware-worws/v48/DSP.bin \
  --res firmware-worws/v48/RES.bin \
  --output-dir hass/docs
```

## Three limits Remote Studio must not conflate

| Limit | Evidence | What it means |
| --- | --- | --- |
| Five page indexes (`0..4`) | `0F 62 06` record path documented in `PROTOCOL.md` | Main and at most four encoded subpages are currently known |
| Up to 100 native key indexes | DSP record lookup `2002238c`, comparison against `0x63` | Record lookup bound; not a visible-button count |
| Four screen positions per draw pass | DSP paths `200288e4` and `2002e720` | Visible controls processed in that pass; total page/list capacity remains unknown |

The current integration's validation limits (for example 18 buttons on a native page) are software
rules, not firmware findings. They should stay labelled as product constraints until tested against
the screen/list path.

## Remote Studio implications

1. Keep the selected screen profile/control mode explicit and independent from the icon variant
   and HA action mappings.
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
- Raw `RES.bin` function dump helper: [`DumpLoadedFunctions.java`](../../firmware-worws/scripts/DumpLoadedFunctions.java).
- Resource index extractor: [`extract_glyph_resources.py`](../../firmware-worws/scripts/extract_glyph_resources.py).

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


## Full artwork recheck, 2026-11-14

The [execution report](artwork-firmware-verification.csv) contains 115 cases.
All 115 complete page records were parsed by the V48 ARM page handler and IPC sender
under Ghidra. The resulting 124-byte IPC messages were then supplied to decoded DSP
constructor-field, slot-lookup, table-publication and renderer-load blocks.

- Icons `01..14` (hexadecimal, 20 values), plus zero, were run through each of
  Native, HID and IR's actual renderer argument-load blocks. All 60 nonzero cases
  resolve to the same 20 profiles across the three transports. All 180 resource
  pointers for their 96/32/24 sizes match the actual DSP descriptor table.
- Native catalog types and the four HID/fourteen IR device defaults were also checked.
  Of 115 inputs, 114 complete the resource-selection fixture. The remaining input is
  Native Roller Shade, whose device-specific selector enters opaque FLIX at
  `20023708`. The fixture records this explicitly and does not guess its output.
- All 100 normal/alternate profile PNG files in the integration were compared against
  images freshly decoded from V48 RES. Dimensions and RGBA pixels match exactly.
- Studio now uses cached Main-page type/mode/icon fields for HID and IR artwork too.
  The previous HID fixed-type preview and IR normal/alternate interpretation ignored
  the actual wire icon. The normal picture is the catalog preview convention.
  Live runtime-state variants remain a separate question.

The fixture mocks the existing-model validator, storage and memory boundaries and
does not execute the constructor's opaque FLIX gates or a radio session. This verifies
the decoded field mapping and resources, including the different transport draw loads.
It does not claim every physical screen update or runtime variant has been observed.
