import base64
import binascii
import json
import logging
import typing
import uuid

import sentry_sdk

from .build_info import BUILD_INFO
from .config import Config

if typing.TYPE_CHECKING:
    from sentry_sdk.types import Event, Hint
    from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)

TRACE_UUID_HEADER = b'x-trace-uuid'
SENTRY_TRACE_HEADER = b'sentry-trace'


def init_sentry(config: Config) -> None:
    if not config.sentry.dsn:
        log.info('Sentry DSN not provided; skipping Sentry initialization.')
        return

    try:
        integrations = []
        if config.sentry.aws_lambda:
            # pylint: disable-next=import-outside-toplevel
            from sentry_sdk.integrations.aws_lambda import AwsLambdaIntegration
            integrations.append(AwsLambdaIntegration())
        sentry_sdk.init(
            dsn=config.sentry.dsn,
            traces_sample_rate=float(config.sentry.traces_sample_rate or 1.0),
            profiles_sample_rate=float(config.sentry.profiles_sample_rate or 1.0),
            max_breadcrumbs=int(config.sentry.max_breadcrumbs or sentry_sdk.consts.DEFAULT_MAX_BREADCRUMBS),
            release=config.sentry.release or BUILD_INFO.version,
            environment=config.sentry.environment,
            integrations=integrations,
        )
        scope = sentry_sdk.get_global_scope()
        scope.set_tag('component', config.sentry.component)
        for key, value in config.sentry.tags.items():
            scope.set_tag(key, value)
        log.info('Sentry initialized successfully.')
    except Exception as e:
        log.error('Failed to initialize Sentry: %s',
                  e, exc_info=e)


def normalize_path(path: str) -> str:
    """Mask UUID path segments as `:uuid`, like `normalizePath` in the backend."""
    return '/'.join(
        ':uuid' if _to_trace_id(segment) is not None else segment
        for segment in path.split('/')
    )


def get_route(scope: 'Scope') -> str:
    """Template of the matched route (with root path and mounts), or the masked path if none matched."""
    route_path = getattr(scope.get('route'), 'path', None)
    if isinstance(route_path, str):
        return normalize_path(scope.get('root_path', '') + route_path)
    return normalize_path(scope.get('path', ''))


def _to_trace_id(value: str) -> str | None:
    # only the canonical 36-character form, like `Data.UUID.fromString`
    if len(value) != 36:
        return None
    try:
        return uuid.UUID(value).hex
    except ValueError:
        return None


def _get_header(scope: 'Scope', name: bytes) -> str | None:
    for key, value in scope.get('headers', []):
        if key.lower() == name:
            return value.decode('latin-1')
    return None


def _decode_jwt_claims(authorization: str | None) -> dict:
    """Read the claims of a bearer JWT without verifying it, only to tag Sentry events."""
    if not authorization or not authorization.startswith('Bearer '):
        return {}
    parts = authorization.removeprefix('Bearer ').strip().split('.')
    if len(parts) != 3:
        return {}
    payload = parts[1] + '=' * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, ValueError):
        return {}
    return claims if isinstance(claims, dict) else {}


def _make_event_processor(scope: 'Scope'):
    method = scope.get('method', '').upper()

    def event_processor(event: 'Event', hint: 'Hint') -> 'Event':
        # routing has filled in the matched route by the time an event is captured
        route = get_route(scope)
        event.setdefault('tags', {})
        event['tags']['method'] = method
        event['tags']['route'] = route
        exc_info = hint.get('exc_info')
        if exc_info and exc_info[0] is not None:
            event['fingerprint'] = [method, route, exc_info[0].__name__]
        return event

    return event_processor


class SentryRequestMiddleware:
    """Tag Sentry events with the request the way the backend does.

    It must wrap the whole gateway, outside the Sentry Starlette integration,
    so that the isolation scope it forks per request is inherited by the scope
    in which unhandled exceptions are captured.
    """

    def __init__(self, app: 'ASGIApp'):
        self.app = app

    async def __call__(self, scope: 'Scope', receive: 'Receive', send: 'Send') -> None:
        if scope['type'] != 'http' or not sentry_sdk.get_client().is_active():
            await self.app(scope, receive, send)
            return

        with sentry_sdk.isolation_scope() as sentry_scope:
            claims = _decode_jwt_claims(_get_header(scope, b'authorization'))
            user_uuid = claims.get('userUuid') or claims.get('sub')
            if isinstance(user_uuid, str):
                sentry_scope.set_user({'id': user_uuid})
            tenant_uuid = claims.get('tenantUuid')
            if isinstance(tenant_uuid, str):
                sentry_scope.set_tag('tenantUuid', tenant_uuid)

            trace_uuid = _get_header(scope, TRACE_UUID_HEADER)
            if trace_uuid:
                sentry_scope.set_tag('traceUuid', trace_uuid)
                trace_id = _to_trace_id(trace_uuid)
                if trace_id is not None and _get_header(scope, SENTRY_TRACE_HEADER) is None:
                    sentry_trace = f'{trace_id}-{trace_id[:16]}'
                    sentry_scope.continue_trace({'sentry-trace': sentry_trace})
                    # the Sentry ASGI middleware starts its transaction from the request headers
                    scope = dict(scope)
                    scope['headers'] = [*scope.get('headers', []),
                                        (SENTRY_TRACE_HEADER, sentry_trace.encode('latin-1'))]

            sentry_scope.add_event_processor(_make_event_processor(scope))
            await self.app(scope, receive, send)
