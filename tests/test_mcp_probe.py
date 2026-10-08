import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location('mcp_probe', Path(__file__).parents[1] / 'scripts/mcp_probe.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def catalog():
    return {'structuredContent': {'available': True, 'results': [{'id': 'electricity/retail-sales', 'title': 'Electricity retail sales'}], 'source': {'name': 'EIA', 'attribution': 'Source: EIA.'}}}


class SemanticChecks(unittest.TestCase):
    def test_success_json_and_sse(self):
        expected = catalog()
        response = json.dumps({'jsonrpc': '2.0', 'id': 3, 'result': expected}).encode()
        self.assertEqual(probe.result(response, 'application/json; charset=utf-8', 3), expected)
        self.assertEqual(probe.result(b'event: message\r\ndata: ' + response + b'\r\n\r\n', 'text/event-stream', 3), expected)
        probe.validate_catalog(expected)
        probe.validate_catalog(expected | {'isError': False})

    def test_http200_rpc_errors_and_wrong_id_rejected(self):
        for value in [{'jsonrpc': '2.0', 'id': 3, 'error': {'message': 'sensitive'}}, {'jsonrpc': '2.0', 'id': 4, 'result': catalog()}, []]:
            with self.assertRaises(probe.ProbeFailure):
                probe.result(json.dumps(value).encode(), 'application/json', 3)

    def test_error_cannot_pass_with_success_content(self):
        for flag in [True, 'true', 'false', None, 0]:
            with self.assertRaises(probe.ProbeFailure):
                probe.validate_catalog(catalog() | {'isError': flag})

    def test_missing_or_unavailable_catalog_rejected(self):
        for change in [{'available': False}, {'available': 'true'}, {'results': []}, {'source': {}}, {'source': {'unexpected': True}}, {'source': {'name': 'EIA', 'attribution': ''}}, {'results': [{'id': 'other', 'title': 'x'}]}]:
            response = catalog()
            response['structuredContent'].update(change)
            with self.assertRaises(probe.ProbeFailure):
                probe.validate_catalog(response)

    def test_only_probe_tool_is_allowed(self):
        probe.validate_tools({'tools': [{'name': 'energy_search'}]})
        for response in [{'tools': []}, {'tools': [{'name': 'energy_search'}, {'name': 'monitor_create'}]}, {'tools': [{'name': 'energy_search'}], 'nextCursor': 'more'}]:
            with self.assertRaises(probe.ProbeFailure):
                probe.validate_tools(response)

    def test_html_and_invalid_json_rejected(self):
        for body, mime in [(b'<html>OK</html>', 'text/html'), (b'not json', 'application/json')]:
            with self.assertRaises(probe.ProbeFailure):
                probe.result(body, mime, 3)

    def test_transport_response_bound(self):
        response = Mock()
        response.status = 200
        response.headers = {'Content-Type': 'application/json'}
        response.read1.return_value = b'x' * 8192
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        client = probe.Client('disposable-test-only')
        client.opener = Mock()
        client.opener.open.return_value = response
        with self.assertRaisesRegex(probe.ProbeFailure, '^response_too_large$'):
            client.post('tools/list', {}, 1)
        self.assertEqual(client.opener.open.call_count, 1)
        self.assertLessEqual(response.read1.call_count, 17)

    def test_expired_deadline_does_not_send(self):
        client = probe.Client('disposable-test-only')
        client.deadline = 0
        client.opener = Mock()
        with self.assertRaisesRegex(probe.ProbeFailure, '^timeout$'):
            client.post('tools/list', {}, 1)
        client.opener.open.assert_not_called()

    def test_redirects_never_forward_credential(self):
        self.assertIsNone(probe.NoRedirect().redirect_request(None, None, 302, None, None, 'https://other.example'))


if __name__ == '__main__':
    unittest.main()
