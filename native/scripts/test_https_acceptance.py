"""Synthetic acceptance failures must never become signing approval."""
import io
import json
import unittest
from email.message import Message
from unittest.mock import patch
from https_acceptance import probe, validate_root, NoRedirect


class Response(io.BytesIO):
    def __init__(self, status, body, content_type='application/json'):
        super().__init__(body)
        self.code = status
        self.headers = Message()
        self.headers['Content-Type'] = content_type


class AcceptanceTest(unittest.TestCase):
    def run_probe(self, health):
        responses = [health] + [Response(code, b'{"error":"denied"}') for code in (401,403,403)]
        with patch('https_acceptance.urllib.request.build_opener') as factory:
            factory.return_value.open.side_effect = responses
            return probe('https://example.com')

    def test_healthy_api(self):
        result = self.run_probe(Response(200, b'{"status":"ok","version":"0.17.1"}'))
        self.assertTrue(result['passed'])
        self.assertFalse(result['productionReady'])
        self.assertFalse(result['phoneNetworkVerified'])

    def test_html_interstitial_rejected(self):
        self.assertFalse(self.run_probe(Response(200, b'<html>continue</html>', 'text/html'))['passed'])

    def test_oversized_or_wrong_service_rejected(self):
        for body in [b' ' * 16385, b'{"status":"ok","version":"other"}']:
            self.assertFalse(self.run_probe(Response(200, body))['passed'])

    def test_redirect_not_followed(self):
        self.assertIsNone(NoRedirect().redirect_request(None,None,302,'',{},'https://other.example'))
        self.assertFalse(self.run_probe(Response(302,b'{}'))['passed'])

    def test_root_constraints(self):
        for root in ['http://example.com','https://user:secret@example.com',
                     'https://example.com/path','https://example.com?key=secret',
                     'https://example.com:8443','http://127.0.0.1:4317']:
            with self.assertRaises(ValueError): validate_root(root)
        self.assertEqual(validate_root('http://127.0.0.1:4318',True),'http://127.0.0.1:4318')


if __name__ == '__main__':
    unittest.main()
