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
    caregiver_known = set()
    def patient_row(alias):
        data = coordinator.data if isinstance(coordinator.data, dict) else {}
        return data.get(alias) or getattr(coordinator, "patient_data", {}).get(alias) or {}
    def add(aliases):
        if isinstance(aliases, dict):
            aliases = list(aliases.keys())
        pending = [alias for alias in aliases if alias not in known]
        known.update(pending)
        caregiver_pending = [(alias, caregiver) for alias in aliases for caregiver in patient_row(alias).get("caregivers", []) if (alias, caregiver.get("grant_id")) not in caregiver_known]
        caregiver_known.update((alias, caregiver.get("grant_id")) for alias, caregiver in caregiver_pending)
        entities = [entity for alias in pending for entity in (GluMizanGlucoseSensor(coordinator, alias), GluMizanStatusSensor(coordinator, alias), GluMizanActiveAlertSensor(coordinator, alias))]
        entities.extend(GluMizanCaregiverSensor(coordinator, alias, caregiver) for alias, caregiver in caregiver_pending)
        if entities:
            async_add_entities(entities)
    patient_aliases = list(getattr(coordinator, "patient_data", coordinator.data).keys())
    add(patient_aliases)
    entry.async_on_unload(async_dispatcher_connect(hass, signal_patients_changed(entry.entry_id), add))
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


class GluMizanCaregiverSensor(GluMizanPatientEntity, SensorEntity):
    _attr_icon = "mdi:account-heart"

    def __init__(self, coordinator, alias, caregiver):
        super().__init__(coordinator, alias)
        grant_id = caregiver["grant_id"]
        self.grant_id = grant_id
        self._attr_unique_id = f"{DOMAIN}_{alias}_{grant_id}_caregiver"
        self._attr_name = caregiver.get("display_label") or "Caregiver"

    @property
    def caregiver(self):
        return next((item for item in self.coordinator.data.get(self.alias, {}).get("caregivers", []) if item.get("grant_id") == self.grant_id), None)

    @property
    def available(self):
        return super().available and self.caregiver is not None

    @property
    def native_value(self):
        caregiver = self.caregiver or {}
        return caregiver.get("care_state") or "AVAILABLE"

    @property
    def extra_state_attributes(self):
        caregiver = self.caregiver or {}
        return {
            "grant_id": self.grant_id,
            "display_label": caregiver.get("display_label"),
            "care_state": caregiver.get("care_state"),
            "notification_target": caregiver.get("notification_target"),
        }


class GluMizanActiveAlertSensor(GluMizanPatientEntity, SensorEntity):
    _attr_icon = "mdi:bell-alert"
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, alias):
        super().__init__(coordinator, alias)
        self._attr_unique_id = f"{DOMAIN}_{alias}_active_alert"
        self._attr_name = "Active Alerts"

    @property
    def native_value(self):
        data = self.coordinator.data.get(self.alias, {})
        alerts = data.get("active_alerts") or []
        return len(alerts)

    @property
    def extra_state_attributes(self):
        data = self.coordinator.data.get(self.alias, {})
        alerts = data.get("active_alerts") or []
        return {
            "alert_count": len(alerts),
            "alerts": [
                {
                    "category": a.get("category"),
                    "episode_id": a.get("id"),
                    "occurrence_count": a.get("occurrenceCount"),
                    "first_detected_at": a.get("firstDetectedAt"),
                    "last_seen_at": a.get("lastSeenAt"),
                    "last_reading_value": a.get("lastReadingValue"),
                }
                for a in alerts if isinstance(a, dict)
            ],
            "episode": data.get("episode"),
            "episode_id": data.get("episode_id"),
        }
