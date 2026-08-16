from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import CONF_BASE_URL, CONF_CALLBACK_SECRET, DOMAIN
from .pairing import apply_validated_pairing, validate_pairing


def _schema(base_url: str | None = None):
    fields = {}
    if base_url:
        fields[vol.Required(CONF_BASE_URL, default=base_url)] = str
    else:
        fields[vol.Required(CONF_BASE_URL)] = str
    fields[vol.Required(CONF_CALLBACK_SECRET)] = str
    return vol.Schema(fields)


class GluMizanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            error = await validate_pairing(user_input[CONF_BASE_URL], user_input[CONF_CALLBACK_SECRET])
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title="GluMizan",
                    data={
                        CONF_BASE_URL: user_input[CONF_BASE_URL].strip().rstrip("/"),
                        CONF_CALLBACK_SECRET: user_input[CONF_CALLBACK_SECRET].strip(),
                    },
                )
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    async def async_step_reconfigure(self, user_input=None):
        entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
        errors = {}
        if user_input is not None:
            error = await apply_validated_pairing(self.hass, entry, user_input[CONF_BASE_URL], user_input[CONF_CALLBACK_SECRET])
            if error:
                errors["base"] = error
            else:
                return self.async_abort(reason="reconfigure_successful")
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_schema(base_url=entry.data.get(CONF_BASE_URL)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GluMizanOptionsFlow()


class GluMizanOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry=None):
        if config_entry is not None:
            self._config_entry = config_entry

    def _entry(self):
        return getattr(self, "config_entry", None) or self._config_entry

    async def async_step_init(self, user_input=None):
        entry = self._entry()
        errors = {}
        if user_input is not None:
            error = await apply_validated_pairing(self.hass, entry, user_input[CONF_BASE_URL], user_input[CONF_CALLBACK_SECRET])
            if error:
                errors["base"] = error
            else:
                return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(base_url=entry.data.get(CONF_BASE_URL)),
            errors=errors,
        )
