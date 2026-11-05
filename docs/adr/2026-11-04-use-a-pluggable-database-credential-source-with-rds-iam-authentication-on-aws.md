---
status: "proposed"
deciders: []
---

# Use a pluggable database credential source with RDS IAM authentication on AWS

## Context and Problem Statement

The IVaaS Django application is designed to be used with a PostgreSQL database, with separate database users for migrations and application runtime (see [Use separate database users for Django migrations and application runtime](2026-11-04-use-separate-database-users-for-django-migrations-and-application-runtime.md)). The code base should be reusable by teams deploying to AWS, Azure or other clouds, using that provider's managed PostgreSQL. Local development uses static credentials. What type of credentials should the two database users use in AWS?

### Decision Drivers

* Cloud agnosticism: the application code should deploy to other clouds without rework.
* Security: avoid long-lived credentials where we can.
* Operational overhead: minimize infrastructure and processes teams must build and operate, such as password rotation.

## Decision Outcome

Use a pluggable database credential source with RDS IAM authentication on AWS, because it avoids long-lived passwords for the application's database users and the overhead of operating password rotation, including the extra database users that rotation can require.

### Consequences

* The application gets its database password from a configured credential source at connect time. We'll ship two sources: static credentials and RDS IAM authentication.
* Deployed AWS environments use the RDS IAM source for both database users. Each ECS task role gets `rds-db:connect` scoped to its own database user only.
* We must turn on IAM authentication for the database, since it's off by default, and grant `rds_iam` to both database users. A user with `rds_iam` authenticates by token only, so the static source can't be used for that user in AWS.
* Local development uses the static source.
* Teams deploying to another cloud would require a credential source for their provider's token authentication or use the static source and operate their own password rotation.

## Options Considered

### Pluggable credential source

The application reads its database password through a small abstraction. Each deployment configures which source to use.

* `+` no long-lived passwords for the application's database users in deployed AWS environments
* `+` no password rotation to operate in deployed AWS environments
* `+` static credentials remain an available source, so it is no less portable than static credentials everywhere
* `+` application code need not depend on AWS outside the RDS IAM source
* `-` two credential paths to maintain
* `-` local development does not exercise the RDS IAM path

### Static credentials everywhere

Every environment, local and deployed, uses a static password stored in a secret store.

* `+` one credential path in every environment, including local development
* `+` works with any PostgreSQL deployment and client without token generation
* `-` uses long-lived passwords in deployed environments
* `-` each adopting team must build and operate password rotation for its cloud
* `-` on AWS, single-user rotation causes a brief window of failed connections; alternating-users rotation avoids it but needs a superuser secret and a cloned user per rotated user, whose permissions must be kept in sync
