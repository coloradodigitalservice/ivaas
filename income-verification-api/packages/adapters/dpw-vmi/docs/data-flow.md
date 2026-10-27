# Digital Public Works (DPW) - Verify My Income (VMI) Adapter Data Flow

Based on DPW's [Webhooks Transmission Spec](https://github.com/Digital-Public-Works/dicit-webhook-api-ref-impl/blob/main/Webhooks%20Data%20Transmission%20Spec%20v1.md)

## Program Client Onboarding

Programs must coordinate the configuration and implementation of several interactions with IVaaS:

1. The ability to generate VMI invite links for their users
   - This synchronous API call leverages the same API authentication as other IVaaS endpoints, so programs must register as clients as shown in the general IVaaS [data flow documentation](../../../../../docs/api/data-flow.md)
2. The ability to receive VMI verification results via webhook
   - Programs must expose an endpoint that IVaaS will POST VMI results to, and share an API key with the IVaaS team
3. (Optional) The ability to receive VMI verification results via document upload
   - If using, programs must configure IVaaS access to upload VMI verification documents

## Data Flow (Pilot)

During the initial pilot phase, the pilot program will use a direct integration to DPW's VMI for creating invitations.
Webhook events will route through IVaaS.

### Invite generation
```mermaid
sequenceDiagram
    autonumber

    actor applicant
    participant programApp as Program Application
    participant vmi as DPW VMI

    loop whenever applicants trigger income verification flows
        applicant->>programApp: Trigger income verification
        programApp->>vmi: Create Invitation request 🔒
        note over programApp,vmi: Include necessary `custom_attributes`
        vmi->>programApp: Create Invitation response 🔒
        programApp->>applicant: Share invitation link with applicant
    end

    note over applicant,vmi: Applicants may complete Verify My Income flow any time before the invitation link expires
```

### ReportSubmission Webhook
```mermaid
    sequenceDiagram
    autonumber

    actor applicant
    participant programApp as Program Application
    participant api as IVaaS API
    participant vmi as DPW VMI

    loop whenever applicant completes VMI flow
        applicant->>vmi: User (or household member) completes Verify My Income flow

        par VMI webhook handling
            vmi->>api: Send verification results via webhook message 🔒 (IVAAS_VMI_API_KEY)
            api->>api: Validate webhook headers and message
            note over api: Program routing is singular to the pilot program
            api->>api: Build program-specific, signed webhook message
            api->>programApp: Send verification results via webhook message 🔒 (PROGRAM_VMI_API_KEY)
            note over programApp,api: Message includes all `custom_attributes` from the invitation request
            programApp->>programApp: Validate webhook headers and message
            programApp->>programApp: Use `custom_attributes` for applicant/application/case matching and routing

            opt
                programApp->>programApp: Process and store results
                programApp->>applicant: Notify applicant of results or further required action(s)
            end

            programApp->>api: 200 response 🔒
            api->>vmi: 200 response 🔒
        end
   end
```

### Document results and TransmissionComplete webhook
```mermaid
    sequenceDiagram
    autonumber

    actor applicant
    box Program Environment
       participant programApp as Program Application
       participant programS3 as Program S3 VMI Inbox
    end
    participant api as IVaaS API
    participant vmi as DPW VMI

    loop whenever applicant completes VMI flow
        applicant->>vmi: User (or household member) completes Verify My Income flow
        vmi->>programS3: Upload document to program's S3 bucket 🔒
        vmi->>api: Send TransmissionComplete event via webhook message 🔒

        opt if program is configured to handle VMI document uploads (pilot program will be)
            api->>programApp: Send TransmissionComplete event via webhook message 🔒
            programApp->>programApp: Fetch, process, & match document via `confirmation_code`
            programApp->>api: 200 response 🔒
        end
        api->>vmi: 200 response 🔒
    end
```

## Data Flow

> [!NOTE]
> Currently, these diagrams only show the "happy path".
>
> Error cases can be added with `option` and/or `break`, but will significantly impact readability at this stage.

### Invite generation
```mermaid
sequenceDiagram
    autonumber

    actor applicant
    participant programApp as Program Application
    box IVaaS Environment
        participant cognito as IV Cognito
        participant api as IVaaS API
    end
    participant vmi as DPW VMI

    loop whenever applicants trigger income verification flows
        applicant->>programApp: Trigger income verification

        opt needs fresh access token
            programApp->>cognito: access token request 🔒
            cognito->>programApp: access token response 🔒
            programApp->>programApp: cache access token
        end

        programApp->>api: Create Invitation request 🔒
        note over programApp,api: Include program originating `custom_attributes`
        api->>api: Add IV `custom_attributes` and `metrics_attributes`
        api->>vmi: Create Invitation request 🔒 (VMI_IVAAS_API_KEY)
        vmi->>api: Create Invitation response 🔒
        api->>programApp: Create Invitation response 🔒

        programApp->>applicant: Share invitation link with applicant
    end

    note over applicant,vmi: Applicants may complete Verify My Income flow any time before the invitation link expires
```

### ReportSubmission Webhook
```mermaid
    sequenceDiagram
    autonumber

    actor applicant
    participant programApp as Program Application
    participant api as IVaaS API
    participant vmi as DPW VMI

    loop whenever applicant completes VMI flow
        applicant->>vmi: User (or household member) completes Verify My Income flow

        par VMI webhook handling
            vmi->>api: Send verification results via webhook message 🔒 (IVAAS_VMI_API_KEY)
            api->>api: Validate webhook headers and message
            api->>api: Parse custom_attributes to determine program routing
            api->>api: Build program-specific, signed webhook message
            api->>programApp: Send verification results via webhook message 🔒 (PROGRAM_VMI_API_KEY)
            note over programApp,api: Message includes all `custom_attributes` from the invitation request
            programApp->>programApp: Validate webhook headers and message
            programApp->>programApp: Use `custom_attributes` for applicant/application/case matching and routing

            opt
                programApp->>programApp: Process and store results
                programApp->>applicant: Notify applicant of results or further required action(s)
            end

            programApp->>api: 200 response 🔒
            api->>vmi: 200 response 🔒
        end
   end
```

### Document results and TransmissionComplete webhook
```mermaid
    sequenceDiagram
    autonumber

    actor applicant
    participant programApp as Program Application
    box IVaaS Environment
        participant api as IVaaS API
        participant s3 as IV S3 VMI Inbox
    end
    participant vmi as DPW VMI

    loop whenever applicant completes VMI flow
        applicant->>vmi: User (or household member) completes Verify My Income flow
        vmi->>s3: Upload document to S3 🔒
        vmi->>api: Send TransmissionComplete event via webhook message 🔒
        api->>api: Determine document upload's originating program via `confirmation_code`

        opt if program is configured to handle VMI document uploads
            api->>s3: Fetch document from S3 🔒
            s3->>api: Return document 🔒
            api->>programApp: Upload document per program configuration 🔒
            api->>programApp: Send TransmissionComplete event via webhook message 🔒
            programApp->>programApp: Process and store document
            programApp->>api: 200 response 🔒
        end
        api->>vmi: 200 response 🔒
    end
```
