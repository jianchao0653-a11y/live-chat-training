"""Read-only API boundary probe. No credentials, redirects or paid model calls."""
import argparse
import json
import urllib.error
import urllib.request
from urllib.parse import urlsplit


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def validate_root(root, local=False):
    u = urlsplit(root)
    if (not u.hostname or u.username or u.password or u.query or u.fragment
            or u.path not in ('', '/') or u.port not in (None, 443)):
        if not (local and root == 'http://127.0.0.1:4318'):
            raise ValueError('Expected an HTTPS service root on port 443')
    if u.scheme != 'https' and not (local and root == 'http://127.0.0.1:4318'):
        raise ValueError('HTTPS required; local check only permits loopback:4318')
    return root.rstrip('/')


def probe(root, local=False):
    root = validate_root(root, local)
    opener = urllib.request.build_opener(NoRedirect(), urllib.request.ProxyHandler({}))
    cases = [('/api/native/health', 200), ('/api/native/library/people', 401),
             ('/', 403), ('/api/people', 403)]
    checks = []
    for path, expected in cases:
        result = {'path': path, 'expected': expected, 'passed': False}
        try:
            req = urllib.request.Request(root + path, headers={
                'Accept': 'application/json', 'User-Agent': 'ConversationLens-Acceptance/0.16'})
            try:
                response = opener.open(req, timeout=10)
            except urllib.error.HTTPError as error:
                response = error
            with response:
                result['status'] = response.code
                data = response.read(16385)
                is_json = response.headers.get_content_type() == 'application/json'
            payload = json.loads(data) if len(data) <= 16384 and is_json else None
            result['passed'] = (result['status'] == expected and isinstance(payload, dict)
                                and (expected != 200 or (payload.get('status') == 'ok'
                                     and payload.get('version') == '0.17.1')))
        except Exception as error:
            # Never print response content, request headers or exception URLs.
            result['error'] = type(error).__name__
        checks.append(result)
    return {'root': root, 'scope': 'local' if local else 'public-https',
            'passed': all(c['passed'] for c in checks), 'checks': checks,
            'phoneNetworkVerified': False, 'productionReady': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root')
    parser.add_argument('--local', action='store_true')
    args = parser.parse_args()
    try:
        result = probe(args.root, args.local)
    except ValueError:
        parser.error('Supply an HTTPS service root, or --local http://127.0.0.1:4318')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
