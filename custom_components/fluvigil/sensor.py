"""The water-level sensor for one gauge."""

from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import UnitOfLength
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from . import FluvigilConfigEntry
from .const import CONF_STATION_ID, DOMAIN
from .coordinator import FluvigilCoordinator

WATER_LEVEL = SensorEntityDescription(
    key="water_level",
    translation_key="water_level",
    device_class=SensorDeviceClass.DISTANCE,
    native_unit_of_measurement=UnitOfLength.CENTIMETERS,
    state_class=SensorStateClass.MEASUREMENT,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: FluvigilConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([FluvigilWaterLevelSensor(entry.runtime_data, entry)])


class FluvigilWaterLevelSensor(CoordinatorEntity[FluvigilCoordinator], SensorEntity):
    """Water level in centimetres above the gauge datum."""

    _attr_has_entity_name = True
    entity_description = WATER_LEVEL

    def __init__(self, coordinator: FluvigilCoordinator, entry: FluvigilConfigEntry) -> None:
        super().__init__(coordinator)
        station_id = entry.data[CONF_STATION_ID]
        self._attr_unique_id = f"{station_id}_water_level"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, station_id)},
            name=entry.title,
            manufacturer="Fluvigil",
            model="Pegel",
            configuration_url=f"https://fluvigil.de/stations/{station_id}",
        )

    @property
    def native_value(self) -> int | None:
        return self.coordinator.data.value_centimeters if self.coordinator.data else None

    @property
    def available(self) -> bool:
        # A gauge that reports no value is as unavailable as one we could not reach — showing
        # the last known reading as if it were current is the failure this guards against.
        return super().available and self.coordinator.data is not None and (
            self.coordinator.data.value_centimeters is not None
        )

    @property
    def extra_state_attributes(self) -> dict[str, str | bool | None]:
        state = self.coordinator.data

        if state is None:
            return {}

        return {
            # When the gauge was read, as opposed to when we fetched it — the two differ by
            # up to the poll interval and only the former says how fresh the number is.
            "measured_at": state.measured_at.isoformat() if state.measured_at else None,
            "water": state.water,
            "severity": state.severity,
            "headline": state.headline,
            "is_flood": state.is_flood,
        }
