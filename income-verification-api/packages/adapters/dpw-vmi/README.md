# DPW VMI adapter

Public webhook adapter for Digital Public Works Verify My Income (VMI).

## Webhook URL

When installed, the adapter is enabled by default. Set `DPW_VMI_ADAPTER_ENABLED=False` to remove
its endpoint.
`DPW_VMI_WEBHOOK_PATH` sets the route beneath IVaaS's `/api` prefix and defaults to
`/dpw-vmi/v1/income-report`.

See the [data flow](docs/data-flow.md) for the planned integration.

## Webhook signing key

DPW's [webhook specification](https://github.com/Digital-Public-Works/dicit-webhook-api-ref-impl/blob/main/Webhooks%20Data%20Transmission%20Spec%20v1.md)
calls for a partner-supplied GUID and distinct keys for demo and production.
The [key-generation command](../../../../docs/configuration/ivaas-configuration.md#generating-api-keys)
produces a 32-character UUIDv4 GUID in hex form. Generate a separate key for
each environment.

DPW uses this shared secret to sign webhook requests; under webhook contract
2, the key itself is not sent in `X-VMI-API-Key`. The separate invitation API
key is issued by DPW to IVaaS.

Set `DPW_VMI_WEBHOOK_API_KEY` in `.envs/.local/.secrets` when the adapter is enabled.
IVaaS checks the lowercase hex HMAC-SHA512 of `<X-VMI-Timestamp>:<raw body>`
before processing a webhook. `DPW_VMI_WEBHOOK_TIMESTAMP_MAX_AGE_SECONDS` sets
how old a timestamp may be (default 300 seconds; must be positive). Timestamps
up to 5 seconds in the future are also accepted to allow minor clock drift.
Invalid headers, signatures, or timestamps return `401`
with a generic `error_code` and `message`. The specific failure is logged
without the key, signature, or body.

## Development

The DPW VMI adapter declares its own [Makefile](./Makefile) for development and testing tasks, and is included in the
root [Makefile](../../../../Makefile) for convenience.

## Testing

To smoke test the vmi-adapter locally, incoming webhook events can be simulated, which can be passed to a [mock receiver](./scripts/mock_webhook_receiver.py).

1. Ensure that the [local .adapters](../../../config/settings.py) URL and Signing Key configurations for the desired program are set to the values expected by the [mock receiver](./scripts/mock_webhook_receiver.py) (`_WEBHOOK_RECEIVER_URL` & `_SIGNING_KEY`)
2. Start IVaaS (`make run` or `make up`)
3. Start the mock receiver (`make vmi-webhook-listener-mock`)
4. Send webhook messages to IVaaS with the corresponding make recipes (e.g. `make vmi-report-submission`, `make vmi-transmission-complete`)
5. Verify traffic and logs of IVaaS and the mock receiver are as expected
