"""Battery sensor for the SwitchBot Universal Remote (WoRWS)."""
from __future__ import annotations

from collections.abc import Callable

from homeassistant.components import bluetooth
from homeassistant.components.bluetooth import (
    BluetoothCallbackMatcher,
    BluetoothChange,
    BluetoothScanningMode,
    BluetoothServiceInfoBleak,
)
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_ADDRESS, DOMAIN, SVC_WORWS_ADVERTISEMENT, decode_worws_battery


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the WoRWS battery sensor."""
    async_add_entities([UrcBatterySensor(hass, entry)])


class UrcBatterySensor(SensorEntity):
    """Battery percentage advertised by the physical Universal Remote."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True
    _attr_name = "Battery"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_should_poll = False
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self._hass = hass
        self._address = str(entry.data[CONF_ADDRESS]).upper()
        self._attr_unique_id = f"{self._address.replace(':', '').lower()}_battery"
        self._attr_native_value: int | None = None
        self._attr_available = False
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._address)},
            connections={(CONNECTION_BLUETOOTH, self._address)},
            manufacturer="SwitchBot",
            model="Universal Remote (WoRWS)",
            name=entry.title or f"Universal Remote {self._address}",
        )

    async def async_added_to_hass(self) -> None:
        """Listen for passive WoRWS advertisements."""
        await super().async_added_to_hass()
        if service_info := bluetooth.async_last_service_info(
            self._hass, self._address, connectable=True
        ):
            self._apply_advertisement(service_info, write_state=False)

        unsubscribe: Callable[[], None] = bluetooth.async_register_callback(
            self._hass,
            self._async_advertisement,
            BluetoothCallbackMatcher(address=self._address),
            BluetoothScanningMode.PASSIVE,
        )
        self.async_on_remove(unsubscribe)

    @callback
    def _async_advertisement(
        self, service_info: BluetoothServiceInfoBleak, change: BluetoothChange
    ) -> None:
        """Update the entity whenever the remote advertises a battery value."""
        self._apply_advertisement(service_info, write_state=True)

    @callback
    def _apply_advertisement(
        self, service_info: BluetoothServiceInfoBleak, *, write_state: bool
    ) -> None:
        payload = service_info.service_data.get(SVC_WORWS_ADVERTISEMENT)
        battery = decode_worws_battery(payload)
        if battery is None:
            return
        self._attr_native_value = battery
        self._attr_available = True
        if write_state:
            self.async_write_ha_state()
