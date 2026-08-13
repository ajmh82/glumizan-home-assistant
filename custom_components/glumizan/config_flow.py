from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import CONF_BASE_URL, CONF_CALLBACK_SECRET, DOMAIN


class GluMizanConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            base_url = user_input[CONF_BASE_URL].rstrip("/")
            if not base_url.startswith("https://"):
                errors["base"] = "https_required"
            else:
                await self.async_set_unique_id(DOMAIN)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="GluMizan", data={**user_input, CONF_BASE_URL: base_url})
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required(CONF_BASE_URL): str,
                vol.Required(CONF_CALLBACK_SECRET): str,
            }),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return GluMizanOptionsFlow()


class GluMizanOptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Required(CONF_BASE_URL, default=data[CONF_BASE_URL]): str,
            vol.Required(CONF_CALLBACK_SECRET, default=data[CONF_CALLBACK_SECRET]): str,
        }))
