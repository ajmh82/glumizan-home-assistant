from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import DOMAIN, signal_patients_changed
from .presentation import last_reading_time, nightscout_direction, trend_presentation


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    def add(aliases, defer=False):
        if isinstance(aliases, dict):
            aliases = list(aliases.keys())
        pending = [alias for alias in aliases if alias not in known]
        known.update(pending)
        if pending:
            entities = [entity for alias in pending for entity in (GluMizanGlucoseSensor(coordinator, alias), GluMizanStatusSensor(coordinator, alias))]
            if defer:
                hass.async_add_job(async_add_entities, entities)
            else:
                async_add_entities(entities)
    patient_aliases = list(getattr(coordinator, "patient_data", coordinator.data).keys())
    add(patient_aliases)
    entry.async_on_unload(async_dispatcher_connect(hass, signal_patients_changed(entry.entry_id), lambda aliases: add(aliases, defer=True)))
    add(patient_aliases)


class GluMizanPatientEntity(CoordinatorEntity):
    def __init__(self, coordinator, alias):
        super().__init__(coordinator)
        self.alias = alias
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, alias)}, name=f"GluMizan {alias}", manufacturer="GluMizan", model="CGM Patient Bridge")

    @property
    def available(self):
        return super().available and self.alias in self.coordinator.data


class GluMizanGlucoseSensor(GluMizanPatientEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.BLOOD_GLUCOSE_CONCENTRATION
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "mg/dL"
    def __init__(self, coordinator, alias):
        super().__init__(coordinator, alias); self._attr_unique_id = f"{DOMAIN}_{alias}_glucose"; self._attr_name = "Glucose"
    @property
    def native_value(self): return self.coordinator.data[self.alias].get("value")
    @property
    def extra_state_attributes(self):
        value = self.coordinator.data[self.alias]
        trend_label, trend_icon = trend_presentation(value.get("trend"))
        measured_at = value.get("measuredAt")
        return {"trend": value.get("trend"), "direction": nightscout_direction(value.get("trend")), "trend_label": trend_label, "trend_icon": trend_icon, "measured_at": measured_at, "measurement_timestamp": measured_at, "last_reading_time": last_reading_time(measured_at), "freshness": value.get("freshness"), "update_source": value.get("updateSource"), "episode": value.get("episode"), "care_response": value.get("careResponse"), "caregivers": [{"grant_id": caregiver.get("grant_id"), "display_label": caregiver.get("display_label"), "care_state": caregiver.get("care_state"), "notification_target": caregiver.get("notification_target")} for caregiver in value.get("caregivers", [])]}
    @property
    def icon(self):
        return trend_presentation(self.coordinator.data[self.alias].get("trend"))[1]


class GluMizanStatusSensor(GluMizanPatientEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    def __init__(self, coordinator, alias):
        super().__init__(coordinator, alias); self._attr_unique_id = f"{DOMAIN}_{alias}_freshness"; self._attr_name = "Data Freshness"
    @property
    def native_value(self): return self.coordinator.data[self.alias].get("freshness")
