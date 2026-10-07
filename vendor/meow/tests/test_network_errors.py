import asyncio
import json
from pathlib import Path
import socket
import ssl
import sys
import unittest
from unittest.mock import patch

import httpx

WORK = next(p for p in Path(__file__).resolve().parents if (p / 'gpt56_vnext').is_dir())
sys.path[:0] = [str(WORK), str(WORK / 'meow-web')]
from gpt56_vnext.transport import AsyncTransport
from gpt56_vnext.errors import RequestError, network_failure
from gpt56_vnext.security import SecretGuard
try:
    from meow_web.network import Transport, public_socket
    from meow_web.errors import RequestError as WebError
except ModuleNotFoundError:
    Transport = None  # Standalone desktop distribution has no public website runtime.
SIDES = ('desktop','website') if Transport else ('desktop',)

KEY = 'synthetic-network-secret-321'
BASE = 'https://api.example.com/v1'


def failure(code):
    return {'dns_error': socket.gaierror(-2, 'DNS failed ' + KEY),
            'tls_error': ssl.SSLCertVerificationError(1, 'certificate verification failed ' + KEY),
            'request_timeout': TimeoutError('read timed out'),
            'response_decode_error': UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'invalid start byte'),
            'connection_error': ConnectionRefusedError(10061, 'connection refused')}[code]


class WebResponse:
    status = 200
    headers = {}
    def __init__(self, error):
        self.error = error
    async def __aenter__(self):
        raise self.error
    async def __aexit__(self, *args):
        pass


class WebClient:
    def __init__(self, error):
        self.error = error
    def post(self, *args, **kwargs):
        return WebResponse(self.error)
    get = post
    async def close(self):
        pass


class NetworkErrorTests(unittest.IsolatedAsyncioTestCase):
    async def test_received_http_status_survives_body_and_parse_failures(self):
        class BodyResponse:
            headers = {}
            def __init__(self, status, body):
                self.status, self.body, self.content = status, body, self
            async def __aenter__(self):
                return self
            async def __aexit__(self, *args):
                pass
            async def iter_chunked(self, size):
                yield self.body

        class BodyClient:
            def __init__(self, status, body):
                self.response = BodyResponse(status, body)
            def post(self, *args, **kwargs):
                return self.response
            get = post
            async def close(self):
                pass

        for status in (200, 400, 503):
            for side in SIDES:
                for operation in ('request', 'models'):
                    with self.subTest(status=status, side=side, operation=operation):
                        if side == 'desktop':
                            client = AsyncTransport()
                            client._clients[BASE] = httpx.AsyncClient(transport=httpx.MockTransport(
                                lambda request: httpx.Response(status, content=b'failure: \xff')))
                            error_type = RequestError
                        else:
                            client = Transport()
                            await client.close()
                            client.client = BodyClient(status, b'failure: \xff')
                            error_type = WebError
                        try:
                            with self.assertRaises(error_type) as got:
                                if operation == 'models':
                                    await client.models(BASE, KEY)
                                elif side == 'website':
                                    await client.request('gpt', BASE, KEY, 'fixture', {'prompt': 'choose'}, lambda: None)
                                else:
                                    await client.request('gpt', BASE, KEY, 'fixture', {'prompt': 'choose'})
                            public = got.exception.public()
                            self.assertEqual(public['http_status'], status)
                            self.assertEqual(public['code'], 'response_decode_error' if status == 200 else 'upstream_http_error')
                            self.assertIn('local' if status == 200 else 'upstream', public)
                            self.assertTrue(public['retryable'])
                        finally:
                            await client.close()

    async def test_timeout_keeps_timeout_cause_not_internal_cancellation(self):
        try:
            async with asyncio.timeout(.001):
                await asyncio.sleep(1)
        except TimeoutError as exc:
            public = network_failure(exc, SecretGuard()).public()
        self.assertEqual(public['local']['type'], 'TimeoutError')

    @unittest.skipUnless(Transport, 'Website socket boundary is tested in the website suite')
    async def test_public_address_rejection_is_separate_and_does_not_open_socket(self):
        with patch('meow_web.network.socket.socket') as connect:
            try:
                public_socket((socket.AF_INET, socket.SOCK_STREAM, 6, '', ('127.0.0.1', 443)))
            except OSError as exc:
                from meow_web.errors import network_failure as web_failure
                from meow_web.security import SecretGuard as WebGuard
                public = web_failure(exc, WebGuard()).public()
        self.assertEqual(public['code'], 'unsafe_destination')
        self.assertFalse(public['retryable'])
        self.assertIsNone(public['http_status'])
        connect.assert_not_called()

    async def test_request_and_models_share_reason_classification(self):
        for code in ('dns_error', 'tls_error', 'request_timeout', 'response_decode_error', 'connection_error'):
            for side in SIDES:
                for operation in ('request', 'models'):
                    with self.subTest(code=code, side=side, operation=operation):
                        exc = failure(code)
                        if side == 'desktop':
                            client = AsyncTransport()
                            async def fail(request):
                                if code in ('dns_error', 'tls_error'):
                                    raise httpx.ConnectError('connection failed') from exc
                                raise exc
                            client._clients[BASE] = httpx.AsyncClient(transport=httpx.MockTransport(fail))
                            error_type = RequestError
                        else:
                            client = Transport()
                            await client.close()
                            client.client = WebClient(exc)
                            error_type = WebError
                        try:
                            with self.assertRaises(error_type) as got:
                                if operation == 'models':
                                    await client.models(BASE, KEY)
                                elif side == 'website':
                                    await client.request('gpt', BASE, KEY, 'fixture', {'prompt': 'choose'}, lambda: None)
                                else:
                                    await client.request('gpt', BASE, KEY, 'fixture', {'prompt': 'choose'})
                            public = got.exception.public()
                            self.assertEqual(public['code'], code)
                            self.assertIsNone(public['http_status'])
                            self.assertNotIn('upstream', public)
                            self.assertIn('local', public)
                            self.assertNotIn(KEY, json.dumps(public))
                        finally:
                            await client.close()


if __name__ == '__main__':
    unittest.main()
