# Generating API keys

After `make setup`, run the generator from the IVaaS repository root with
the project's Python interpreter. Generate a fresh key for each integration
and environment:

```sh
income-verification-api/.venv/bin/python scripts/generate-api-key.py .local-secrets/your-new-api-key
```

The script uses Python's `secrets` module to create a random UUIDv4. It
writes the key to a new local file with mode 600, prints only the file path,
and refuses to overwrite an existing file. Keep the output under
`.local-secrets/`, which is gitignored. Use a different filename and a new
key for each integration and environment.

DPW's [current webhook
specification](https://github.com/Digital-Public-Works/dicit-webhook-api-ref-impl/blob/main/Webhooks%20Data%20Transmission%20Spec%20v1.md)
calls for a partner-supplied secret API key GUID and a unique key for each
environment. It does not require a particular UUID version; UUIDv4 is this
script's choice. API keys should not be reused across environments and should be rotated. The filename
identifies the integration and environment; it is not part of the key. Check
another integration's format requirements before using this generator for it.

Once the key is generated, manually transfer it your team's secret store along with when it was generated, the environment, and how it's being used then share it
with the partner through an approved method, such as a 1Password link or
encrypted email. This script does not store keys in an external system or
send them anywhere.

After transferring the key to your team's secret store, remove the local file from your local system. Never commit a key, include it in
a ticket, or paste it into command arguments or logs.
