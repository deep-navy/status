import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('reconcile_status_tools', Path(__file__).parents[1] / 'scripts/reconcile_status_tools.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Reconciliation(unittest.TestCase):
    def client(self):
        state = {'energy_search': True, 'news_search': False, 'monitor_poll': True, 'monitor_ack': True}
        methods = []

        def call(service, method, body):
            methods.append((method, body.copy()))
            if method == 'ListApiKeys':
                return {'keys': [{'id': 'existing-key'}]}
            if method == 'ListMyTools':
                return {'tools': [{'tool': {'name': name}, 'enabledByMe': enabled, 'effective': enabled} for name, enabled in state.items()]}
            if method == 'SetMyToolEnabled':
                state[body['tool']] = body['enabled']
                return {}
            raise AssertionError('Unexpected API method: ' + method)

        return state, methods, call

    def test_disables_new_defaults_and_preserves_existing_key(self):
        state, methods, call = self.client()
        module.reconcile(call, ['monitor_poll', 'monitor_ack'])
        self.assertEqual([name for name, enabled in state.items() if enabled], ['energy_search'])
        self.assertEqual([(method, body) for method, body in methods if method == 'SetMyToolEnabled'], [('SetMyToolEnabled', {'tool': 'monitor_poll', 'enabled': False}), ('SetMyToolEnabled', {'tool': 'monitor_ack', 'enabled': False})])
        self.assertEqual(sum(method == 'ListApiKeys' for method, _ in methods), 2)

    def test_refuses_before_migration_without_tool_mutation(self):
        _, methods, call = self.client()
        with self.assertRaisesRegex(RuntimeError, '^expected_tool_migration_not_visible$'):
            module.reconcile(call, ['not_migrated'])
        self.assertNotIn('SetMyToolEnabled', [method for method, _ in methods])

    def test_second_reconciliation_is_noop(self):
        _, methods, call = self.client()
        module.reconcile(call)
        methods.clear()
        module.reconcile(call)
        self.assertNotIn('SetMyToolEnabled', [method for method, _ in methods])


if __name__ == '__main__':
    unittest.main()
