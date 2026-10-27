"""Exercise the real SSE methods through AST without HA, credentials, or network."""
import ast
import asyncio
from datetime import datetime, timedelta, timezone
import logging
from pathlib import Path
import unittest

P = Path(__file__).resolve().parents[1] / "custom_components/glumizan/coordinator.py"
tree = ast.parse(P.read_text(encoding="utf-8"), filename=str(P))
source_functions = [
    node for node in tree.body if isinstance(node, ast.FunctionDef)
    and node.name in {"normalize_episode_ids", "_only_long_lived_technical_alerts"}
]
assert {n.name for n in source_functions} == {"normalize_episode_ids", "_only_long_lived_technical_alerts"}
coordinator = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GluMizanCoordinator")
methods = [n for n in coordinator.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
           and n.name in {"_update_poll_interval", "_sse_connect_once"}]
assert {n.name for n in methods} == {"_update_poll_interval", "_sse_connect_once"}

class UpdateFailed(Exception):
    pass

ns = {
    "datetime": datetime, "timedelta": timedelta, "timezone": timezone,
    "_TECHNICAL_MONITORING_ALERT_CATEGORIES": frozenset({"NO_RECENT_READING", "SYNC_FAILURE"}),
    "_TECHNICAL_ALERT_FAST_GRACE": timedelta(minutes=30),
    "_IDLE_UPDATE_INTERVAL": timedelta(seconds=30), "_ACTIVE_UPDATE_INTERVAL": timedelta(seconds=2),
    "SSE_STREAM_PATH": "/v1/integrations/home-assistant/stream",
    "UpdateFailed": UpdateFailed, "_LOGGER": logging.getLogger("test.sse"),
}
unit = ast.Module(body=source_functions + [
    ast.ClassDef(name="Policy", bases=[], keywords=[], body=methods, decorator_list=[])
], type_ignores=[])
exec(compile(ast.fix_missing_locations(unit), str(P), "exec"), ns)
Policy = ns["Policy"]

def episode(category="NO_RECENT_READING", id="e1"):
    return {"id": id, "category": category,
            "firstDetectedAt": (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()}

class Response:
    def __init__(self, status=200, chunks=(), error=None, hold=False):
        self.status, self.chunks, self.error = status, list(chunks), error
        self.content, self.hold = self, hold
        self.entered, self.release = asyncio.Event(), asyncio.Event()
    async def __aenter__(self):
        return self
    async def __aexit__(self, typ, val, tb):
        return False
    async def iter_any(self):
        for chunk in self.chunks:
            yield chunk
        self.entered.set()
        if self.hold:
            await self.release.wait()
        if self.error:
            raise self.error

class Session:
    def __init__(self, responses):
        self.responses, self.requests = list(responses), []
    def get(self, url, headers):
        self.requests.append((url, headers))
        return self.responses.pop(0)

class FakeCoordinator(Policy):
    def __init__(self, responses, alerts):
        self._session = Session(responses)
        self._sse_connected, self.update_interval = False, timedelta(seconds=2)
        self.patient_data = {"A": {"active_alerts": alerts, "active_episode_ids": [a["id"] for a in alerts], "caregivers": []}}
        self.trace = []
    def _base_url(self):
        return "https://example.invalid"
    def _headers(self):
        return {"X-Home-Assistant-Signature": "dummy-not-secret"}
    async def _async_handle_realtime_invalidation(self):
        self.trace.append(("reconcile", self._sse_connected, self.update_interval.total_seconds()))
    def _queue_realtime_invalidation(self):
        self.trace.append(("event", self._sse_connected, self.update_interval.total_seconds()))

class SSERecoveryTests(unittest.TestCase):
    def test_technical_sse_event_and_disconnect_fallback(self):
        p = FakeCoordinator([Response(chunks=[
            b": heartbeat\n\n", b'event: state.changed\ndata: {"patientId":"opaque"}\n\n'
        ])], [episode(), episode("SYNC_FAILURE", "e2")])
        asyncio.run(p._sse_connect_once())
        self.assertEqual(p.trace, [("reconcile", True, 30), ("event", True, 30)])
        self.assertFalse(p._sse_connected)
        self.assertEqual(p.update_interval, timedelta(seconds=2))
        self.assertTrue(p._session.requests[0][0].endswith("/stream"))

    def test_open_stream_maintains_idle_until_close(self):
        response = Response(chunks=[b": keepalive\n\n"], hold=True)
        p = FakeCoordinator([response], [episode()])
        async def scenario():
            task = asyncio.create_task(p._sse_connect_once())
            await asyncio.wait_for(response.entered.wait(), 2)
            self.assertFalse(task.done())
            self.assertTrue(p._sse_connected)
            self.assertEqual(p.update_interval, timedelta(seconds=30))
            response.release.set()
            await asyncio.wait_for(task, 2)
        asyncio.run(scenario())
        self.assertFalse(p._sse_connected)
        self.assertEqual(p.update_interval, timedelta(seconds=2))

    def test_medical_and_mixed_alert_stay_fast(self):
        for alerts in ([episode("URGENT_LOW")], [episode(), episode("HIGH_GLUCOSE", "e2")]):
            p = FakeCoordinator([Response()], alerts)
            asyncio.run(p._sse_connect_once())
            self.assertEqual(p.trace, [("reconcile", True, 2)])
            self.assertEqual(p.update_interval, timedelta(seconds=2))

    def test_http_401_does_not_mark_connected(self):
        p = FakeCoordinator([Response(status=401)], [episode()])
        with self.assertRaises(UpdateFailed):
            asyncio.run(p._sse_connect_once())
        self.assertFalse(p._sse_connected)
        self.assertEqual(p.trace, [])

    def test_network_exception_restores_fast_polling(self):
        p = FakeCoordinator([Response(error=ConnectionError("closed"))], [episode()])
        with self.assertRaises(ConnectionError):
            asyncio.run(p._sse_connect_once())
        self.assertFalse(p._sse_connected)
        self.assertEqual(p.update_interval, timedelta(seconds=2))

    def test_reconnect_reconciles_again(self):
        p = FakeCoordinator([Response(), Response()], [episode()])
        async def scenario():
            await p._sse_connect_once()
            await p._sse_connect_once()
        asyncio.run(scenario())
        self.assertEqual(p.trace, [("reconcile", True, 30), ("reconcile", True, 30)])
        self.assertEqual(len(p._session.requests), 2)

    def test_malformed_sse_frame_is_ignored(self):
        p = FakeCoordinator([Response(chunks=[
            b"event: state.changed\ndata: not-json\n\n",
            b'event: state.changed\ndata: {"unrelated":true}\n\n',
            b'event: state.changed\ndata: {"patient',
            b'Id":"opaque"}\n\n'])], [episode()])
        asyncio.run(p._sse_connect_once())
        self.assertEqual(p.trace, [("reconcile", True, 30), ("event", True, 30)])

if __name__ == "__main__":
    unittest.main()
