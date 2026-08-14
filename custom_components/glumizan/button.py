from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import signal_patients_changed


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    def add(aliases):
        if isinstance(aliases, dict):
            aliases = list(aliases.keys())
        pending = [(alias, caregiver) for alias in aliases for caregiver in coordinator.data.get(alias, {}).get("caregivers", []) if (alias, caregiver["grant_id"]) not in known]
        known.update((alias, caregiver["grant_id"]) for alias, caregiver in pending)
        if pending:
            async_add_entities([entity for alias, caregiver in pending for entity in (GluMizanAcknowledgeButton(coordinator, alias, caregiver["grant_id"]), GluMizanPresenceButton(coordinator, alias, caregiver["grant_id"], "start"), GluMizanPresenceButton(coordinator, alias, caregiver["grant_id"], "end"))])
    patient_aliases = list(getattr(coordinator, "patient_data", coordinator.data).keys())
    add(patient_aliases)
    entry.async_on_unload(async_dispatcher_connect(hass, signal_patients_changed(entry.entry_id), add))
    add(patient_aliases)


class GluMizanAcknowledgeButton(ButtonEntity):
    def __init__(self, coordinator, alias, grant_id):
        self.coordinator = coordinator; self.alias = alias; self.grant_id = grant_id; self._attr_unique_id = f"{DOMAIN}_{alias}_{grant_id}_acknowledge"; self._attr_name = "Acknowledge Alert"
    @property
    def available(self):
        return self.alias in self.coordinator.data and bool(self.coordinator.data[self.alias].get("episode_id"))
    async def async_press(self):
        await self.coordinator.async_acknowledge(self.alias, self.grant_id, self.coordinator.data[self.alias].get("episode_id"))


class GluMizanPresenceButton(ButtonEntity):
    def __init__(self, coordinator, alias, grant_id, action):
        self.coordinator = coordinator; self.alias = alias; self.grant_id = grant_id; self.action = action; self._attr_unique_id = f"{DOMAIN}_{alias}_{grant_id}_{'leave' if action == 'end' else 'arrive'}"; self._attr_name = "I Left The Patient" if action == "end" else "I Am With The Patient"
    @property
    def available(self):
        caregiver = next((item for item in self.coordinator.data.get(self.alias, {}).get("caregivers", []) if item["grant_id"] == self.grant_id), None)
        return caregiver is not None and bool(caregiver.get("active_presence_session_id")) == (self.action == "end")
    async def async_press(self):
        await self.coordinator.async_command(self.alias, self.grant_id, "caregiver.presence.end" if self.action == "end" else "caregiver.presence.start")
