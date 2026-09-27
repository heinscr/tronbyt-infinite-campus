"""Exercise the native app's Python-compatible logic with mocked Pixlet modules."""
import builtins
import json
from pathlib import Path
from types import SimpleNamespace
import unittest


def config():
    return {'username': 'test', 'password': 'example&with#symbols',
            'campus_url': 'https://school.example/campus/', 'app_name': 'district',
            'timezone': 'UTC'}


class Cache:
    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value, ttl_seconds=60):
        self.values[key] = value


class Response:
    def __init__(self, data=None, headers=None):
        self.status_code = 200
        self.data = data
        self.headers = headers or {}

    def body(self):
        return json.dumps(self.data)

    def json(self):
        # This matches Pixlet's numeric decoding and catches the personID regression.
        return json.loads(self.body(), parse_int=float)


class HTTP:
    def __init__(self, placements):
        self.placements = placements
        self.logins = 0
        self.roster_params = None

    def post(self, url, **kwargs):
        self.logins += 1
        assert kwargs['params']['nonBrowser'] == 'true'
        assert 'password' not in url
        return Response(headers={'Set-Cookie': 'JSESSIONID=fake; Path=/campus,tomcat-cookie=test; Path=/'})

    def get(self, url, params, **kwargs):
        if url.endswith('/students'):
            return Response([{'personID': 12345, 'firstName': 'Test'}])
        self.roster_params = params
        assert params['personID'] == '12345', 'Student ID must not include .0'
        return Response([{'sectionID': 99, 'courseName': 'Math', 'sectionPlacements': self.placements}])


def placement(**changes):
    result = {'instructionalDay': True, 'startDate': '2026-08-31', 'endDate': '2026-11-06',
              'startTime': '08:00:00', 'endTime': '08:45:00', 'periodName': '1', 'roomName': '101'}
    result.update(changes)
    return result


def load_app(placements):
    http = HTTP(placements)
    env = {'http': http, 'cache': Cache(),
           'json': SimpleNamespace(encode=json.dumps, decode=json.loads),
           'type': lambda obj: builtins.type(obj).__name__}
    source = Path('tronbyt/family_schedule.star').read_text()
    source = '\n'.join(line for line in source.splitlines() if not line.startswith('load('))
    exec(compile(source, 'family_schedule.star', 'exec'), env)
    return env, http


class NativeScheduleTests(unittest.TestCase):
    def test_integer_id_date_and_duplicate_filter(self):
        env, http = load_app([placement(), placement(), placement(instructionalDay=False),
                              placement(startDate='2027-01-01'), placement(endDate='2026-09-01')])
        settings = config()
        result = env['fetch_day'](settings, '2026-09-28')
        self.assertEqual(len(result[0]['classes']), 1)
        self.assertEqual(result[0]['classes'][0]['period'], '1')
        self.assertEqual(http.roster_params['_date'], '2026-09-28')
        self.assertEqual(result, env['fetch_day'](settings, '2026-09-28'))
        self.assertEqual(http.logins, 1)

    def test_non_school_day(self):
        env, _ = load_app([placement(instructionalDay=False)])
        result = env['fetch_day'](config(), '2026-09-27')
        self.assertEqual(result[0]['classes'], [])

    def test_full_day_not_only_current_and_next(self):
        env, _ = load_app([])
        calls = []
        env['time'] = SimpleNamespace(now=lambda: SimpleNamespace(in_location=lambda tz:
            SimpleNamespace(format=lambda f: {'2006-01-02': '2026-09-28', '15:04:05':'09:00:00',
                                             'Mon':'Mon'}[f])))
        env['fetch_day'] = lambda config, day: [{'name':'Test','classes':[
            {'start':'08:00:00','end':'08:45:00','course':'Past'},
            {'start':'09:00:00','end':'09:45:00','course':'Current'},
            {'start':'10:00:00','end':'10:45:00','course':'Future'}]}]
        env['day_page'] = lambda *args: calls.append(args) or args
        env['render'] = SimpleNamespace(Animation=lambda **kw: kw, Root=lambda **kw: kw)
        env['main'](config())
        self.assertEqual(len(calls), 1)
        self.assertEqual([c['course'] for c in calls[0][2]], ['Past','Current','Future'])
        self.assertEqual(calls[0][1], 'Mon')

    def test_cache_isolated_between_districts(self):
        env, http = load_app([placement()])
        first = config()
        second = dict(first, campus_url='https://another.example/campus/')
        env['fetch_day'](first, '2026-09-28')
        env['fetch_day'](second, '2026-09-28')
        self.assertEqual(http.logins, 2)

    def test_credentials_not_sent_to_http(self):
        env, http = load_app([])
        result = env['fetch_day'](dict(config(), campus_url='http://school.example/campus/'), '2026-09-28')
        self.assertIn('error', result)
        self.assertEqual(http.logins, 0)


if __name__ == '__main__':
    unittest.main()
