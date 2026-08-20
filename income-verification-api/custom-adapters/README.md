# Custom Adapters

States have the need for custom adapters interacting with proprietary data sources.

Custom adapters can be developed in separate repositories, built, and fetched into `wheels/` for the IVaaS application to register.

This workflow is suitable for adapters with private source code where information about the corresponding data sources is preferred to be kept private, since adapter wheels are .gitignored.

Fetching and verifying wheels is handled by the `adapters-*` targets in the project's [Makefile](../../Makefile).
See `make help`.
