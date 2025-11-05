import logging
import os
import pathlib

import pydantic
import yaml

from .consts import DEFAULT_ENCODING


CONFIG_FILE_NAME = os.environ.get('CONFIG_FILE')
CONFIG_FILE = pathlib.Path.cwd() / 'config.yaml'
if CONFIG_FILE_NAME:
    CONFIG_FILE = pathlib.Path(CONFIG_FILE_NAME)

log = logging.getLogger(__name__)


def _is_true(value: str) -> bool:
    return value.lower() in ('1', 'true', 'yes', 'on')


class AppConfig(pydantic.BaseModel):
    path: str
    module: str
    app: str | None
    factory: str | None
    kwargs: dict | None


class SentryConfig(pydantic.BaseModel):
    dsn: str | None
    traces_sample_rate: float | None
    profiles_sample_rate: float | None
    max_breadcrumbs: int | None
    environment: str | None
    tags: dict[str, str]
    aws_lambda: bool = False


class GatewayConfig(pydantic.BaseModel):
    title: str
    root_path: str
    info_enabled: bool
    info_token: str | None


class Config:

    def __init__(self):
        self.gateway: GatewayConfig = GatewayConfig(
            title='Engine Gateway',
            root_path='',
            info_enabled=False,
            info_token=None,
        )
        self.sentry: SentryConfig = SentryConfig(
            dsn=None,
            traces_sample_rate=None,
            profiles_sample_rate=None,
            max_breadcrumbs=None,
            environment=None,
            aws_lambda=False,
            tags={},
        )
        self.mounts: list[AppConfig] = []

    def load_yaml(self):
        if not CONFIG_FILE.exists():
            log.warning('Config file %s does not exist; skipping YAML loading.',
                        CONFIG_FILE)
            return
        with open(CONFIG_FILE, 'r', encoding=DEFAULT_ENCODING) as f:
            data = yaml.safe_load(f)

        mounts_data = data.get('mounts', {})
        for path, details in mounts_data.items():
            app_config = AppConfig(
                path=path,
                module=details.get('module'),
                app=details.get('app'),
                factory=details.get('factory'),
                kwargs=details.get('kwargs', {})
            )
            self.mounts.append(app_config)
        self._load_yaml_gateway(data)
        self._load_yaml_sentry(data)

    def _load_yaml_gateway(self, data: dict):
        gateway_data = data.get('gateway', {})
        if 'title' in gateway_data:
            self.gateway.title = gateway_data['title']
        if 'root_path' in gateway_data:
            self.gateway.root_path = gateway_data['root_path']
        info_data = gateway_data.get('info', None)
        if info_data is not None:
            self.gateway.info_enabled = info_data.get('enabled', True)
            self.gateway.info_token = info_data.get('token', None)

    def _load_yaml_sentry(self, data: dict):
        sentry_data = data.get('sentry', None)
        if sentry_data is not None:
            if 'dsn' in sentry_data:
                self.sentry.dsn = sentry_data['dsn']
            if 'traces_sample_rate' in sentry_data:
                self.sentry.traces_sample_rate = float(sentry_data['traces_sample_rate'])
            if 'profiles_sample_rate' in sentry_data:
                self.sentry.profiles_sample_rate = float(sentry_data['profiles_sample_rate'])
            if 'max_breadcrumbs' in sentry_data:
                self.sentry.max_breadcrumbs = int(sentry_data['max_breadcrumbs'])
            if 'environment' in sentry_data:
                self.sentry.environment = sentry_data['environment']
            if 'tags' in sentry_data:
                self.sentry.tags = sentry_data['tags']
            if 'aws_lambda' in sentry_data:
                self.sentry.aws_lambda = bool(sentry_data['aws_lambda'])

    def load_env(self):
        if 'GATEWAY_TITLE' in os.environ:
            self.gateway.title = os.getenv('GATEWAY_TITLE', 'Engine Gateway')
        if 'GATEWAY_ROOT_PATH' in os.environ:
            self.gateway.root_path = os.getenv('GATEWAY_ROOT_PATH', '')
        if 'GATEWAY_INFO_ENABLED' in os.environ:
            self.gateway.info_enabled = _is_true(os.getenv('GATEWAY_INFO_ENABLED', 'false'))
        if 'GATEWAY_INFO_TOKEN' in os.environ:
            self.gateway.info_token = os.getenv('GATEWAY_INFO_TOKEN')

        if 'SENTRY_DSN' in os.environ:
            self.sentry.dsn = os.getenv('SENTRY_DSN')
        if 'SENTRY_TRACES_SAMPLE_RATE' in os.environ:
            self.sentry.traces_sample_rate = float(os.getenv('SENTRY_TRACES_SAMPLE_RATE', '1.0'))
        if 'SENTRY_PROFILES_SAMPLE_RATE' in os.environ:
            self.sentry.profiles_sample_rate = float(os.getenv('SENTRY_PROFILES_SAMPLE_RATE', '1.0'))
        if 'SENTRY_MAX_BREADCRUMBS' in os.environ:
            self.sentry.max_breadcrumbs = int(os.getenv('SENTRY_MAX_BREADCRUMBS', '100'))
        if 'SENTRY_ENVIRONMENT' in os.environ:
            self.sentry.environment = os.getenv('SENTRY_ENVIRONMENT')
        if 'SENTRY_AWS_LAMBDA' in os.environ:
            self.sentry.aws_lambda = _is_true(os.getenv('SENTRY_AWS_LAMBDA', 'false'))
