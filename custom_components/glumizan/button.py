from homeassistant.components.button import ButtonEntity
from .const import DOMAIN
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from .const import SIGNAL_PATIENTS_CHANGED


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = hass.data[DOMAIN][entry.entry_id]
    known = set()
    def add(aliases):
        pending = [alias for alias in aliases if alias not in known]
        known.update(pending)
        if pending:
            async_add_entities([GluMizanAcknowledgeButton(coordinator, alias) for alias in pending])
    add(coordinator.data)
    entry.async_on_unload(async_dispatcher_connect(hass, SIGNAL_PATIENTS_CHANGED, add))


class GluMizanAcknowledgeButton(ButtonEntity):
    def __init__(self, coordinator, alias):
        self.coordinator = coordinator; self.alias = alias; self._attr_unique_id = f"{DOMAIN}_{alias}_acknowledge"; self._attr_name = f"GluMizan {alias} I am with the patient"
    @property
    def available(self):
        return self.alias in self.coordinator.data and bool(self.coordinator.data[self.alias].get("episode_id"))
    async def async_press(self):
        await self.coordinator.async_acknowledge(self.alias, self.coordinator.data[self.alias].get("episode_id"))
