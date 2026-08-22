"""System-check behavior: undeclared landing-zone wheels warn, declared ones don't."""

from pathlib import Path

from django.test import override_settings

from adapter_registry.checks import unreferenced_adapter_wheels
from adapter_registry.registry import INCOME_SOURCE_ADAPTERS

STUB_DECLARATIONS = {
    "stub": {"class": "stub_adapter.StubAdapter", "enabled": False},
}


def wheels_dir(tmp_path: Path, wheels: list[str]) -> Path:
    directory = tmp_path / "custom-adapters" / "wheels"
    directory.mkdir(parents=True)
    for wheel in wheels:
        (directory / wheel).touch()
    return tmp_path


def test_declared_wheel_is_silent(tmp_path: Path) -> None:
    base = wheels_dir(tmp_path, ["stub_adapter-1.0.0-py3-none-any.whl"])

    with override_settings(**{"BASE_DIR": base, INCOME_SOURCE_ADAPTERS: STUB_DECLARATIONS}):
        assert unreferenced_adapter_wheels() == []


def test_undeclared_wheel_warns(tmp_path: Path) -> None:
    base = wheels_dir(
        tmp_path,
        ["stub_adapter-1.0.0-py3-none-any.whl", "stray_adapter-9.9.9-py3-none-any.whl"],
    )

    with override_settings(**{"BASE_DIR": base, INCOME_SOURCE_ADAPTERS: STUB_DECLARATIONS}):
        messages = unreferenced_adapter_wheels()

    assert [message.id for message in messages] == ["adapter_registry.W001"]
    assert "stray_adapter-9.9.9" in messages[0].msg


def test_disabled_but_declared_wheel_is_silent(tmp_path: Path) -> None:
    """Declared is enough — enablement is a deployment decision, not a mistake."""
    base = wheels_dir(tmp_path, ["stub_adapter-1.0.0-py3-none-any.whl"])

    with override_settings(**{"BASE_DIR": base, INCOME_SOURCE_ADAPTERS: STUB_DECLARATIONS}):
        assert unreferenced_adapter_wheels() == []


def test_inapplicable_outside_a_source_tree(tmp_path: Path) -> None:
    with override_settings(BASE_DIR=tmp_path):
        assert unreferenced_adapter_wheels() == []


def test_check_is_registered() -> None:
    from django.core.checks.registry import registry

    assert unreferenced_adapter_wheels in registry.registered_checks
