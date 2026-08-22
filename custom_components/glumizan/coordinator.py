from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import timedelta
import aiohttp
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.helpers.dispatcher import async_dispatcher_send
try:
    from homeassistant.helpers.storage import Store
except ModuleNotFoundError:  # lightweight contract-test stubs omit HA storage
    class Store:
        def __init__(self, hass, _version, key):
            self._data = hass.data.setdefault("_glumizan_test_storage", {})
            self._key = key

        async def async_load(self):
            return self._data.get(self._key)

        async def async_save(self, value):
            self._data[self._key] = value
from .const import CONF_BASE_URL, CONF_CALLBACK_SECRET, DOMAIN, SSE_STREAM_PATH, SSE_RECONNECT_BASE_SECONDS, SSE_RECONNECT_MAX_SECONDS, SSE_BACKOFF_MULTIPLIER, signal_patients_changed

_LOGGER = logging.getLogger(__name__)
_DELIVERY_DEDUP_VERSION = 1
_DELIVERY_DEDUP_LIMIT = 512
_IDLE_UPDATE_INTERVAL = timedelta(seconds=30)
_ACTIVE_UPDATE_INTERVAL = timedelta(seconds=2)


def re_full_uuid(value):
    try:
        return str(uuid.UUID(value)) == value.lower()
    except (AttributeError, ValueError):
        return False


def normalize_caregivers(raw):
    caregivers = []
    if not isinstance(raw, list):
        return caregivers
    for item in raw:
        if not isinstance(item, dict):
            continue
        grant_id = item.get("grant_id") or item.get("grantId")
        if not isinstance(grant_id, str) or not grant_id:
            continue
        caregivers.append({
            "grant_id": grant_id,
            "display_label": item.get("display_label") or item.get("displayLabel") or "Caregiver",
            "care_state": item.get("care_state") or item.get("careState") or "AVAILABLE",
            "active_episode_id": item.get("active_episode_id") or item.get("activeEpisodeId"),
            "active_presence_session_id": item.get("active_presence_session_id") or item.get("activePresenceSessionId"),
            "notification_target": item.get("notification_target") or item.get("notificationTarget"),
            "permissions": item.get("permissions") or [],
        })
    return caregivers


def normalize_episode_ids(raw):
    if not isinstance(raw, list):
        return []
    return list(dict.fromkeys(item for item in raw if isinstance(item, str) and item))


def set_active_episode_ids(current, episode_ids):
    normalized = normalize_episode_ids(episode_ids)
    current["active_episode_ids"] = normalized
    current["episode_id"] = normalized[0] if len(normalized) == 1 else None


class GluMizanCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry):
        self.entry = entry
        self._session = aiohttp.ClientSession()
        self.patient_data = {}
        self._delivery_store = Store(hass, _DELIVERY_DEDUP_VERSION, f"{DOMAIN}.{entry.entry_id}.deliveries")
        self._processed_delivery_ids = set()
        self._delivery_dedup_loaded = False
        self._fired_opened_episode_ids = set()
        self._fired_alert_transition_keys = set()
        self._sse_task = None
        self._sse_reconnect_delay = SSE_RECONNECT_BASE_SECONDS
        super().__init__(hass, _LOGGER, name=DOMAIN, update_interval=_IDLE_UPDATE_INTERVAL)

    async def async_close(self):
        if self._sse_task and not self._sse_task.done():
            self._sse_task.cancel()
            try:
                await self._sse_task
            except asyncio.CancelledError:
                pass
        await self._session.close()

    def _snapshot(self):
        return {alias: dict(value) for alias, value in self.patient_data.items()}

    def _update_poll_interval(self):
        active = any(
            data.get("active_episode_ids") or data.get("active_alerts") or any(
                caregiver.get("care_state") == "WITH_PATIENT" or caregiver.get("active_presence_session_id")
                for caregiver in data.get("caregivers", []) if isinstance(caregiver, dict)
            )
            for data in self.patient_data.values()
        )
        interval = _ACTIVE_UPDATE_INTERVAL if active else _IDLE_UPDATE_INTERVAL
        if getattr(self, "update_interval", None) != interval:
            self.update_interval = interval

    async def _async_update_data(self):
        try:
            async with asyncio.timeout(25):
                async with self._session.get(f"{self._base_url()}/v1/integrations/home-assistant/events?limit=100", headers=self._headers()) as response:
                    if response.status < 300:
                        body = await response.json()
                        await self.async_receive_events(body.get("events", []))
                        await self.async_receive_delivery_events(body.get("deliveries", []))
                return self._snapshot()
        except TimeoutError as error:
            raise UpdateFailed("GluMizan bridge unavailable") from error

    async def async_receive_events(self, events):
        event_ids = []
        new_aliases = []
        for event in events:
            alias = event["patientAlias"]
            if alias not in self.patient_data:
                new_aliases.append(alias)
            prev = self.patient_data.get(alias, {})
            prev_alerts = list(prev.get("active_alerts", []))
            prev_caregivers = list(prev.get("caregivers", []))
            current = self.patient_data.setdefault(alias, {"alias": alias, "glucose": None, "trend": None, "freshness": "UNKNOWN", "episode": None, "active_alerts": [], "caregivers": []})
            payload = event.get("payload", {})
            glucose = payload.get("glucose")
            if glucose:
                current.update(glucose)
            if "caregivers" in payload:
                incoming = normalize_caregivers(payload.get("caregivers"))
                if incoming or not current.get("caregivers"):
                    current["caregivers"] = incoming
            if event["type"].startswith("episode."):
                current["episode"] = event["type"]
                episode_id = payload.get("episodeId") or payload.get("activeEpisodeId")
                if isinstance(episode_id, str) and episode_id:
                    set_active_episode_ids(current, [episode_id])
            if "activeAlerts" in payload:
                current["active_alerts"] = payload["activeAlerts"] or []
                set_active_episode_ids(current, [alert.get("id") for alert in current["active_alerts"] if isinstance(alert, dict)])
            if isinstance(event["id"], str) and len(event["id"]) == 36:
                event_ids.append(event["id"])
            await self.async_refresh_presence_context(alias)
            new_alerts = current.get("active_alerts", [])
            self._fire_alert_events(alias, prev_alerts, new_alerts)
            self._fire_care_events(alias, prev_caregivers, current.get("caregivers", []))
        self._update_poll_interval()
        self.async_set_updated_data(self._snapshot())
        if new_aliases:
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), new_aliases)
        else:
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), list(self.patient_data))
        if event_ids:
            headers = self._headers()
            try:
                async with self._session.post(f"{self._base_url()}/v1/integrations/home-assistant/events/ack", headers=headers, json={"eventIds": event_ids}) as response:
                    if response.status >= 300:
                        _LOGGER.warning("GluMizan event acknowledgement failed with status %s", response.status)
            except Exception:
                _LOGGER.warning("GluMizan event acknowledgement failed", exc_info=True)

    async def _async_load_delivery_dedup(self):
        if self._delivery_dedup_loaded:
            return
        saved = await self._delivery_store.async_load()
        if isinstance(saved, list):
            self._processed_delivery_ids = {item for item in saved if isinstance(item, str)}
        self._delivery_dedup_loaded = True

    async def _async_record_delivery(self, delivery_id):
        self._processed_delivery_ids.add(delivery_id)
        if len(self._processed_delivery_ids) > _DELIVERY_DEDUP_LIMIT:
            self._processed_delivery_ids = set(sorted(self._processed_delivery_ids)[-_DELIVERY_DEDUP_LIMIT:])
        await self._delivery_store.async_save(sorted(self._processed_delivery_ids))

    async def async_receive_delivery_events(self, deliveries):
        await self._async_load_delivery_dedup()
        acknowledged = []
        if not isinstance(deliveries, list):
            return
        for delivery in deliveries:
            if not isinstance(delivery, dict):
                _LOGGER.warning("GluMizan alert delivery was malformed")
                continue
            delivery_id = delivery.get("delivery_id")
            alias = delivery.get("patient_alias")
            is_test = delivery.get("is_test") is True
            episode_id = delivery.get("episode_id")
            test_id = delivery.get("test_id")
            if not isinstance(delivery_id, str) or not re_full_uuid(delivery_id) or not isinstance(alias, str) or not alias.startswith("A") or (is_test and not isinstance(test_id, str)) or (not is_test and not isinstance(episode_id, str)):
                _LOGGER.warning("GluMizan alert delivery was malformed")
                continue
            if delivery_id in self._processed_delivery_ids:
                acknowledged.append(delivery_id)
                continue
            try:
                await self._async_record_delivery(delivery_id)
            except Exception:
                _LOGGER.warning("GluMizan alert delivery could not be persisted", exc_info=True)
                continue
            event_data = {
                "delivery_id": delivery_id,
                "patient_alias": alias,
                "episode_id": episode_id if not is_test else None,
                "test_id": test_id if is_test else None,
                "event": delivery.get("event"),
                "action": delivery.get("action"),
                "category": delivery.get("category"),
                "severity": delivery.get("severity"),
                "recipient_role": delivery.get("recipient_role"),
                "recipient_ref": delivery.get("recipient_ref"),
                "route_key": delivery.get("route_key"),
                "notification_target": delivery.get("notification_target"),
                "is_test": is_test,
                "created_at": delivery.get("created_at"),
            }
            if isinstance(delivery.get("glucose"), dict):
                event_data["glucose"] = delivery["glucose"]
            transition_action = event_data.get("action")
            transition_episode_id = event_data.get("episode_id")
            transition_key = (
                str(transition_episode_id),
                str(transition_action),
            ) if transition_episode_id and transition_action in ("opened", "resolved") else None
            if transition_key is None or transition_key not in self._fired_alert_transition_keys:
                self.hass.bus.async_fire(f"{DOMAIN}_alert", event_data)
                if transition_key is not None:
                    self._fired_alert_transition_keys.add(transition_key)
                    if transition_action == "opened":
                        self._fired_opened_episode_ids.add(str(transition_episode_id))
            acknowledged.append(delivery_id)
        if acknowledged:
            try:
                async with self._session.post(
                    f"{self._base_url()}/v1/integrations/home-assistant/events/ack",
                    headers=self._headers(),
                    json={"deliveryIds": acknowledged},
                ) as response:
                    if response.status >= 300:
                        _LOGGER.warning("GluMizan alert delivery acknowledgement failed with status %s", response.status)
            except Exception:
                _LOGGER.warning("GluMizan alert delivery acknowledgement failed", exc_info=True)

    def _headers(self):
        return {"X-Home-Assistant-Signature": self.entry.data[CONF_CALLBACK_SECRET]}

    def _fire_alert_events(self, alias, previous_alerts, current_alerts):
        prev_ids = {a.get("id") for a in previous_alerts if isinstance(a, dict)}
        curr_ids = {a.get("id") for a in current_alerts if isinstance(a, dict)}
        for alert in current_alerts:
            if not isinstance(alert, dict):
                continue
            aid = alert.get("id")
            if aid and aid not in prev_ids:
                transition_key = (str(aid), "opened")
                if transition_key not in self._fired_alert_transition_keys:
                    self.hass.bus.async_fire(f"{DOMAIN}_alert", {
                        "patient_alias": alias,
                        "action": "opened",
                        "category": alert.get("category"),
                        "episode_id": aid,
                        "occurrence_count": alert.get("occurrenceCount"),
                    })
                    self._fired_alert_transition_keys.add(transition_key)
                self._fired_opened_episode_ids.add(aid)
        for alert in previous_alerts:
            if not isinstance(alert, dict):
                continue
            aid = alert.get("id")
            if aid and aid not in curr_ids:
                transition_key = (str(aid), "resolved")
                if transition_key not in self._fired_alert_transition_keys:
                    self.hass.bus.async_fire(f"{DOMAIN}_alert", {
                        "patient_alias": alias,
                        "action": "resolved",
                        "category": alert.get("category"),
                        "episode_id": aid,
                    })
                    self._fired_alert_transition_keys.add(transition_key)
                self._fired_opened_episode_ids.discard(aid)

    def _fire_care_events(self, alias, previous_caregivers, current_caregivers):
        prev_states = {}
        for cg in previous_caregivers:
            if isinstance(cg, dict):
                gid = cg.get("grant_id")
                if gid:
                    prev_states[gid] = cg.get("care_state")
        for cg in current_caregivers:
            if not isinstance(cg, dict):
                continue
            gid = cg.get("grant_id")
            if not gid:
                continue
            curr_state = cg.get("care_state")
            prev_state = prev_states.get(gid)
            if prev_state is not None and curr_state != prev_state:
                self.hass.bus.async_fire(f"{DOMAIN}_care", {
                    "patient_alias": alias,
                    "grant_id": gid,
                    "care_state": curr_state,
                    "previous_care_state": prev_state,
                    "display_label": cg.get("display_label"),
                })

    def _base_url(self):
        return self.entry.data[CONF_BASE_URL]

    async def async_command(self, alias, grant_id, action, episode_id=None):
        previous_caregivers = list(
            self.patient_data.get(alias, {}).get("caregivers", [])
        )
        headers = {"Idempotency-Key": str(uuid.uuid4()), **self._headers()}
        body = {"action": action, "patientAlias": alias, "grantId": grant_id, "metadata": {"action": "caregiver_response"}}
        if episode_id:
            body["episodeId"] = episode_id
        async with self._session.post(f"{self._base_url()}/v1/integrations/home-assistant/commands", headers=headers, json=body) as response:
            if response.status >= 300:
                raise UpdateFailed("GluMizan command rejected")
        await self.async_refresh_presence_context(alias)
        self._fire_care_events(
            alias,
            previous_caregivers,
            self.patient_data.get(alias, {}).get("caregivers", []),
        )
        self.async_set_updated_data(self._snapshot())

    async def async_refresh_presence_context(self, alias):
        async with self._session.get(f"{self._base_url()}/v1/integrations/home-assistant/patients/{alias}/presence", headers=self._headers()) as response:
            if response.status < 300:
                payload = await response.json()
                caregivers = normalize_caregivers(payload.get("caregivers", []))
                current = self.patient_data.setdefault(alias, {"alias": alias, "glucose": None, "trend": None, "freshness": "UNKNOWN", "episode": None, "active_alerts": [], "caregivers": []})
                caregivers_updated = False
                if caregivers or not current.get("caregivers"):
                    current["caregivers"] = caregivers
                    caregivers_updated = True
                if "activeEpisodeIds" in payload:
                    episode_ids = normalize_episode_ids(payload.get("activeEpisodeIds"))
                    known_alerts = {alert.get("id"): alert for alert in current.get("active_alerts", []) if isinstance(alert, dict) and alert.get("id") in episode_ids}
                    current["active_alerts"] = [known_alerts.get(episode_id, {"id": episode_id}) for episode_id in episode_ids]
                    set_active_episode_ids(current, episode_ids)
                elif caregivers_updated:
                    episode_ids = [item.get("active_episode_id") for item in caregivers if item.get("active_episode_id")]
                    set_active_episode_ids(current, episode_ids)
                    if not episode_ids:
                        current["active_alerts"] = []
                self._update_poll_interval()

    async def async_request_reconcile(self):
        headers = self._headers()
        async with self._session.post(f"{self._base_url()}/v1/integrations/home-assistant/reconcile", headers=headers, json={}) as response:
            if response.status >= 300:
                _LOGGER.warning("GluMizan reconcile request failed with status %s", response.status)
        for alias in list(self.patient_data):
            await self.async_refresh_presence_context(alias)
        if self.patient_data:
            self.async_set_updated_data(self._snapshot())
            async_dispatcher_send(self.hass, signal_patients_changed(self.entry.entry_id), list(self.patient_data))

    async def async_acknowledge(self, alias, grant_id, episode_id):
        if not episode_id:
            raise UpdateFailed("No active GluMizan episode for this patient")
        await self.async_command(alias, grant_id, "caregiver.acknowledge", episode_id)

    def start_sse_listener(self):
        if self._sse_task and not self._sse_task.done():
            return
        self._sse_task = self.hass.async_create_background_task(
            self._sse_listener_loop(), f"{DOMAIN}_sse_{self.entry.entry_id}"
        )

    async def _sse_listener_loop(self):
        backoff = SSE_RECONNECT_BASE_SECONDS
        while True:
            try:
                await self._sse_connect_once()
                backoff = SSE_RECONNECT_BASE_SECONDS
            except asyncio.CancelledError:
                return
            except Exception:
                _LOGGER.debug("GluMizan SSE connection lost, reconnecting in %ss", backoff)
            await asyncio.sleep(backoff)
            backoff = min(backoff * SSE_BACKOFF_MULTIPLIER, SSE_RECONNECT_MAX_SECONDS)

    async def _sse_connect_once(self):
        url = f"{self._base_url()}{SSE_STREAM_PATH}"
        headers = self._headers()
        async with self._session.get(url, headers=headers) as response:
            if response.status >= 300:
                _LOGGER.warning("GluMizan SSE rejected with status %s", response.status)
                raise UpdateFailed(f"SSE rejected {response.status}")
            buffer = ""
            async for chunk in response.content.iter_any():
                buffer += chunk.decode("utf-8", errors="replace")
                while "\n\n" in buffer:
                    event_block, buffer = buffer.split("\n\n", 1)
                    event_type = None
                    data_lines = []
                    for line in event_block.split("\n"):
                        if line.startswith("event: "):
                            event_type = line[7:].strip()
                        elif line.startswith("data: "):
                            data_lines.append(line[6:])
                        elif line.startswith(":"):
                            continue
                    if event_type == "state.changed" and data_lines:
                        try:
                            import json
                            signal = json.loads(data_lines[0])
                            if isinstance(signal, dict) and signal.get("patientId"):
                                self.hass.async_create_task(self.async_request_refresh())
                        except Exception:
                            pass
