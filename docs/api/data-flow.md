# Data Flow

> [!NOTE]
> Currently, this only shows the "happy path".
>
> Error cases can be added with `option` and/or `break`, but will significantly impact readability at ths stage.

API request details can be found in the [open-api-spec.yaml](./open-api-spec.yaml)

## Program Client Onboarding

```mermaid
sequenceDiagram
    autonumber

    actor programAdmin as Program Administrator
    actor ivAdmin as IV Administrator
    box Program Environment
    participant programApp as Program Application
    end
    box IVaaS Environment
    participant cognito as IV Cognito
    participant api as IVaaS API
    end

    programAdmin->>ivAdmin: Initiate onboarding
    ivAdmin->>cognito: Setup client (client id & client secret)
    ivAdmin->>programAdmin: Share client credentials 🔒
    programAdmin->>programApp: Store client credentials 🔒
    ivAdmin->>api: Add program configurations

    loop as neeeded, verify connection and configurations
    programAdmin->>programApp: Initiate connection test
    opt needs fresh access token
    programApp->>cognito: Access token request 🔒
    cognito->>programApp: Access token response 🔒
    programApp->>programApp: Cache access token
    end
    programApp->>api: Test connection request 🔒
    api->>cognito: Validate token
    api->>api: Validate request
    api->>api: Build response
    api->>api: Log results
    api->>programApp: Test connection response 🔒
    programApp->>programApp: Log results
    programAdmin->>programApp: Verify results of test
    ivAdmin->>api: Verify results of test
    end
```

## Income Verification API

```mermaid
sequenceDiagram
    autonumber

    actor user
    participant programApp as Program Application
    box IVaaS Environment
    participant cognito as IV Cognito
    participant api as IVaaS API
    participant adapter as Income Source Adapter
    end
    participant source as Income Source

    loop whenever users trigger income verification flows
    user->>programApp: Trigger income verification

    opt needs fresh access token
    programApp->>cognito: Access token request 🔒
    cognito->>programApp: Access token response 🔒
    programApp->>programApp: Cache access token
    end

    programApp->>api: Income data request 🔒
    api->>cognito: Validate token
    api->>api: Validate request

    loop for each configued adapter
    api ->> adapter: Invoke adapter
    adapter <<->> source: Authenticate against data source 🔒
    adapter ->> source: Request Income Data 🔒
    source ->> adapter: Return Income Data 🔒
    adapter ->> adapter: Parse, validate, and package data
    adapter ->> api: Return packaged response
    end

    api->>api: Package and consolidate adapter responses
    api->>programApp: Income data response 🔒

    opt Income verification business logic
    programApp->>programApp: Validate response
    programApp-->>programApp: Business logic & transformations
    programApp-->>programApp: Persist audit data
    programApp-->>user: Present data / eligibility
    end
    end
```
