# Changelog

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
