# Testing Strategy

## General Testing Approach

Use unit tests to verify logic, integration tests against mocks to verify how components work together, and a small end-to-end (E2E) suite to verify the deployed application against real services. Run unit and mock integration tests in CI before deployment, then run E2E tests in sandbox or development before promotion. Reserve a limited smoke suite for production. Target at least 80% code coverage, with meaningful assertions for critical behavior.

Public adapters in the IVaaS repository should include tests in each applicable category. Private adapter tests and fixtures belong with those adapters, outside the public IVaaS repository. Deployers should run the IVaaS and adapter unit and integration suites in their own CI before deployment, including integration checks for their configuration and adapter combination. An unchanged release can rely on verified upstream unit-test results; deployment-specific integration and E2E checks remain the deployer's responsibility. Promote the same application image that passed testing.

## Unit Testing

Unit tests provide the fastest feedback on logic and regressions. They should cover validation, transformations, and error handling, and run locally without deployed infrastructure or live services.

## Integration Testing with Mocks

Run the real application and installed adapter against mock identity and upstream services, exercising the HTTP API and normal authentication path. Use deterministic fixtures for success, no data, timeout, and malformed upstream responses. Assert the API response and the requests received by the upstream mock, including required audit writes or other side effects. These tests should run locally and in CI without production credentials.

## End-to-End Testing

Deployers should run automated E2E tests against their deployed application, real identity provider, and real upstream services. Use provider-approved test subjects and environment-specific credentials from the deployer's secret store.

Run the tests after deployment is ready, either directly on the deployer's CI runner or in a separate test container launched by the pipeline. The test environment must be able to reach the API and identity provider. For private endpoints, place it on a network with the required access. Test code and dependencies stay outside the application image. Developers can run the same tests locally against an accessible environment.

For both suites below, check source-level results as well as HTTP status, and record correlation IDs for failures without logging credentials or claimant data.

### Tests for Any Environment

Maintain a small suite of tests with explicit expected results that can be configured and run in any environment (including production):

- **Health and connection:** the API responds, and an authenticated connection test returns the expected agency and environment.
- **Authentication rejection:** a request without a token is rejected.
- **No income:** a known no-data subject returns the expected no-data status and no income payload, where the provider supplies a stable test subject.

In production, run only smoke cases supported by production-safe test identities; report any missing verification coverage.

The [smoke suite](../../smoke_tests/test_api.py) uses pytest and Python's standard-library HTTP client. It runs independently of Django settings, database setup, and unit-test coverage requirements. Configure these environment variables on the runner:

| Variable                                              | Value                                                                                  |
| ----------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `SMOKE_BASE_URL`                                      | Application base URL, such as `https://iv.example.org`, without `/api`.                |
| `SMOKE_TOKEN_URL`                                     | OAuth client-credentials token endpoint.                                               |
| `SMOKE_CLIENT_ID`, `SMOKE_CLIENT_SECRET`              | Test-client credentials, supplied through the deployer's secret store.                 |
| `SMOKE_EXPECTED_AGENCY`, `SMOKE_EXPECTED_ENVIRONMENT` | Expected values from the authenticated connection test.                                |
| `SMOKE_API_VERSION`                                   | Optional; defaults to `v1`.                                                            |
| `SMOKE_SCOPE`                                         | Optional; defaults to `ivaas/income.verify`.                                           |
| `SMOKE_NO_INCOME_CASES`                                | Optional path to a private JSON file defining approved no-income scenarios.              |

From the IVaaS repository root, on a fresh CI runner:

```shell
uv sync --project income-verification-api --locked --only-group test
make test-smoke SMOKE_TEST_ARGS="--junitxml=smoke-results.xml"
```

For local testing, use the normal `make sync` setup, start the application with `make run` or `make up`, and run `make test-smoke-local` in another terminal. This supplies the committed local API and mock OAuth settings. Use `make test-smoke` with the configuration above for other environments. URLs must use HTTPS except on localhost. The HTTP client uses a 30-second socket timeout and does not follow redirects. This does not limit the total request duration; set an overall test deadline in the pipeline or execution environment.

The missing-token check requires HTTP `401` but does not require an application-specific response body or correlation header: an authentication gateway may reject the request before it reaches the application. Application tests retain the detailed error-contract assertions. Authenticated smoke requests still check correlation ID propagation.

HTTP failures identify the endpoint and include the response status when available, including invalid-JSON and redirect responses. Redirects are rejected without following their destination. Diagnostics exclude response bodies, URLs, credentials, and claimant data. JUnit correlation properties are named by API route so the connection check and verification request can be distinguished.

Set `SMOKE_NO_INCOME_CASES` to a JSON case file such as:

```json
[
  {
    "name": "no-records-in-either-source",
    "requestFile": "requests/subject-a.json",
    "expectedSources": {
      "source-a": {"status": "NO_DATA"},
      "source-b": {"status": "NO_DATA"}
    }
  },
  {
    "name": "different-lookback",
    "requestFile": "requests/subject-a-earlier-period.json",
    "expectedSources": {
      "source-a": {"status": "NO_DATA"},
      "source-b": {"status": "NO_DATA"}
    }
  }
]
```

Request-file paths are relative to the case file, or absolute paths within the runner. Each request contains the normal verification fields for an approved test subject and lookback period. Use unique, non-sensitive case names of 1-64 letters, digits, underscores, or hyphens; names appear in test output and JUnit results.

Pytest runs each scenario as a separate test in the same process or container. The suite generates a unique `applicationId` and correlation IDs, verifies the target agency/environment before submitting, and requires exactly one result for every expected source, with no additional sources. Every source must return `NO_DATA` with explicitly null `rawIncome` and `retrievedAt`. Expected source IDs describe the response; they do not select which adapters the application invokes. Requests can still create audit records.

Without `SMOKE_NO_INCOME_CASES`, verification is explicitly skipped. A supplied case file must contain at least one valid scenario; malformed files or missing request fixtures fail the suite. This case file replaces the earlier `SMOKE_NO_INCOME_REQUEST` and `SMOKE_SOURCE_ID` settings. Mixed outcomes and known-income payload assertions belong in the broader adapter tests below.

CI builds the test image and runs its connectivity and authentication checks against the local application image and mock identity provider. Results remain in the CI logs; this workflow does not upload JUnit artifacts. Deployers run the same suite after deployment with their own configuration and approved fixture, using the IVaaS revision associated with the deployed release. Deployer pipelines should publish the JUnit report even when tests fail to retain results, skips, correlation IDs, and verification IDs. Require the test job to pass before promotion.

#### Container Runner

Build the standalone [test image](../../smoke_tests/Dockerfile) from the IVaaS repository root. It uses the existing lockfile's test dependencies and runs pytest as a non-root user. Tag it with the release being tested; the following example assumes the required `SMOKE_*` variables are already set:

```shell
make smoke-image SMOKE_IMAGE=ivaas-smoke:my-release
mkdir -p smoke-results
docker run --rm \
  --user "$(id -u):$(id -g)" \
  --mount "type=bind,source=$PWD/smoke-results,target=/results" \
  -e SMOKE_BASE_URL -e SMOKE_TOKEN_URL \
  -e SMOKE_CLIENT_ID -e SMOKE_CLIENT_SECRET \
  -e SMOKE_EXPECTED_AGENCY -e SMOKE_EXPECTED_ENVIRONMENT \
  ivaas-smoke:my-release
```

- The default report is `/results/smoke-results.xml`, written to `smoke-results/` on the host in this example. The container returns pytest's exit code. Additional arguments after the image name replace the default `--junitxml=/results/smoke-results.xml` argument; include it if you also pass test-selection options.
- Supply optional `SMOKE_*` variables as needed. For verification, mount the case file and its request fixtures together read-only, for example with `--mount type=bind,source=/absolute/path/approved-fixtures,target=/fixtures,readonly` and `-e SMOKE_NO_INCOME_CASES=/fixtures/no-income-cases.json`. Relative request paths then resolve within that mounted directory. Credentials and private fixtures are supplied at runtime and excluded from the image build context.
- Container networking must reach the configured URLs; `localhost` inside a container refers to that container. CI uses Linux host networking to reach its local application and mock OAuth server. For local development, `make test-smoke-local` avoids container-network setup.
- Deployers own image publishing, network access, secret injection, and report persistence. Treat task startup failure, timeout, missing results, and a nonzero test exit code as failed validation. A stopped test container alone does not establish success.

#### Adapter Test Images

An adapter repository can extend the shared image and copy its HTTP tests beneath the shared fixture directory:

```dockerfile
FROM ivaas-smoke:release
COPY tests/deployed/ /smoke/smoke_tests/adapter_tests/
```

The shared [pytest fixtures](../../smoke_tests/conftest.py) provide `base_url`, `access_token`, and `api`. Tests that invoke verification should use `verified_api`, which checks the expected agency and environment before returning the authenticated request function. Both request functions accept a relative API route and a JSON payload (`None` for GET), and return the HTTP status and decoded response. Use fixed route names, with subject data in the payload.

The inherited default runs only the shared smoke file. To also run the adapter tests, supply `/smoke/smoke_tests/adapter_tests` as an additional pytest argument, together with `--junitxml=/results/smoke-results.xml`. Keep these broader scenarios opt-in for sandbox or development, with approved fixtures supplied at runtime. Build the derived image from the shared image version associated with the deployed release.

### Sandbox and Development Tests

Run one test suite against the deployed income-verification API, covering every adapter the deployment is configured to invoke. A single test runner executes the scenarios for all adapters:

1. After the candidate deployment is ready in sandbox or development, run the test suite from a connected CI runner or a single test container.
2. Configure the runner with the API URL, credentials, and expected agency/environment. Supply approved request fixtures and expected source-level outcomes for each scenario. A single request may cover multiple adapters; use separate test cases within the same run when adapters need different test subjects or lookback periods.
3. Execute the shared smoke tests and broader verification scenarios against the same deployment. For each scenario, assert exactly one result for every expected `sourceId` and check its status and payload. Verify that the returned set of sources matches the configured orchestration for that request.
4. Require all scenarios to pass before promotion, with verification coverage for every adapter. Connectivity checks alone or a skipped no-income case do not establish adapter coverage.

Use approved test subjects with known results and cover:

- **Known income:** verify the intended `sourceId`, `OK` status, retrieval timestamp, and expected income records. Include subjects with multiple records where the source supports them.
- **Request variations:** exercise the identifiers and lookback periods the adapter supports, including records at the start and end of the requested period where applicable. Verify that returned records match the adapter's documented behavior.
- **Response contract:** check `rawIncome` against the adapter's documented field names, types, and meanings. Assert known values for stable test data; avoid relying on volatile timestamps or changing income values. Fail on missing expected fields or incompatible types.
- **Required side effects:** confirm any audit writes or other required provider-side effects using the provider's supported verification mechanism.

Run this suite after deployment to sandbox or development and require it to pass before promotion. Keep injected upstream failures in the mock integration suite.
