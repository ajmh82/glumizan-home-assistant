from homeassistant.components.button import ButtonEntity
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import signal_patients_changed


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    def patient_row(alias):
        data = coordinator.data if isinstance(coordinator.data, dict) else {}
        return data.get(alias) or getattr(coordinator, "patient_data", {}).get(alias) or {}
    def add(aliases):
        if isinstance(aliases, dict):
            aliases = list(aliases.keys())
        pending = [(alias, caregiver) for alias in aliases for caregiver in patient_row(alias).get("caregivers", []) if caregiver.get("grant_id") and (alias, caregiver["grant_id"]) not in known]
        known.update((alias, caregiver["grant_id"]) for alias, caregiver in pending)
        if pending:
            entities = [entity for alias, caregiver in pending for entity in (GluMizanAcknowledgeButton(coordinator, alias, caregiver["grant_id"]), GluMizanPresenceButton(coordinator, alias, caregiver["grant_id"], "start"), GluMizanPresenceButton(coordinator, alias, caregiver["grant_id"], "end"))]
            async_add_entities(entities)
    patient_aliases = list(getattr(coordinator, "patient_data", coordinator.data).keys())
    add(patient_aliases)
    entry.async_on_unload(async_dispatcher_connect(hass, signal_patients_changed(entry.entry_id), add))
    add(patient_aliases)


class GluMizanCaregiverButton(CoordinatorEntity, ButtonEntity):
    def __init__(self, coordinator, alias, grant_id):
        super().__init__(coordinator)
        self.alias = alias
        self.grant_id = grant_id
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, alias)}, name=f"GluMizan {alias}", manufacturer="GluMizan", model="CGM Patient Bridge")

    @property
    def caregiver(self):
        return next((item for item in self.coordinator.data.get(self.alias, {}).get("caregivers", []) if item["grant_id"] == self.grant_id), None)

    def _active_episode_id(self):
        patient = self.coordinator.data.get(self.alias, {})
        episode_ids = patient.get("active_episode_ids")
        if isinstance(episode_ids, list):
            canonical = list(dict.fromkeys(episode_id for episode_id in episode_ids if isinstance(episode_id, str) and episode_id))
            return canonical[0] if len(canonical) == 1 else None
        return (self.caregiver or {}).get("active_episode_id") or patient.get("episode_id")

    @property
    def available(self):
        return super().available and self.caregiver is not None


class GluMizanAcknowledgeButton(GluMizanCaregiverButton):
    def __init__(self, coordinator, alias, grant_id):
        super().__init__(coordinator, alias, grant_id)
        self._attr_unique_id = f"{DOMAIN}_{alias}_{grant_id}_acknowledge"
        self._attr_name = "Acknowledge Alert"

    @property
    def available(self):
        return super().available and bool(self._active_episode_id())

    async def async_press(self):
        episode_id = self._active_episode_id()
        if not episode_id:
            return
        await self.coordinator.async_acknowledge(self.alias, self.grant_id, episode_id)


class GluMizanPresenceButton(GluMizanCaregiverButton):
    def __init__(self, coordinator, alias, grant_id, action):
        super().__init__(coordinator, alias, grant_id)
        self.action = action
        self._attr_unique_id = f"{DOMAIN}_{alias}_{grant_id}_{'leave' if action == 'end' else 'arrive'}"
        self._attr_name = "I Left The Patient" if action == "end" else "I Am With The Patient"

    @property
    def available(self):
        caregiver = self.caregiver
        if not super().available or caregiver is None:
            return False
        if not self._active_episode_id():
            return False
        claimed = bool(caregiver.get("active_presence_session_id")) or caregiver.get("care_state") == "WITH_PATIENT"
        if self.action == "end":
            return claimed
        all_caregivers = self.coordinator.data.get(self.alias, {}).get("caregivers", [])
        any_claimed = any(
            bool(c.get("active_presence_session_id")) or c.get("care_state") == "WITH_PATIENT"
            for c in all_caregivers
        )
        return not any_claimed

    async def async_press(self):
        episode_id = self._active_episode_id()
        if not episode_id:
            return
        await self.coordinator.async_command(self.alias, self.grant_id, "caregiver.presence.end" if self.action == "end" else "caregiver.presence.start", episode_id)
