from django.conf import settings


def test_every_declared_adapter_package_logs_like_the_engine() -> None:
    engine_logger = settings.LOGGING["loggers"]["adapter_engine"]

    for declaration in settings.INCOME_SOURCE_ADAPTERS.values():
        package = str(declaration["class"]).partition(".")[0]
        assert settings.LOGGING["loggers"][package] == engine_logger
