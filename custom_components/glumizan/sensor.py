from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, signal_patients_changed


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    def add(aliases):
        pending = [alias for alias in aliases if alias not in known]
        known.update(pending)
        if pending:
            async_add_entities([entity for alias in pending for entity in (GluMizanGlucoseSensor(coordinator, alias), GluMizanStatusSensor(coordinator, alias))])
    add(coordinator.data)
    entry.async_on_unload(async_dispatcher_connect(hass, signal_patients_changed(entry.entry_id), add))


class GluMizanPatientEntity(CoordinatorEntity):
    def __init__(self, coordinator, alias):
        super().__init__(coordinator)
        self.alias = alias
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, alias)}, name=f"GluMizan {alias}", manufacturer="GluMizan", model="Patient glucose bridge")

    @property
    def available(self):
        return super().available and self.alias in self.coordinator.data


class GluMizanGlucoseSensor(GluMizanPatientEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "mg/dL"
    def __init__(self, coordinator, alias):
        super().__init__(coordinator, alias); self._attr_unique_id = f"{DOMAIN}_{alias}_glucose"
    @property
    def native_value(self): return self.coordinator.data[self.alias].get("value")
    @property
    def extra_state_attributes(self):
        value = self.coordinator.data[self.alias]
        return {"trend": value.get("trend"), "measured_at": value.get("measuredAt"), "freshness": value.get("freshness"), "episode": value.get("episode"), "caregivers": value.get("caregivers", [])}


class GluMizanStatusSensor(GluMizanPatientEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, alias):
        super().__init__(coordinator, alias); self._attr_unique_id = f"{DOMAIN}_{alias}_freshness"
    @property
    def native_value(self): return self.coordinator.data[self.alias].get("freshness")
