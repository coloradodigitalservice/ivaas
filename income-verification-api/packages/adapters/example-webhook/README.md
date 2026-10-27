# example-webhook-adapter

This package demonstrates the complete structure of a webhook-based adapter.
It has a program-facing invitation endpoint and an inbound event endpoint.
It is a development dependency registered only by tests and must not be enabled in a deployed environment.

Tests configure the adapter with this mapping:

```python
WEBHOOK_ADAPTERS = {
    "example_webhook_adapter": {
        "enabled": True,
        "config": {"api_key": "example-webhook-test-key"},
    },
}
```

The API key authenticates requests to the inbound event endpoint.

See [the webhook adapters section of the IVaaS documentation](../../../../docs/configuration/ivaas-configuration.md#webhook-adapters) for more details on registering and configuring webhook-based adapters like this one.
