import os

from .utils.logging import app_logger


def init_sentry(settings) -> None:
    if not settings.SENTRY_DSN:
        app_logger.info("Sentry disabled: SENTRY_DSN is not configured")
        return

    # Avoid eventlet greendns import issues present in this environment.
    os.environ.setdefault("EVENTLET_NO_GREENDNS", "yes")

    from sentry_sdk import init
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    init(
        dsn=settings.SENTRY_DSN,
        enable_tracing=settings.SENTRY_TRACES_SAMPLE_RATE > 0,
        traces_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        profile_session_sample_rate=settings.SENTRY_PROFILE_SESSION_SAMPLE_RATE,
        profile_lifecycle=settings.SENTRY_PROFILE_LIFECYCLE,
        enable_logs=settings.SENTRY_ENABLE_LOGS,
        environment=settings.SENTRY_ENVIRONMENT,
        release=settings.VERSION,
        send_default_pii=True,
        integrations=[FastApiIntegration()],
    )

    app_logger.info(
        "Sentry initialized",
        environment=settings.SENTRY_ENVIRONMENT or "unset",
        release=settings.VERSION,
    )
