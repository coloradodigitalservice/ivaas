---
status: "accepted"
deciders: CDS-IVAAS
---

# Squash and merge with Conventional Commits for PR titles

## Context and Problem Statement

Income Verification as a Service is a service consumed by external stakeholders who would benefit from a changelog summarizing changes to this service.
The repository is new and has no history to retrofit.
We already squash and merge, with the GitHub PR title as the squash commit subject, and the repository setting that enforces this is enabled.

Should we adopt a structured commit message convention now?

### Decision Drivers

* API Clients and other stakeholders will benefit from a changelog to summarize the changes to this service
* `income-verification-core` [has already adopted this strategy](https://github.com/coloradodigitalservice/income-verification-core/blob/main/docs/adr/2026-07-22-squash-and-merge-with-conventional-commits-for-PR-titles.md)
* The team is lean, so whatever we adopt has to cost close to nothing.
* The repository is new, so a convention adopted now applies to the whole history.

## Decision Outcome

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for the application code, because a machine-readable history
lets us easily generate changelogs instead of maintaining them by hand.

This ADR decides the convention only. It does not select tooling to aid with enforcement.

### Consequences

* We should enable [similar automated checks](https://github.com/coloradodigitalservice/income-verification-core/blob/main/.github/workflows/lint-pr.yml) as `income-verification-core`
* All [consequences of the `income-verification-core` adr](https://github.com/coloradodigitalservice/income-verification-core/blob/main/docs/adr/2026-07-22-squash-and-merge-with-conventional-commits-for-PR-titles.md#consequences) would apply here

## Options Considered

### Adopt the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification for merge commits

All the [pros and cons of this option from the `income-verification-core` adr](https://github.com/coloradodigitalservice/income-verification-core/blob/main/docs/adr/2026-07-22-squash-and-merge-with-conventional-commits-for-PR-titles.md#adopt-the-conventional-commits-specification-for-merge-commits), plus:

* `++` Unifies the contributor experience across modules that the team is already accutomed to.
* `±` Adds process where there currently is none.

### No commit convention

Freeform commits. Change metadata lives on the pull request rather than in the
message.

All the [pros and cons of this option from the `income-verification-core` adr](https://github.com/coloradodigitalservice/income-verification-core/blob/main/docs/adr/2026-07-22-squash-and-merge-with-conventional-commits-for-PR-titles.md#no-commit-convention), plus:

* `-` Would require a different mechanism (possibly manual) to generate changelogs for API clients and stakeholders.
* `-` Makes the developer experience between modules dissimilar.
