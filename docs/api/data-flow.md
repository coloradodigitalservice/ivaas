# Data Flow

> [!NOTE]
> Currently, this only shows the "happy path".
>
> Error cases can be added with `option` and/or `break`, but will significantly impact readability at ths stage.

API request details can be found in the open-api-spec.yaml

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
    api->>cognito: Validate token
    api->>api: Validate request
    api->>api: build response
    api->>api: log results
    api->>programApp: Test connection response 🔒
    programApp->>programApp: Log results
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

    par fetch data from configured datasources
    %% CDLE
    opt if the program requests data from CDLE FAMLI
    create participant datasource1 as IV Snowflake CDLE Data Share
    api-->datasource1: invoke adapter
    api->>datasource1: SQL REST API Query
    datasource1->>api: Query result(s)
    api->>api: Validate datasource results
    api->>api: Normalize datasource results for response
    api->>datasource1: Log audit metadata
    note over datasource1: (metadata is shared with CDLE)
    destroy datasource1
    datasource1-->api: finalize adapter invocation
    end

    and

    %% Equifax
    opt if the program requests data from Equifax API
    create participant datasource2 as Equifax API
    api-->datasource2: invoke adapter
    opt needs fresh access token
    api->>datasource2: access token request 🔒
    datasource2->>api: access token response 🔒
    api->>api: cache access token
    end
    api->>datasource2: Instant Client Insights for Eligibility Request 🔒
    datasource2->>api: Instant Client Insights for Eligibility Response 🔒
    api->>api: Validate datasource results
    api->>api: Normalize datasource results for response
    destroy datasource2
    datasource2-->api: finalize adapter invocation
    end
    end

    api->>api: package normalized response data
    api->>programApp: Income data response 🔒

    opt Income verification business logic
    programApp->>programApp: Validate response
    programApp-->>programApp: Business logic & transformations
    programApp-->>programApp: Persist audit data
    programApp-->>user: Present data / eligibility
    end
    end
```
