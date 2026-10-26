"""Isolated policy tests exercising the actual coordinator AST, no Home Assistant dependency."""
import ast
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest

COORDINATOR = Path(__file__).resolve().parents[1] / 'custom_components/glumizan/coordinator.py'
SOURCE = COORDINATOR.read_text(encoding='utf-8')
TREE = ast.parse(SOURCE, filename=str(COORDINATOR))

def extract_function(name):
    functions = [n for n in TREE.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(functions) != 1:
        raise AssertionError('Expected exactly one function: ' + name)
    return functions[0]

helper_nodes = [extract_function(n) for n in ('normalize_episode_ids','_only_long_lived_technical_alerts')]
coordinator = next(n for n in TREE.body if isinstance(n, ast.ClassDef) and n.name == 'GluMizanCoordinator')
policy = next(n for n in coordinator.body if isinstance(n, ast.FunctionDef) and n.name == '_update_poll_interval')
# Execute the source-derived policy methods without creating HA entities or requesting network access.
module = ast.fix_missing_locations(ast.Module(body=helper_nodes, type_ignores=[]))
context = {'datetime':datetime, 'timedelta':timedelta, 'timezone':timezone,
           '_TECHNICAL_MONITORING_ALERT_CATEGORIES':frozenset({'NO_RECENT_READING','SYNC_FAILURE'}),
           '_TECHNICAL_ALERT_FAST_GRACE':timedelta(minutes=30)}
exec(compile(module, str(COORDINATOR), 'exec'), context)
cls = ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Policy',bases=[],keywords=[],body=[policy],decorator_list=[])],type_ignores=[]))
context.update({'_IDLE_UPDATE_INTERVAL':timedelta(seconds=30),
                '_ACTIVE_UPDATE_INTERVAL':timedelta(seconds=2)})
exec(compile(cls,str(COORDINATOR),'exec'),context)
Policy = context['Policy']
classification = context['_only_long_lived_technical_alerts']
NOW = datetime.now(timezone.utc)

def alert(category='NO_RECENT_READING', age_minutes=200, episode_id='id-1', timestamp=None):
    return {'id':episode_id,'category':category,
            'firstDetectedAt':timestamp if timestamp is not None else (NOW-timedelta(minutes=age_minutes)).isoformat()}

def patient(*alerts, episode_ids=None, caregivers=None):
    return {'active_alerts':list(alerts),
            'active_episode_ids':list(episode_ids) if episode_ids is not None else [x['id'] for x in alerts],
            'caregivers':caregivers or []}

def seconds(data, sse=True):
    instance = Policy()
    instance._sse_connected = sse
    instance.patient_data = ({'a':data} if isinstance(data,dict) and 'active_alerts' in data else data)
    instance.update_interval=None
    instance._update_poll_interval()
    return int(instance.update_interval.total_seconds())

class PollingSafety(unittest.TestCase):
    def test_no_active_alerts_idle(self):
        self.assertEqual(seconds(patient()),30)
    def test_two_chronic_technical_alerts_reduce_polling_only_with_sse(self):
        p=patient(alert(),alert('SYNC_FAILURE',300,'id-2'))
        self.assertTrue(classification(p))
        self.assertEqual(seconds(p,True),30)
        self.assertEqual(seconds(p,False),2)
    def test_medical_low_and_high_remain_fast(self):
        for category in ('LOW_GLUCOSE','URGENT_LOW','HIGH_GLUCOSE','EMERGENCY','PATIENT_SOS'):
            with self.subTest(category=category):
                self.assertEqual(seconds(patient(alert(category)),True),2)
    def test_mixed_medical_and_technical_remain_fast(self):
        self.assertEqual(seconds(patient(alert(),alert('URGENT_LOW',300,'id-2')),True),2)
    def test_unknown_category_remains_fast(self):
        self.assertEqual(seconds(patient(alert('UNKNOWN_ALERT')),True),2)
    def test_new_technical_alert_remains_fast(self):
        self.assertEqual(seconds(patient(alert(age_minutes=5)),True),2)
    def test_age_cutoff(self):
        self.assertFalse(classification(patient(alert(age_minutes=29)),NOW))
        self.assertTrue(classification(patient(alert(age_minutes=31)),NOW))
    def test_invalid_timestamp_remains_fast(self):
        for stamp in ('not-a-date','2026-10-01T00:00:00','',123):
            with self.subTest(stamp=stamp):
                self.assertEqual(seconds(patient(alert(timestamp=stamp)),True),2)
    def test_future_timestamp_remains_fast(self):
        self.assertEqual(seconds(patient(alert(timestamp=(NOW+timedelta(hours=1)).isoformat())),True),2)
    def test_mismatched_episode_ids_remain_fast(self):
        self.assertEqual(seconds(patient(alert(),episode_ids=['different']),True),2)
    def test_missing_episode_ids_remain_fast(self):
        self.assertEqual(seconds(patient(alert(),episode_ids=[]),True),2)
    def test_episode_without_alert_remains_fast(self):
        self.assertEqual(seconds(patient(episode_ids=['id-1']),True),2)
    def test_duplicate_episode_ids_remain_fast(self):
        self.assertEqual(seconds(patient(alert(),alert(episode_id='id-1')),True),2)
    def test_non_dict_alert_remains_fast(self):
        self.assertEqual(seconds(patient('not-an-object', episode_ids=['id-1']),True),2)
    def test_presence_fallback(self):
        p=patient(caregivers=[{'care_state':'WITH_PATIENT'}])
        self.assertEqual(seconds(p,True),30)
        self.assertEqual(seconds(p,False),2)
    def test_multiple_patients_any_critical_remains_fast(self):
        self.assertEqual(seconds({'one':patient(alert()),'two':patient(alert('URGENT_LOW'))},True),2)
    def test_no_unconditional_medical_relaxation(self):
        self.assertIn('_ACTIVE_UPDATE_INTERVAL = timedelta(seconds=2)',SOURCE)
        self.assertIn('and not (self._sse_connected and _only_long_lived_technical_alerts(data))',SOURCE)
        self.assertIn('await self.async_receive_delivery_events(body.get("deliveries", []))',SOURCE)
        self.assertIn('await self._async_handle_realtime_invalidation()',SOURCE)
        self.assertIn('self._sse_connected = False',SOURCE)

if __name__=='__main__':
    unittest.main()
