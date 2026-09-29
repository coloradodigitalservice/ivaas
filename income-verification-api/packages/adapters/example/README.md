# example-adapter

This adapter does nothing. It answers every lookup with an empty response.
It exists only as a reference implementation of the `ivaas-core` adapter
contract and as a stand-in adapter for ivaas's own tests. It should never be registered
outside of tests.

It is a uv workspace member installed through the `dev` dependency group, so
it is present in a development checkout and absent from the runtime image.

For the settings entry that registers an adapter, see
[Adapter configuration](../../../../docs/configuration/ivaas-configuration.md#adapter-configuration).
