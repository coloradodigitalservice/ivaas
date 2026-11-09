---
status: "accepted"
deciders: CDS-IVAAS
---

# Use static credentials for Django database users

## Context and Problem Statement

The IVaaS Django application is designed to be used with a PostgreSQL database. The code base should be reusable by teams deploying to AWS, Azure or other clouds, using that provider's managed PostgreSQL. Local development uses static credentials. What type of credentials should the database users use in AWS?

### Decision Drivers

* Cloud agnosticism: the application code should deploy to other clouds without rework.
* Security: avoid long-lived credentials where we can.
* Operational overhead: minimize infrastructure and processes teams must build and operate, such as password rotation.

## Decision Outcome

Use static credentials for Django database users, because it avoids the application code and configuration work that RDS IAM authentication would require and provides a cloud-agnostic application code path.

This doesn't rule out adding an RDS IAM authentication option later. Adding it means a credential source that supplies a fresh token for each new database connection.

### Consequences

* Local development and deployed environments use the same credential path.
* Application database users authenticate with passwords stored in a secret store, one secret per user.
* We (and other teams) will need decide how to manage password creation and
  rotation, either as a manual process or through automation, and either as a
  zero-downtime operation or a maintenance window activity.

## Options Considered

### Static credentials

Deployed environments use static credentials, stored in a secret store.

* `+` no additional application code or configuration for authentication
* `+` one credential path in every environment, so local development exercises it
* `+` works with any PostgreSQL deployment and client without token generation
* `-` uses long-lived passwords in deployed environments
* `-` each adopting team must build and operate password rotation for its cloud
* `-` in AWS, single-user rotation causes a brief window of failed connections; alternating-users rotation avoids it but needs a superuser secret and a cloned user per rotated user, whose permissions must be kept in sync

### Pluggable credential source with RDS IAM authentication in AWS

The application reads its database password through a small abstraction. Each deployment configures which source to use via environment variable toggle. Deployed AWS environments use RDS IAM authentication tokens. Local development uses static credentials.

* `+` no long-lived passwords for the application's database users in deployed AWS environments
* `+` no password rotation to operate in deployed AWS environments
* `+` static credentials remain an available source, so it is no less portable than static credentials everywhere
* `-` requires application code to generate and inject tokens
* `-` tokens expire after 15 minutes, so Django's psycopg connection pool must fetch a fresh token for each new physical connection
* `-` local development does not exercise the RDS IAM path, and it is difficult to test locally
* `-` two credential paths to maintain
