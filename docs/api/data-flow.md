# Data Flow

> [!NOTE]
> Currently, this only shows the "happy path".
>
> Error cases can be added with `option` and/or `break`, but will significantly impact readability at ths stage.

API request details can be found in the swapper-api-spec.y

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
    programApp->>cognito: access token request 🔒
    cognito->>programApp: access token response 🔒
    programApp->>programApp: cache access token
    end
    programApp->>api: Test connection request 🔒
    api->>programApp: Test connection response 🔒
    programAdmin->>programApp: Verify results of test
    ivAdmin->>api: Verify results of test
    end
```

## Income Verification

```mermaid
sequenceDiagram
    autonumber

    actor user
    participant programApp as Program Application
    box IVaaS Environment
    participant cognito as IV Cognito
    participant api as IVaaS API
    end
    box IV Snowflake
    participant datasource1 as FAMLI Direct Share
    participant datasource1Meta as CDLE-specific Metadata
    end
    box CDLE FAMLI Snowflake
    participant datasource1Originator as IV Share Schema
    participant datasource1OriginatorMeta as Metadata Share Schema
    end

    loop whenever users trigger income verification flows
    user->>programApp: Trigger income verification

    opt needs fresh access token
    programApp->>cognito: access token request
    cognito->>programApp: access token response
    programApp->>programApp: cache access token
    end

    programApp->>api: Income data request 🔒
    api->>cognito: Validate token
    api->>api: Validate request
    api->>datasource1: SQL REST API Query
    datasource1->>api: Query result(s)
    api->>api: Validate results
    api->>api: Normalize results for response
    api->>datasource1Meta: Log metadata
    note over datasource1Meta: (metadata is shared with CDLE)
    api->>programApp: Income data response 🔒

    opt Income verification business logic
    programApp->>programApp: Validate response
    programApp-->>programApp: Business logic & transformations
    programApp-->>programApp: Persist audit data
    programApp-->>user: Present data / eligibility
    end
    end
```
