import importlib
import logging
from pip._internal.operations import freeze

import fastapi

from .build_info import BUILD_INFO
from .config import AppConfig, Config
from .sentry import SentryRequestMiddleware
from . import schemas


log = logging.getLogger(__name__)


def _import(module_name: str, def_name: str):
    module = importlib.import_module(module_name)
    return getattr(module, def_name)


class EngineGateway(fastapi.FastAPI):

    async def __call__(self, scope, receive, send):
        # outside the middleware stack, which the Sentry integration wraps
        await SentryRequestMiddleware(super().__call__)(scope, receive, send)

    def _mount_from_app(self, config: AppConfig):
        if config.app is None:
            return
        try:
            app = _import(config.module, config.app)
            self.mount(config.path, app)
        except (ImportError, AttributeError) as e:
            log.error('Error importing "%s" from "%s": %s',
                      config.app, config.module, e)

    def _mount_from_factory(self, config: AppConfig):
        if config.factory is None:
            return
        try:
            factory = _import(config.module, config.factory)
            app = factory(**(config.kwargs or {}))
            self.mount(config.path, app)
        except (ImportError, AttributeError) as e:
            log.error('Error importing "%s" from "%s": %s',
                      config.app, config.module, e)

    def mount_gateway_app(self, config: AppConfig):
        if config.factory is not None:
            self._mount_from_factory(config)
        else:
            self._mount_from_app(config)


def create_info(config: Config) -> schemas.GatewayInfo:
    packages = list(freeze.freeze())
    return schemas.GatewayInfo(
        title=config.gateway.title,
        version=config.gateway.version,
        engine_gateway=schemas.EngineInfo(
            version=BUILD_INFO.version,
            built_at=BUILD_INFO.built_at,
        ),
        mounts=config.mounts,
        packages=packages,
    )
