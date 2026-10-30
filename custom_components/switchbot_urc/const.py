"""Constants for the SwitchBot Universal Remote (WoRWS) integration."""
from __future__ import annotations

DOMAIN = "switchbot_urc"
PLATFORMS = ["sensor"]

# WoRWS advertisements use the Bluetooth SIG service-data UUID assigned to SwitchBot.
# The official Android WoRwsParser reads byte 2 and masks its high flag bit for battery %.
SVC_WORWS_ADVERTISEMENT = "0000fd3d-0000-1000-8000-00805f9b34fb"

# Config entry keys
CONF_ADDRESS = "address"        # BLE MAC, e.g. A1:B2:C3:D4:E5:F6
CONF_KEY_ID = "key_id"          # hex string, e.g. "95"
CONF_KEY = "key"                # 32 hex chars (16 bytes AES key)

# SwitchBot BLE GATT
SVC_SWITCHBOT = "cba20d00-224d-11e6-9fb8-0002a5d5c51b"
CHAR_WRITE = "cba20002-224d-11e6-9fb8-0002a5d5c51b"   # commands
CHAR_NOTIFY = "cba20003-224d-11e6-9fb8-0002a5d5c51b"  # encrypted responses/events

# Standard HID-over-GATT (appears once the remote is HID-configured against a host). If the
# remote reports presses as GATT notifications, they arrive here (report char 0x2A4D).
UUID_HID_SERVICE = "00001812-0000-1000-8000-00805f9b34fb"
UUID_HID_REPORT = "00002a4d-0000-1000-8000-00805f9b34fb"

# Command envelope: 57 <keyId> <nonce[0:2]> <AES-CTR ciphertext>
CMD_MAGIC = 0x57

# Device response codes (first byte of a decrypted notify to a command).
RESP_OK = 0x01
RESP_VALUE_ERR = 0x02
RESP_FORMAT_ERR = 0x04
RESP_HID_NO_PAIR = 0x11

# HASS event fired for every decrypted notification from the remote.
EVENT_NOTIFY = f"{DOMAIN}_notify"
# HASS event fired when we recognise a physical button press (HID report, notify, or add-on MQTT).
EVENT_BUTTON = f"{DOMAIN}_button"
# Fired after each stage of native provisioning: set_key, associate, bind_main, bind_colors.
EVENT_NATIVE_BIND = f"{DOMAIN}_native_bind"

# MQTT topic the switchbot_urc_bridge add-on publishes button presses to. Subscribing here lets
# the integration re-fire them as EVENT_BUTTON, so automations use one event for all sources.
MQTT_BUTTON_TOPIC = "switchbot_urc/button"
MQTT_BRIDGE_CONTROL_TOPIC = "switchbot_urc/bridge/control"
MQTT_BRIDGE_STATUS_TOPIC = "switchbot_urc/bridge/status"
MQTT_BRIDGE_INFO_TOPIC = "switchbot_urc/bridge/info"
MQTT_BRIDGE_MANAGE_TOPIC = "switchbot_urc/bridge/manage"
MQTT_BRIDGE_MANAGE_RESULT_TOPIC = "switchbot_urc/bridge/manage_result"


def decode_worws_battery(service_data: bytes | bytearray | None) -> int | None:
    """Decode WoRWS battery percentage from its FD3D service-data payload."""
    if not service_data or len(service_data) < 3:
        return None
    battery = int(service_data[2]) & 0x7F
    return battery if 0 <= battery <= 100 else None
