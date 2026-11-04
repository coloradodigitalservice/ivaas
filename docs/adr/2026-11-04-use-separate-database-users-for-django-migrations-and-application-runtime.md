---
status: "proposed"
deciders: []
---

# Use separate database users for Django migrations and application runtime

## Context and Problem Statement

The IVaaS Django application uses a PostgreSQL database. Migrations need DDL rights to create and alter schema. Regular application functionality only needs to read and write data. Should migrations and the running application share one database user, or use separate users?

How migrations are executed is out of scope. A separate ADR covers it.

## Decision Outcome

Use separate database users for Django migrations and application runtime, because each type of task should run with only the privileges it needs.

### Consequences

* Tables and sequences created by migrations are owned by the migration user. We must grant the application user access to them and set default privileges for the migration user so future objects are covered.
* If using static credentials, we manage two credentials.
* Migrations must run in an execution context that can read the migration user's secret. The application runtime must not be able to read it. The ADR on migration execution must work within this constraint.

## Options Considered

### Separate users for migrations and application runtime

A migration user owns the schema and runs `migrate`. An application user has data access only and no DDL rights.

* `+` each type of task runs with only the privileges it needs
* `+` the application user has no DDL rights, which limits the blast radius of a compromised application or SQL injection
* `-` the migration user owns the objects it creates, so the application user needs `GRANT`s and `ALTER DEFAULT PRIVILEGES` to access new tables

### Single user for migrations and application runtime

One user runs `migrate` and serves application traffic.

* `+` one credential and one secret to manage
* `+` no grant or default-privilege management, since the user owns everything it creates
* `-` the application runtime holds DDL rights and table ownership, so a compromised application or SQL injection can drop or alter schema
