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
* The team is lean, so whatever we adopt has to cost close to nothing.
* The repository is new, so a convention adopted now applies to the whole history.

## Decision Outcome

Use [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) for the application code, because a machine-readable history
lets us easily generate changelogs instead of maintaining them by hand.

This ADR decides the convention only. It does not select tooling to aid with enforcement.

### Consequences

* We should enable automated checks on PRs to enforce the convention.
* The type and scope vocabulary is ours to agree on and document in `CONTRIBUTING` documentation.
* Breaking changes are best marked with `!` in the title, given the single line restriction.
* Release automation becomes a follow-on decision. Candidates could include:
  * [python-semantic-release](https://python-semantic-release.readthedocs.io/), which ships a `conventional-monorepo` parser that filters commits per package by changed path and scope
  * [release-please-action](https://github.com/googleapis/release-please-action) or [git-cliff](https://git-cliff.org/) for changelog generation alone.

## Options Considered

### Adopt the [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/) specification for merge commits

* `++` Unifies the contributor experience across modules that the current IVaaS team is already accutomed to.
* `++` Encodes change type and breaking status in the subject, so changelogs and version
  bumps can be derived from history.
* `+` Published specification with an existing [tool ecosystem](https://www.conventionalcommits.org/en/about/),
  so we do not design or maintain a format ourselves.
* `+` Under squash and merge, the check lands on the PR title, so commits on a branch are
  unaffected.
* `±` Requires agreeing a type and scope vocabulary and documenting it.
* `-` Adds a required check that can block a merge on a title typo.
* `-` Restricts breaking-change notation to `!`, because the PR title is a single line.

### No commit convention

Freeform commits. Change metadata lives on the pull request rather than in the
message.

* `+` Adds no CI check, no vocabulary to agree, and nothing for contributors to learn.
* `±` Something like [Release Drafter](https://github.com/release-drafter/release-drafter) could still be used to automate release notes, but it reads labels applied by hand to each pull request.
  That metadata lives in GitHub rather than the repository, so a fork or a migration off GitHub would lose it.
* `-` Adopting the convention later splits the history into two formats and leaves the earlier range unusable by tooling.
* `-` Would require a different mechanism (possibly manual) to generate changelogs for API clients and stakeholders.
* `-` Makes the developer experience between modules dissimilar, as the current IVaaS team is using conventional commits in other repositories.
