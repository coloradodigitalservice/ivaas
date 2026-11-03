"""Check the DPW VMI skeleton endpoint."""

from collections.abc import Iterator

import pytest
from django.conf import settings
from django.test import Client, override_settings

WEBHOOK_PATH = "/dpw-vmi/v1/income-report"
WEBHOOK_URL = f"/api{WEBHOOK_PATH}"


@pytest.fixture
def dpw_vmi_adapter() -> Iterator[None]:
    with (
        override_settings(
            ROOT_URLCONF="tests.webhook_adapters.dpw_vmi_adapter.urls",
            WEBHOOK_ADAPTERS={
                "dpw_vmi_adapter": {
                    "enabled": True,
                    "config": {"webhook_path": WEBHOOK_PATH},
                }
            },
        ),
        override_settings(
            INSTALLED_APPS=list(dict.fromkeys([*settings.INSTALLED_APPS, "dpw_vmi_adapter"]))
        ),
    ):
        yield


@pytest.mark.usefixtures("dpw_vmi_adapter")
def test_webhook_is_acknowledged(client: Client) -> None:
    response = client.post(WEBHOOK_URL)

    assert response.status_code == 200
    assert response.json() == {"received": True}
