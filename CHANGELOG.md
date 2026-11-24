# Changelog

## 0.53.27

- DIY IR remotes ("Others", the type the SwitchBot app uses for a remote of learned keys only, for example one made on a Hub) can now be installed from your account. The install stopped with "IR key map must not be empty", because Studio had no layout for this type. It now lays them out as the app does: the first three learned keys on A, B and C, the rest (up to 15) on a page behind D, each with its own learned code.
- New blank IR type **Other (DIY)** under **Add a remote → Empty remote**: a remote with no stock keys at all, so A–D carry no menu icons of their own. Give its keys commands and icons, add pages or a number pad, the same as on any generic IR remote.
- Fix the menu rows of a remote from your account on Studio's picture of the remote: their icons were translated a second time as if they were the account's key numbers, so Forward showed as "8", and every row was named "Function N". A row now shows its own icon and the caption the remote writes for it: the icon's name (Rewind, Forward, Play…), or the key's own name for a learned key without an icon.
- **Add a remote → From your account**: the **Type default** picture now follows the remote you pick (it kept showing the first one in the list), and a remote of learned keys shows the picture of its type (a learned soundbar shows the audio picture) instead of none.
- Everything that waits on the remote, the account or Home Assistant now shows the same loading panel: a spinner with its message in a padded, rounded box (reading settings or scenes, loading remotes, the catalog or remote options, talking to the account, running a diagnostic). Busy buttons (Save, Install, Check availability) show a small spinner next to their text.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.26

- **Re-read my remotes** now also finds the IR remotes of your SwitchBot account that are not on this Universal Remote yet, such as a remote made on a Hub. They are listed under **IR saved in your account** and are installed the same way, from the codes in your account. Before, only remotes already added to the Universal Remote in the app were read. Remotes deleted in the app are left out.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.25

- Fix the number pad on Studio's picture of the remote: its keys were drawn huge and the screen scrolled sideways, because a key without a command picked up the panel's style for empty notices. The pad is now drawn small enough to show the whole grid and the four keys under it at once.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.24

- Key A of an audio remote can no longer be given a command: on the remote it opens the number pad when it has one and otherwise shows "No list under this shortcut", so a command there was never sent. Studio offers only **Turn key A into a number pad** on it, like D, which only opens a page. On every key that only opens a page (audio A and D, light D, fan C and D, air conditioner A–D) Studio no longer offers **Give this key a command**, and a command left there from an earlier version is flagged in the key's editor.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.23

- Fix a new command on an IR remote's A–D key starting on the key's menu icon (123 on A, and similar on B–D): giving an empty A key a command kept the 123 picture, and the remote then showed "No list under this shortcut" instead of sending the code. A new key now starts on no icon, a key that already carries a menu icon says so in its editor, and such a key is not saved until it gets another icon. The same applies to a Native A–D key whose action is a menu function (for example Mode).
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.22

- A key that does what another button does now says so. A key with no actions of its own runs the Quick bind of its action: a menu row whose action is OFF turns the light off like the OFF button. Studio now marks such a key "same as OFF" on the remote picture, and its **Quick bind** tab explains that it copies the OFF button and how to change that (**Custom actions**, or **Disabled** to make it do nothing). The remote itself always sends the key's own command; the icon only changes the picture.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.21

- The icon picker sorts the remote's icons by what they do: **Icons** (the picture only), **Menu icons** (on Main A–D they make the key open a list) and **123** (on Main A–D it opens the number pad). Each place offers only the icons that work there, with a note on what an icon does in it. In a list every icon is only the picture and the row always sends its command, so lists offer all of them; on an HID remote the key always sends its command too.
- The icon that used to be called "More Buttons" (39) is now **123 (number pad)**: it is the "123" picture, and the only icon that opens the number pad.
- A Native command key on Main A–D can no longer take a menu icon: the remote reads it as a menu shortcut and shows "No list under this shortcut" instead of sending the action. IR remotes already had this rule.
- An HID page with a single row now says to add a second one: with one row the remote may send the key's own command instead of opening the page.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.20

- New **number pad** for IR remotes, the screen the remote's "123" key opens. Select A (or, on most IR types, any of A–D) and choose **Turn key A into a number pad**. Studio shows the pad as the remote draws it: 1–9 and 0 in a phone grid with four keys under them (3-digit input, 10, 11, 12). Select a key on the pad and give it an IR code, the same way as any other key; a key without a code is drawn dim, as the remote does. The pad's keys are written with the ids the remote's pad looks for (40–49 for the digits, 203 and 200–202 under them), and the key that opens it with 39.
- The digit pages of TV, IPTV, set-top box, DVD and audio remotes from the catalog or your account now open as this number pad in Studio, not as a list.
- A page is only offered where the remote opens one. On TV, IPTV, set-top box and audio remotes the page under A is always the number pad, so it cannot be a list; on light, fan and air-conditioner remotes only the keys that open a page on the remote can get one (light D, fan C and D, air conditioner A–D, audio D).
- Fix a list page under A on DVD, projector, camera and other generic IR remotes opening the number pad on the remote: Studio linked it with the "123" function. A list is now linked with a menu function that opens a list.
- A key outside the number pad can no longer carry one of the pad's icons (0–9, 10, 11, 12, 3-digit input) while the remote has a number pad, since the pad would send that key's command.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.19

- Studio no longer sends the remote a page without keys, by any path: Studio's editors, **Write again**, installs and the `send_command` action. The remote writes such a page over whichever tile sits at that position in its list. After a reorder that is another remote, which then disappears from the screen while every tile opens the one before it. Such a write is now refused before anything is sent, with "Add at least one key to the page". The one page without keys the remote needs, the start of a new IR remote's install, still goes through.
- An IR key's code can now be pasted in other formats: a Pronto code, a list of pulse and pause lengths in µs as Home Assistant and ESPHome write them (`+9000 -4500 +560 …`), or a base64 code that starts with `Z6V` (a header `67 A5`, a table of lengths and one table index per half byte). Studio turns it into the remote's own code when it is pasted, shows it in the field, and says what it was converted from. The remote's code is 16 µs ticks after a fixed header, ending with a pause and a byte sum; a code that stops on a pulse gets a 96 ms pause.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.18

- New **Repair list order** in **Diagnostics**. When a tile on the remote opens the remote above it, the remote's list has a gap or a repeated slot. This sends the order the list already has and names every row to the remote by its full id, so the remote sets the place of every tile once. The tiles themselves are not touched, and the table is read back afterwards.
- **Apply order** now also names every row to the remote by its full id. Before, the Bluetooth, HID and text tiles were found by the first six bytes of their address, and when several shared one (Bridge profiles on one bridge) the remote renumbered only the first, which left a gap and a repeat in its list. Remotes that share an address can now be ordered.
- An IR remote with no key on its Main page is not saved again (a page without keys is not kept by the remote, which then opens the screen it showed before). The panel says "An IR remote needs at least one key on Main" next to **Save** instead of leaving it grey. This undoes the change of 0.53.16.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.17

- **No icon** is now a proper state of an IR or HID key. A key on no icon shows an empty picture and the words "No icon" in its **Button icon** choice, the **No icon** button is pressed, and both icon codes the firmware uses for it are named so in the list. On Studio's picture of the remote the key is drawn without a picture, on the menu rows and on A–D. A new IR key starts on no icon, and **Reset to default** returns to it.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.16

- Fix **Save** staying disabled after **Clear this key** removed the last key of an IR remote's Main page. An IR remote with no keys is a normal state (an empty remote is installed that way), so it can now be saved; Native and HID remotes still need a command on Main.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.15

- The slot saved with each remote now follows the remote's table, not only what Studio shows. Whenever Studio reads the table (an install, **Apply order**, **Refresh**) or saves a remote, each saved remote takes the slot the table names for it, so a restart of Home Assistant no longer brings back stale slots and two remotes sharing one. A remote is only corrected when the table names its address once and no other saved remote has the same address.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.14

- Fix a newly added remote being drawn as another remote when you drag it on the remote's screen. The slot saved with a remote goes stale when the remote's table changes under it, so two tiles could share a slot, and the panel then showed one of them twice. A tile's slot now follows the last read of the remote's table, and two tiles can no longer claim one slot; a tile whose slot is out of date cannot be dragged until the table is read again (**Refresh**).
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.13

- The A–D keys of light, fan, audio and air conditioner IR remotes no longer disappear after Studio writes the layout. These remotes draw a fixed picture on A–D and show a key only when it carries its own function id, so Studio now writes that id for each key and for the links to pages A–D.
- On those types Studio no longer offers an icon for the A–D keys, and the key's editor says why. A key that only opens a page there (D on all of them, C on a fan, all four on an air conditioner) cannot be given a command, and the layout is refused with a message that names the key.
- An IR key on Main A–D that sends a command is not offered the icons the remote treats as menu shortcuts: with one of those, pressing the key showed "No list under this shortcut" instead of sending the code.
- The IR device type is chosen from cards with the picture of each type and a mark showing whether its A–D keys take your icon (**Custom A–D icons**) or draw a fixed picture (**Fixed A–D icons**), with an explanation under the cards. The type of a remote cannot be changed afterwards.
- Studio's picture of the remote shows the icon you chose for a key, not the stock icon of the type.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.12

- A Native remote's A–D key on the Main page can now show an icon with no action (**Icon only, no command**), as an IR remote's can. It is written like a key that opens a page, without a page behind it.
- When the chosen icon of an icon-only key is one the remote treats as a menu shortcut, the editor warns that pressing the key shows "No list under this shortcut".
- Where a picture alone is not possible (HID remotes and the rows of a menu), the editor now says that the key needs a command first.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.11

- The **Button icon** choice of IR and HID keys has a **No icon** button, and the empty picture is named "No icon" in the list instead of "No caption".
- An A–D key on the Main page of an IR remote can now show an icon with no command behind it (**Icon only, no command**), so you no longer have to give the key a command first. It is written to the remote as a shown softkey, the same record the keys that open a page use.
- The picture of the remote in Studio shows the icon you chose for an A–D key.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.10

- Keys of an IR remote that send an IR code you pasted or learned (including a remote you made empty) now have a **Button icon** choice, as HID remotes do. The icon is the picture the remote shows for the key; with an icon chosen, the remote also shows that icon's own caption instead of the key's name. Keys copied from the app's profile keep what they had.
- The README now leads with finding the integration in HACS search, and keeps adding a custom repository as a fallback.
- The Bridge add-on is unchanged in this release (0.53.6 is the latest).

## 0.53.9

- Studio now draws the remote's tiles in the order the remote lists them, from the highest slot down, in the picture of the remote and in the Remote selector. Dragging tiles and **Apply order** follow the same order: the order shown from top to bottom is the order the remote ends up with.
- The Bridge add-on is unchanged in this release.

## 0.53.8

- Fix the drag grips (⠿) of the tile order never appearing in Studio: the panel looked for a tile's slot in a field the server does not send. Tiles on the remote's screen can now be dragged, as 0.53.6 described.
- The grip is narrow now, so the tile's name follows it right away, and the **New order** bar with **Apply order** and **Reset** sits above the remote's picture in one compact row instead of inside its screen.
- Fix the picture of the remote not following the remote's own order after Refresh. Refresh now gives every saved remote the slot its row has on the device and lists them in that order, and Studio draws them in the slot order whatever order they were saved in.
- The Bridge add-on is unchanged in this release.

## 0.53.7

- Recreating an installed IR or HID remote (rewriting its edited key pages) no longer checks glyph files on disk on the Home Assistant event loop: the compile step now runs in the executor. Adding an HID remote and importing an HID layout from the account did the same check on the loop and now use the executor too.
- Removed a duplicate definition of the recreate function and a few unused imports.
- The Bridge add-on is unchanged in this release.

## 0.53.6

- Reorder the tiles by dragging them on the remote's own screen in Studio: drag a tile by its grip (⠿) and press **Apply** in the **New order** bar (or **Reset**). Apply reads the remote's table, asks for confirmation and sends the order as a whole; rows Studio does not know keep their place. The ▲/▼ buttons and the drag handles in the "Installed on the remote" table are gone. Dragging did not work before: moving a row in the list made the browser stop sending the pointer's events to the grip, so the release was never seen.
- **Add a remote** now has one **IR remote** tab with three ways inside it: **From the catalog**, **From your account** and the new **Empty remote**. An empty IR remote of the type you choose (TV, air conditioner, light, fan, audio, IPTV, set-top box, DVD, projector, air purifier, water heater, robot vacuum, camera) is installed on the remote with its main page and no codes; give its buttons IR codes afterwards in the button editor. It counts towards the ten IR remotes and is not saved to the SwitchBot account.
- Fix installed IR remotes that were made of learned keys (an account remote of a custom type, such as an audio soundbar, comes with `no_data` instead of a code bank and all its keys in `keyDetail`). Refresh failed on them with "Only base64 data is allowed". They are now laid out from their key list: free-named keys go to page D (at most 15), learned copies of default keys go to their own page, and an empty key map is accepted by every layout.
- Studio now reads the real icon and screen mode of HID and IR remotes from the remote when you press Refresh. A remote Studio found on the device used to show a placeholder icon (the TV icon), which is why "Original" could show a picture the remote did not have.
- Fix a main-page key that was removed from a layout still showing the stock profile's picture on the remote's face (key C of a light strip showed the warm-white ring although the remote does not draw it).
- Fix the captions of submenu rows: the remote captions a row from the picture it carries, and Studio used the name of the row's command, so rows showed "Color 1…" where the remote shows "Color 7", "Color Bulb" and so on.
- Remotes the SwitchBot app set up (Studio holds no pages it wrote) now say that Studio cannot read their pages back, so the pages shown are the standard ones for the type.

## 0.53.5

- Every IR remote type is now laid out the way the official app lays it out, not only TVs. The remote finds a key by the firmware's function id next to a screen position, and each type has its own main-page positions, sub-pages behind the A-D soft keys and Power handling. Covered: air conditioner, air purifier, IPTV, set-top box, DVD, fan, projector, light, audio, water heater, robot vacuum and camera. DIY remotes are not covered.
- Fix the type of IR remotes installed from the catalog. The catalog numbers its types like the SwitchBot hub (light is 3), while the remote and the app use their own ids (light is 14). The catalog number was written to the remote as it was, so anything except TVs and air conditioners was installed under the wrong type. It is now converted, and the picture shown for "Type default" in the Add dialog follows the same conversion.
- Fix the soft keys A-D of an IR TV carrying zero bytes where the app writes the key's own function id.
- Fix learned keys of an account remote being named by a wrong field (the app calls it `keyName`), and the type names used when the cloud sends a type as a word.
- An air conditioner can be installed without per-key code references in its key map; it is built from its code bank and fast-config data.
- Bridge add-on 0.53.5 (update it as well): it now answers the remote's connection-parameter requests. Without the answer the remote stopped responding during an IR install, showed "sync error" and the link dropped with `central disconnected: 0x08`. The add-on log also shows what the remote sends besides ATT data and how long each install step took.
- An IR install announces one remote in its sync boundary, as the official app does, instead of the size of the device table.

## 0.53.4

- Fix an IR remote install ending in "sync error" on the remote's screen. The sync boundary of an install carries the number of remotes sent in this synchronisation, and Studio announced the size of the device table instead, so the remote waited for remotes that never came. It now announces one remote, as the official app does for a single new remote.
- Bridge add-on 0.53.4 (update it as well): the link to the remote now tolerates 20 seconds of silence instead of 4, so an install is no longer cut off with `central disconnected: 0x08` while the remote is busy, and the add-on log shows how long the remote took to answer each install step.

## 0.53.3

- Fix the buttons of an IR TV installed from Studio doing nothing. Studio laid the key pages out its own way, with the SwitchBot cloud's key ids and keys in cloud order, while the remote looks keys up by the firmware's function ids and expects each main-page key on its own position. A TV now gets the layout the official app writes: Power on both ON and OFF, volume, channel, arrows, OK, back and menu on their own positions, and the digits, playback, inputs and extra keys on the sub-pages behind the A-D soft keys (a soft key without keys is switched off). The other IR types (air conditioner, fan, light, set-top box and so on) are still laid out the old way.
- The Bridge add-on is unchanged in this release.

## 0.53.2

- IR remotes from the SwitchBot account are now installed as new remotes under a new ID, the same way catalog remotes always were. Installing one used to write it under its account ID, where what an interrupted earlier upload left behind could keep the new copy from working. The **Replace an existing copy of the same remote** option is gone from the Add dialog; delete a remote you no longer want from its row. When the IR slots are full, Studio now says to delete one first.
- The **Type default** tile in the Add dialog shows the picture of the chosen IR remote type for catalog and account remotes too, instead of an arrow.
- The brand search in the IR catalog keeps its text and its filtered list when you choose a brand or a model.
- Bridge add-on 0.53.2: a refused connection attempt to the remote is routine, so it is logged at info level and retried up to six times before a failure is reported; large uploads are no longer paused 50 ms after every chunk, and the log shows how long they took and the ATT MTU.

## 0.53.1

- Reorder the tiles in the Universal Remote's own list: under **Installed on the remote**, move rows with ▲ and ▼ and choose **Apply order**. Studio sends the remote's `sortDevice` command (`0F 62 0A`) with the whole table, checks first that the remote still holds exactly the table you saw, refuses a list that is not a clean permutation or whose rows share one Bluetooth address, reads the table back afterwards and moves its saved records to the new slots. The rows now also show the name Studio knows them by. Rows can also be dragged by their handle (⠿), with a mouse or by touch.
- Fix choosing an icon for an IR remote that was imported from the SwitchBot account. Studio rewrote the pages it had rebuilt from the account instead of the ones the app had put on the remote, which could stop the remote from sending and lose its on-screen icons. Studio now refuses to rewrite such a remote and says how to change its icon (install it again with **Replace an existing copy**).
- Fix **Original** (formerly **Type default**) on HID and IR remotes: it now gives back the icon the remote had before Studio first changed it instead of writing icon 0.
- The **Type default** / **Original** tile now shows the picture it gives back (the device type's own picture, or the picture of the icon the remote had before Studio changed it) instead of a placeholder arrow, in the appearance editor and in the Add dialog.
- Fix Save staying disabled after switching from a custom icon back to the default: the chosen icon is compared with the icon byte the remote carries, not with a name.
- The Bridge add-on is unchanged in this release.

## 0.53.0

- Choose an icon for every kind of remote in Remote Studio: native, text, HID and IR remotes now offer the firmware's own pictures (washing machine, bathtub, fridge and the rest) and **Type default** to give the picture back to the device type. A nonzero icon replaces the type's picture on the remote's list. Confirmed on a real Universal Remote for native, text, HID and IR remotes.
- Two more firmware icons, **Roller blind** and **Garage** (bytes `13` and `14`): the app has no names for them, the remote draws them.
- Live captions on the text remote: write a Home Assistant template in a button's caption, such as `Battery {{ states('sensor.vacuum_battery') }}%`, and the remote's screen follows it, also while that screen is open. A caption is written only when its text really changed and never sooner than the interval you set (default 60 seconds, 0 to 3600; there is no lower limit, how often is up to you), because each write pauses the bridge for a few seconds and rewrites the remote's flash. A text that is too long is cut to fit, a broken template is refused when you save it, and an unreachable remote is retried with growing pauses.
- Writing an icon to an HID or IR remote resends its saved pages with only that byte changed, after checking that the slot, type and id still match.
- Pick the icon while adding a remote too: Bridge, IR (catalog and account), HID and text remotes. New HID remotes now start with **Type default** instead of the lamp icon.
- Delete any row of **Installed on the remote**, also one Studio has no record of (a remote made by another tool, an unsupported type, a leftover from a test). Studio checks that the remote still holds exactly that row before it sends the delete.
- The text remote keeps its icon when its captions are edited.
- `create_remote` and `bind_native` list all 20 icons.
- The Bridge add-on is unchanged in this release.

## 0.52.2

- Fix saving an IR command (and its custom icon) in a HID remote: the remote answers the first upload step with `10 00`, which Studio wrongly treated as a rejection. Storage is still checked before uploading.
- Fix "The text remote is no longer on the device" when editing a text remote after another remote was deleted: the remote is now found by its id, not by a slot number that can shift.
- Show **Text remotes available** next to Scenes available (one per Universal Remote).
- Make error and status notices in Remote Studio opaque and readable while they float over the page.
- Text remote is no longer labelled experimental in Remote Studio and the README; the README now describes scenes and the text remote.
- Align integration, Studio frontend, and Bridge add-on versions at 0.52.2.

## 0.52.1

- Edit a text remote's name and four captions in the appearance editor (pencil on its row). It shows the firmware's own list picture instead of a lamp, and no longer offers an icon that cannot be written.
- Add a scene from **Add a remote → Scene** like any other remote: choose its name, icon and background, then press Install. The extra Scenes button under the loading state is gone.
- Align integration, Studio frontend, and Bridge add-on versions at 0.52.1.

## 0.52.0

- Add a **Text remote** (Matter) in Remote Studio: four captioned buttons A–D written to the Universal Remote, with Home Assistant actions for each button. Presses arrive from the remote's Bluetooth advertisements, so a Bluetooth adapter or proxy must be in range. One text remote per Universal Remote.
- Make the remote's preview screen behave like the real display: the list is clipped below the glass curve, fades at its edges, and scrolls the selected remote into view.
- Keep the SwitchBot account, Installed on the remote and Diagnostics panels visible while a scene is open and remember which are expanded.
- Give the scene and caption editors the same field, icon and card styling as the rest of Studio.
- Align integration, Studio frontend, and Bridge add-on versions at 0.52.0.

## 0.51.4

- Show scenes alongside all other remotes in Remote Studio and load them through the shared inventory.
- Keep scene action drafts when switching remotes and update the shared list after saving or deleting a scene.
- Show Scenes available after the HID remote counter.
- Keep operation results and errors in consistent Studio feedback areas.

## 0.51.3

- Edit scenes on the remote preview and assign Home Assistant action sequences.
- Choose firmware button pictograms for IR commands inside HID remotes.
- Preserve scene drafts across Refresh and fix saving IR commands with an inherited zero HID function.
- Add physical remote settings to Remote Studio and integration options, including touch wheel scrolling, brightness, wake behavior, button sounds, screen timeout, temperature units, and language.
- Remove the previous-layout backup and restore feature.
- Simplify the Quick bind explanation for the selected button.
- Align integration, Studio frontend, and Bridge add-on versions at 0.51.3.

## 0.51.2

- Add and manage scenes from **Add a remote → Scene** or the **Scenes** button in Remote Studio. Assign a Home Assistant scene or script and edit the name, icon, and color shown on the Universal Remote.
- Refresh the Studio frontend version so the scene controls load after updating and restarting Home Assistant.
- Run CI against **SwitchBot URC Bridge 0.32.5**, which assembles fragmented scene-list responses. The previous CI pin used 0.32.4 and failed the long scene-list test. Use Bridge 0.32.5 for complete scene-list reads.

## 0.51.0

Changes since 0.50.4.

Remote Studio is the interface for managing SwitchBot Universal Remote profiles and assigning Home Assistant actions to Bridge remotes. IR and HID profiles send commands directly to the appliance or paired host. Only Bridge button actions require the separate SwitchBot URC Bridge add-on, a dedicated Bluetooth controller, and MQTT.

### Remote Studio

- **Bridge remote** is now the name in the Add a remote menu, capacity counter, and setup guide. The guide links directly to the SwitchBot URC Bridge add-on and explains where to install it in Home Assistant OS.
- Refresh lists installed IR remotes even when their button profiles are unavailable from SwitchBot Cloud. This includes the remote in slot 0. Studio enables button editing once it can load the matching profile.
- IR previews use firmware pictograms for A–D and submenu rows. Reconstructed cloud layouts use the stock profile's icons where the mapping is known. Studio uses the saved button records for layouts it has written.
- KATA is reserved for the Universal Remote across Bridge, IR, and HID profiles. Studio leaves the key visible on the illustration and excludes it from layout editing and Home Assistant button mappings.
- Removing or reordering a submenu row clears the old hardware position when Save writes the layout. Native menu icon choices are limited to the supported submenu icons.

### Bridge and Bluetooth

- Pair this release with **SwitchBot URC Bridge 0.32.4** when using Bridge remotes. The physical remote sends Bridge button presses as plaintext BLE commands. The Bridge device key field has been removed. Home Assistant still uses the separate WoRWS communication key for encrypted management commands, including layout writes. [Bridge add-on repository](https://github.com/batareya16/switchbot-urc-addon)
- The integration checks the device table in the same Bridge transaction after writing a layout when supported. A follow-up read is available if the response does not include the table.
- Studio shares a lock for layout writes, deletes, and recreates so those operations cannot shift slots between a table read and the corresponding write.

### HACS review

- Linux Bluetooth adapter discovery runs in the Home Assistant executor. MQTT callbacks use the cached adapter addresses. An address-only report for an unknown adapter schedules a background refresh.
- Layout validation and compilation run in the executor when saving a physical layout. The IR options flow also checks catalog availability in the executor.
- Remote Studio logs a failed identity repair and continues opening.
- CI runs the Python suite against Bridge 0.32.4 and runs the JavaScript tests for Remote Studio.
