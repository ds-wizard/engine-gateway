import fastapi

from .build_info import BuildInfo
from .config import Config
from .logic import EngineGateway, create_info
from .sentry import init_sentry


def create_app(config: Config | None = None) -> EngineGateway:
    if config is None:
        config = Config()
        config.load_yaml()
        config.load_env()

    init_sentry(config)

    app = EngineGateway(
        title=config.gateway.title,
        version=BuildInfo.version,
        root_path=config.gateway.root_path.rstrip('/'),
    )

    if config.gateway.info_enabled:
        def get_info(request: fastapi.Request):
            token = config.gateway.info_token
            if token:
                auth_header = request.headers.get('Authorization')
                if auth_header != f'Bearer {token}':
                    raise fastapi.HTTPException(status_code=401, detail='Unauthorized')
            return create_info(config)

        app.add_api_route(
            '/info',
            endpoint=get_info,
            methods=['GET'],
        )

    for app_config in config.mounts:
        app.mount_gateway_app(app_config)

    return app
