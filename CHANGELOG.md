# Changelog

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
