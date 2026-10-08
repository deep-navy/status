#!/usr/bin/env python3
"""Bounded authenticated MCP catalog check; emits only fixed, non-sensitive outcomes."""
import json
import os
import time
import urllib.error
import urllib.request

ENDPOINT = 'https://mcp.deep.navy/mcp'
PROTOCOL = '2025-11-25'
MAX_BYTES = 128 * 1024
BUDGET_SECONDS = 15


class ProbeFailure(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def result(body, content_type, request_id):
    """Accept one JSON-RPC response, whether JSON or a finite SSE message stream."""
    try:
        text = body.decode('utf-8')
        if content_type.split(';')[0].strip() == 'text/event-stream':
            messages = []
            for event in text.replace('\r\n', '\n').split('\n\n'):
                data = '\n'.join(line[5:].lstrip(' ') for line in event.splitlines() if line.startswith('data:'))
                if data:
                    messages.append(json.loads(data))
        elif content_type.split(';')[0].strip() == 'application/json':
            messages = [json.loads(text)]
        else:
            raise ProbeFailure('unexpected_content_type')
        matching = [message for message in messages if isinstance(message, dict) and message.get('id') == request_id]
        if len(matching) != 1:
            raise ProbeFailure('invalid_rpc_response')
        response = matching[0]
        if response.get('jsonrpc') != '2.0' or 'error' in response or not isinstance(response.get('result'), dict):
            raise ProbeFailure('rpc_error')
        return response['result']
    except (UnicodeError, ValueError, TypeError):
        raise ProbeFailure('invalid_response') from None


def validate_tools(response):
    tools = response.get('tools')
    if not isinstance(tools, list) or len(tools) != 1 or not isinstance(tools[0], dict) or tools[0].get('name') != 'energy_search' or response.get('nextCursor'):
        raise ProbeFailure('credential_scope_mismatch')


def validate_catalog(response):
    if 'isError' in response and response['isError'] is not False:
        raise ProbeFailure('tool_error')
    structured = response.get('structuredContent')
    if not isinstance(structured, dict) or structured.get('available') is not True:
        raise ProbeFailure('catalog_unavailable')
    rows = structured.get('results')
    if not isinstance(rows, list) or not any(isinstance(row, dict) and row.get('id') == 'electricity/retail-sales' and isinstance(row.get('title'), str) and row['title'].strip() for row in rows):
        raise ProbeFailure('catalog_result_missing')
    source = structured.get('source')
    if not isinstance(source, dict) or any(not isinstance(source.get(field), str) or not source[field].strip() for field in ('name', 'attribution')):
        raise ProbeFailure('catalog_attribution_missing')


class Client:
    def __init__(self, key):
        self.key = key
        self.session = None
        self.deadline = time.monotonic() + BUDGET_SECONDS
        self.opener = urllib.request.build_opener(NoRedirect())

    def post(self, method, params=None, request_id=None):
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            raise ProbeFailure('timeout')
        message = {'jsonrpc': '2.0', 'method': method}
        if params is not None:
            message['params'] = params
        if request_id is not None:
            message['id'] = request_id
        headers = {'Authorization': 'Bearer ' + self.key, 'Content-Type': 'application/json', 'Accept': 'application/json, text/event-stream', 'MCP-Protocol-Version': PROTOCOL, 'User-Agent': 'deep.navy-status/1'}
        if self.session:
            headers['Mcp-Session-Id'] = self.session
        request = urllib.request.Request(ENDPOINT, json.dumps(message).encode(), headers, method='POST')
        try:
            with self.opener.open(request, timeout=min(5, remaining)) as response:
                if response.status not in (200, 202, 204):
                    raise ProbeFailure('http_error')
                self.session = response.headers.get('Mcp-Session-Id') or self.session
                body = bytearray()
                while True:
                    if time.monotonic() >= self.deadline:
                        raise ProbeFailure('timeout')
                    chunk = response.read1(min(8192, MAX_BYTES + 1 - len(body)))
                    if not chunk:
                        break
                    body.extend(chunk)
                    if len(body) > MAX_BYTES:
                        raise ProbeFailure('response_too_large')
                if request_id is None:
                    return None
                return result(body, response.headers.get('Content-Type', ''), request_id)
        except ProbeFailure:
            raise
        except (OSError, urllib.error.URLError, ValueError):
            raise ProbeFailure('transport_error') from None


def probe(key):
    client = Client(key)
    initialized = client.post('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {}, 'clientInfo': {'name': 'deep.navy-status', 'version': '1'}}, 1)
    if initialized.get('protocolVersion') != PROTOCOL:
        raise ProbeFailure('protocol_mismatch')
    client.post('notifications/initialized')
    validate_tools(client.post('tools/list', {}, 2))
    validate_catalog(client.post('tools/call', {'name': 'energy_search', 'arguments': {'query': 'electricity'}}, 3))


def main():
    key = os.environ.get('DEEPNAVY_STATUS_KEY', '')
    if not key or key.strip() != key or any(ord(c) < 33 or ord(c) > 126 for c in key):
        print('FAIL credential_missing_or_invalid')
        return 1
    try:
        probe(key)
    except ProbeFailure as error:
        print('FAIL ' + str(error))  # Only locally defined reason codes, never response content.
        return 1
    except Exception:
        print('FAIL unexpected_probe_error')
        return 1
    print('PASS authenticated_mcp_catalog')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
