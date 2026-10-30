import base64
import json

import pytest
import sentry_sdk
from fastapi.testclient import TestClient
from sentry_sdk.transport import Transport

from engine_gateway import create_app
from engine_gateway import sentry as gateway_sentry
from engine_gateway.build_info import BUILD_INFO
from engine_gateway.config import AppConfig, Config
from engine_gateway.sentry import get_route, normalize_path

PLUGIN_UUID = '55f16aea-5a53-4adb-a8a1-8d72109cb50d'
PROJECT_UUID = 'a6b7c8d9-0e1f-4a2b-8c3d-4e5f6a7b8c9d'
TRACE_UUID = '8a7d1f0e-3b2c-4d5e-9f60-7182a3b4c5d6'
USER_UUID = 'c1d2e3f4-a5b6-4c7d-8e9f-0a1b2c3d4e5f'
TENANT_UUID = '00000000-0000-0000-0000-000000000000'
FAIL_PATH = f'/gateway/plugins/{PLUGIN_UUID}/projects/{PROJECT_UUID}/fail'
FAIL_ROUTE = '/gateway/plugins/:uuid/projects/{project_uuid}/fail'


def make_jwt(claims: dict) -> str:
    def encode(data: dict) -> str:
        return base64.urlsafe_b64encode(json.dumps(data).encode()).rstrip(b'=').decode()
    return f'{encode({"alg": "RS256"})}.{encode(claims)}.signature'


def make_config(*, dsn: str | None = 'https://token@sentry.example.org/1') -> Config:
    config = Config()
    config.gateway.root_path = '/gateway'
    config.sentry.dsn = dsn
    config.sentry.tags = {'foo': 'bar'}
    config.mounts.append(AppConfig(
        path=f'/plugins/{PLUGIN_UUID}',
        module='fake_app',
        app=None,
        factory='create_app',
        kwargs={},
    ))
    return config


class NullTransport(Transport):

    def capture_envelope(self, envelope):
        pass


@pytest.fixture
def captured(monkeypatch):
    events = []
    sentry_init = sentry_sdk.init

    def capture(event, _hint):
        events.append(event)
        return None

    def init(**kwargs):
        return sentry_init(
            **kwargs,
            before_send=capture,
            before_send_transaction=lambda event, hint: None,
            transport=NullTransport(),
        )

    monkeypatch.setattr(gateway_sentry.sentry_sdk, 'init', init)
    yield events
    sentry_sdk.get_global_scope().clear()
    sentry_sdk.get_isolation_scope().clear()
    sentry_sdk.get_client().close()


def get_client(config: Config) -> TestClient:
    return TestClient(create_app(config), raise_server_exceptions=False)


def test_defaults():
    config = Config()
    assert config.sentry.environment == 'development'
    assert config.sentry.component == 'gateway'
    assert config.sentry.release is None


def test_load_env(monkeypatch):
    monkeypatch.setenv('SENTRY_ENVIRONMENT', 'production')
    monkeypatch.setenv('SENTRY_RELEASE', 'v4.34.0~abc1234')
    monkeypatch.setenv('SENTRY_COMPONENT', 'lambda_gateway')
    config = Config()
    config.load_env()
    assert config.sentry.environment == 'production'
    assert config.sentry.release == 'v4.34.0~abc1234'
    assert config.sentry.component == 'lambda_gateway'


def test_load_yaml(monkeypatch, tmp_path):
    config_file = tmp_path / 'config.yaml'
    config_file.write_text('sentry:\n  release: v4.34.0~abc1234\n  component: lambda_gateway\n')
    monkeypatch.setattr('engine_gateway.config.CONFIG_FILE', config_file)
    config = Config()
    config.load_yaml()
    assert config.sentry.environment == 'development'
    assert config.sentry.release == 'v4.34.0~abc1234'
    assert config.sentry.component == 'lambda_gateway'


@pytest.mark.parametrize('path,expected', [
    ('/', '/'),
    (f'/plugins/{PLUGIN_UUID}/info', '/plugins/:uuid/info'),
    (f'/a/{PROJECT_UUID}/{PROJECT_UUID}', '/a/:uuid/:uuid'),
    (f'/a/{PROJECT_UUID.replace("-", "")}', f'/a/{PROJECT_UUID.replace("-", "")}'),
    ('/a/not-a-uuid', '/a/not-a-uuid'),
])
def test_normalize_path(path, expected):
    assert normalize_path(path) == expected


def test_get_route_without_match():
    assert get_route({'path': f'/gateway/unknown/{PROJECT_UUID}'}) == '/gateway/unknown/:uuid'


def test_default_release_and_environment(captured):
    sentry_sdk.capture_message('nothing')
    assert not captured

    get_client(make_config()).get('/gateway/info')
    sentry_sdk.capture_message('failed')

    event = captured[-1]
    assert event['release'] == BUILD_INFO.version
    assert event['environment'] == 'development'
    assert event['tags'] == {'component': 'gateway', 'foo': 'bar'}


def test_release_and_component_override(captured):
    config = make_config()
    config.sentry.release = 'v4.34.0~abc1234'
    config.sentry.environment = 'staging'
    config.sentry.component = 'lambda_gateway'
    get_client(config)
    sentry_sdk.capture_message('failed')

    event = captured[-1]
    assert event['release'] == 'v4.34.0~abc1234'
    assert event['environment'] == 'staging'
    assert event['tags']['component'] == 'lambda_gateway'


@pytest.mark.parametrize('traces_sample_rate', [1.0, 1e-9])
def test_request_event_matches_backend(captured, traces_sample_rate):
    config = make_config()
    config.sentry.traces_sample_rate = traces_sample_rate
    client = get_client(config)
    response = client.get(FAIL_PATH, headers={
        'Authorization': f'Bearer {make_jwt({"userUuid": USER_UUID, "tenantUuid": TENANT_UUID})}',
        'X-Trace-Uuid': TRACE_UUID,
    })
    assert response.status_code == 500

    event = captured[-1]
    assert event['tags'] == {
        'component': 'gateway',
        'foo': 'bar',
        'method': 'GET',
        'route': FAIL_ROUTE,
        'traceUuid': TRACE_UUID,
        'tenantUuid': TENANT_UUID,
    }
    assert event['user'] == {'id': USER_UUID}
    assert event['fingerprint'] == ['GET', FAIL_ROUTE, 'RuntimeError']
    assert event['contexts']['trace']['trace_id'] == TRACE_UUID.replace('-', '')


def test_user_from_sub_claim(captured):
    client = get_client(make_config())
    client.get(FAIL_PATH, headers={'Authorization': f'Bearer {make_jwt({"sub": USER_UUID})}'})

    event = captured[-1]
    assert event['user'] == {'id': USER_UUID}
    assert 'tenantUuid' not in event['tags']


@pytest.mark.parametrize('authorization', [
    'Bearer not-a-jwt',
    'Bearer a.!!!.c',
    f'Bearer {make_jwt({"userUuid": 42})}',
    f'Basic {USER_UUID}',
])
def test_invalid_authorization_is_ignored(captured, authorization):
    client = get_client(make_config())
    response = client.get(FAIL_PATH, headers={'Authorization': authorization})
    assert response.status_code == 500

    event = captured[-1]
    assert 'user' not in event or event['user'].get('id') is None
    assert event['tags']['route'] == FAIL_ROUTE


def test_invalid_trace_uuid_is_tagged_only(captured):
    client = get_client(make_config())
    client.get(FAIL_PATH, headers={'X-Trace-Uuid': 'not-a-uuid'})

    event = captured[-1]
    assert event['tags']['traceUuid'] == 'not-a-uuid'
    assert len(event['contexts']['trace']['trace_id']) == 32


def test_request_scope_does_not_leak(captured):
    client = get_client(make_config())
    client.get(FAIL_PATH, headers={
        'Authorization': f'Bearer {make_jwt({"userUuid": USER_UUID, "tenantUuid": TENANT_UUID})}',
        'X-Trace-Uuid': TRACE_UUID,
    })
    client.get(f'/gateway/plugins/{PLUGIN_UUID}/projects/x/fail')
    sentry_sdk.capture_message('outside of request')

    request_event, outside_event = captured[-2:]
    assert request_event['tags'] == {
        'component': 'gateway',
        'foo': 'bar',
        'method': 'GET',
        'route': FAIL_ROUTE,
    }
    assert 'user' not in request_event
    assert request_event['contexts']['trace']['trace_id'] != TRACE_UUID.replace('-', '')
    assert outside_event['tags'] == {'component': 'gateway', 'foo': 'bar'}
    assert 'user' not in outside_event


def test_without_sentry():
    client = get_client(make_config(dsn=None))
    assert client.get(f'/gateway/plugins/{PLUGIN_UUID}/ok').json() == {'ok': True}
    assert client.get(FAIL_PATH).status_code == 500
