# DPW VMI adapter

Future webhook adapter for Digital Public Works Verify My Income (VMI).

See the [data flow](docs/data-flow.md) for the proposed implementation.

## Webhook signing key

DPW's [webhook specification](https://github.com/Digital-Public-Works/dicit-webhook-api-ref-impl/blob/main/Webhooks%20Data%20Transmission%20Spec%20v1.md)
calls for a partner-supplied GUID and distinct keys for demo and production.
The [key-generation command](../../../../docs/configuration/ivaas-configuration.md#generating-api-keys)
produces a 32-character UUIDv4 GUID in hex form. Generate a separate key for
each environment.

DPW uses this shared secret to sign webhook requests; under webhook contract
2, the key itself is not sent in `X-VMI-API-Key`. The separate invitation API
key is issued by DPW to IVaaS.
