# SwitchBot Universal Remote for Home Assistant

Use your SwitchBot Universal Remote (WoRWS) to control lights, start a robot vacuum, run scripts, or launch scenes in Home Assistant. **Remote Studio** lets you set this up by clicking buttons on a preview of the remote. You can also manage infrared and Bluetooth remotes from the same screen.

<img width="2800" height="3422" alt="Eingesetzt 16  11  2026, um 19 59 04" src="https://github.com/user-attachments/assets/b1b0f17c-04f7-4259-aac4-de6c5ecbd2ed" />

## Which kind of remote do I need?

| In Remote Studio | Use it for | What you need |
| --- | --- | --- |
| **Bridge remote** | Home Assistant lights, scenes, scripts and automations | The Bridge app, a dedicated Bluetooth dongle and MQTT |
| **IR from the catalog** or **IR saved in your account** | TVs, audio equipment and other infrared appliances | A SwitchBot account to download the codes |
| **HID remote** | A TV, streaming box or computer that accepts a Bluetooth remote or keyboard | Bluetooth pairing with the TV, box or computer |

One physical WoRWS can hold remotes of all three kinds. IR and HID send commands directly to the appliance. You can use both without a Bridge dongle or a SwitchBot Hub.

## Before you buy a dongle

For **Bridge remotes**, use **Home Assistant OS** and separate Bluetooth adapter, only for this job, it's must have. Keep your existing adapter for Home Assistant. Give the Bridge its own USB dongle.

**Buy a Linux-compatible Bluetooth 5.0 or newer dongle with BLE peripheral mode and connectable LE Extended Advertising.** Look for **LE Extended Advertising** in the adapter or chipset specs, or ask the seller to confirm it. The Bluetooth version on the box alone does not guarantee this feature. An adapter that can scan for Bluetooth devices can still lack the advertising support the Bridge needs. [Bluetooth LE features](https://www.bluetooth.com/bluetooth-le-primer/)

If you want several Bridge remotes, look for a dongle that can run several **connectable advertising sets** at the same time. One compatible dongle can serve several remotes. After installation, **Native remotes available** in Studio shows how many more you can add with your setup.

## Install

### 1. Install the integration

1. In **HACS**, open **⋮ → Custom repositories**, add `https://github.com/batareya16/SwitchbotURCHass` and select **Integration**.
2. Download **SwitchBot Universal Remote (WoRWS)** and restart Home Assistant.
3. Open **Settings → Devices & services**. Use the discovery card for your Universal Remote, or choose **Add integration** and search for **SwitchBot Universal Remote (WoRWS)**. If the Bluetooth address is blank, enter the address of the physical Universal Remote.
4. Leave the communication key fields blank and choose **Connect SwitchBot cloud**. Sign in with your SwitchBot email and password. If asked, select the home that contains the Universal Remote. The integration fetches the key and keeps the sign-in tokens for renewal. It does not store the password.
5. Open **Remote Studio** from the Home Assistant sidebar. Use an administrator account.

If you already have the remote's communication key and key ID, you can enter them and skip account sign-in. The account is needed for the IR catalog and your saved IR remotes. If your account uses Google, Apple or Amazon sign-in, the setup form needs a SwitchBot email and password login. [HACS custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)

<details>
<summary>Manual installation without HACS</summary>

Download the repository, copy its `custom_components/switchbot_urc` folder into your Home Assistant `/config/custom_components/` folder, then restart Home Assistant and continue with step 3.

</details>

### 2. Install the Bridge for Home Assistant button actions

1. Install and start the official **Mosquitto broker** app in Home Assistant. Open **Settings → Devices & services** and set up the discovered **MQTT** integration. [Home Assistant MQTT setup](https://www.home-assistant.io/integrations/mqtt/)
2. Plug in the dedicated dongle. In **Settings → Connectivity → Bluetooth → Adapters**, find its Linux adapter name, such as `hci0` or `hci1`, and disable **Home Assistant's use of that adapter**. Leave your regular Bluetooth adapter enabled and the Bridge dongle plugged in. [Finding your Bluetooth adapters](https://www.home-assistant.io/connectivity/bluetooth/#viewing-your-bluetooth-adapters-and-proxies)
3. Open **Settings → Apps → Install app → ⋮ → Repositories**. On older Home Assistant versions, look for **Add-ons → Add-on Store**. Add `https://github.com/batareya16/switchbot-urc-addon`, then install **SwitchBot URC Bridge**. [Adding a third-party app repository](https://www.home-assistant.io/common-tasks/os/#installing-a-third-party-app-repository)
4. In the Bridge's **Configuration**, set `adapter` to the dedicated dongle's Linux name from step 2.
5. Leave **Addresses (optional)** empty for automatic setup. Save, start the Bridge and enable **Start on boot**. In the Bridge log, look for a line saying it is running.

Studio picks a free address for new Bridge remotes. The Bridge remembers its addresses across restarts. Leave **Bridge options** on **Automatic** for normal use.

## Use Remote Studio

### Control Home Assistant

1. Wake up the Universal Remote. In Studio, choose **Add a remote → Bridge remote**.
2. Pick a **Type** by its icon, give the remote a name and choose **Install**.
3. For a light, select it under **Quick bind** and click **Save**. The preset assigns common light controls such as power and brightness.
4. To set up a specific button, click it on the remote preview. Choose **Assign an action** if it is empty, then open **Custom actions** and choose what Home Assistant should do. You can add several actions in order. For example, **Scene: Turn on** activates a scene and **Script: Turn on** runs a script.
5. Click **Save** at the bottom of the editor. Use **Test saved mapping** to try the action from Studio. Then open the new remote on the physical WoRWS and press the button to check that the Bridge receives it.

Use the pencil next to a remote's name on the preview to edit its name and appearance. To make a submenu, select an A–D key and choose **Turn key … into a page**. Open the new page and choose **Add row**. You can move or delete rows and choose from the remote's built-in button icons. Click **Save** to apply your edits.

### Control an infrared appliance

Choose **Add a remote → IR from the catalog** and select the device type, brand and model. Or choose **IR saved in your account** to install a remote you set up in the SwitchBot app. After installation, select it on the WoRWS and point the remote at the appliance.

### Control a Bluetooth TV or streaming box

Choose **Add a remote → HID remote**, pick the type and select **Install**. Studio opens the new remote's settings. Click **Enter pairing mode**, open the TV or box's Bluetooth settings, and select the Universal Remote when it appears. Studio reports when the remote confirms pairing. To find the pairing button later, open the remote's settings with the pencil.

Studio starts with that HID type's standard buttons. You can edit individual commands later.

### Bring in a remote you already set up

Choose **Refresh** in Studio while the Universal Remote is awake and nearby. Studio reads what's installed and imports supported remotes. For IR and HID remotes made in the SwitchBot app, sign in to the account where the original remote was saved so Studio can look up its buttons.

## If something doesn't work

| What you see | What to check |
| --- | --- |
| **Remote Studio** is missing | Restart Home Assistant after installing the integration, then open it with an administrator account. |
| The Bridge reports **no extended advertising support** | Confirm `adapter` points to the spare dongle. If it does, that controller cannot run the Bridge. |
| **Bridge remote** is unavailable | Check that Mosquitto, the MQTT integration and the Bridge app are running. Reopen **Add a remote** to refresh availability. |
| **Test saved mapping** works, but the physical button does nothing | Open the matching remote on the WoRWS, move closer to the Bridge and check that Home Assistant has released the dedicated dongle for the Bridge. |
| Studio can't read or write the Universal Remote | Wake it, bring it closer and close the SwitchBot app if it is connected to the remote. If Studio reports an invalid communication key, open **SwitchBot account → Fetch a fresh key**. |
| The IR catalog or saved remotes are missing | Sign in under the integration's **Configure → SwitchBot cloud account**. The saved list only appears if the account has saved IR remotes. |

This is a community project for the SwitchBot Universal Remote. Firmware updates can affect compatibility. [Report an issue](https://github.com/batareya16/SwitchbotURCHass/issues) · [Protocol and hardware notes](PROTOCOL.md) · [License](LICENSE)
