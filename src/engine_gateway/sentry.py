import logging

import sentry_sdk

from .build_info import BuildInfo
from .config import Config

log = logging.getLogger(__name__)


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
            release=BuildInfo.version,
            environment=config.sentry.environment,
            integrations=integrations,
        )
        for key, value in config.sentry.tags.items():
            sentry_sdk.set_tag(key, value)
        log.info('Sentry initialized successfully.')
    except Exception as e:
        log.error('Failed to initialize Sentry: %s',
                  e, exc_info=e)
