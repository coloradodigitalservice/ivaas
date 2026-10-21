# Digital Public Works (DPW) - Verify My Income (VMI) Adapter Data Flow

## Program Client Onboarding

Programs must coordinate the configuration and implementation of several interactions with IVaaS:

1. The ability to generate VMI invite links for their users
   - This synchronous API call leverages the same API authentication as other IVaaS endpoints, so programs must register as clients as shown in the general IVaaS [data flow documentation](../../../../../docs/api/data-flow.md)
2. The ability to receive VMI verification results via webhook
   - Programs must expose an endpoint that IVaaS will POST VMI results to, and share an API key with the IVaaS team
3. (Optional) The ability to receive VMI verification results via document upload
   - If using, programs must configure IVaaS access to upload VMI verification documents

## Data Flow

> [!NOTE]
> Currently, this diagram only shows the "happy path".
>
> Error cases can be added with `option` and/or `break`, but will significantly impact readability at this stage.

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
    
    loop whenever applicant clicks invitation link
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
        and VMI document handling
            vmi->>api: Send verification results via document upload 🔒
            api->>api: Determine document upload's originating program
            
            opt if program is configured to handle VMI document uploads
                api->>programApp: Send verification results via document upload 🔒
                
                opt
                    programApp->>programApp: Process and store document
                    programApp->>applicant: Notify applicant of results or further required action(s)
                end
            end
        end
    end
```