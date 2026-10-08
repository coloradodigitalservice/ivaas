# Logging without raw PII

Logs should explain what happened without recording personal lookup information
or income data. Redaction is a backup protection, not permission to log sensitive values.

## Protections in place

- Application and configured adapter logs use the same JSON formatter and request context.
- The formatter masks sensitive model fields and whole income payloads, and scans
  messages for recognizable PII and credentials, including full SSNs.
- Formatting or redaction failures produce a safe placeholder.
- Ruff checks discourage formatting messages before they reach the logger.

## Acceptable log content

- Operation names, outcomes, attempt counts, durations, and record counts.
- Approved application, verification, agency, source, and correlation identifiers.
- Exception types and sanitized error messages that preserve useful diagnostics.

In IVaaS, prefer `extra` with keys declared by `LogField` for reusable properties
that should be searchable consistently across logs. The formatter emits only
declared fields; add new safe properties to `LogField` when needed.

```python
logger.info("lookup completed", extra={LogField.EVENT_NAME.value: "lookup.completed"})
```

Formatted values are useful for one-off details. Use a literal template and pass
values separately:

```python
logger.info("lookup completed: source=%s count=%d", source_id, record_count)
```

## Do not log

- Names, birth dates, full or partial SSNs, or other PII values.
- Raw request or response bodies, income payloads, or adapter source error bodies.
- Credentials, authorization headers, or tokens.
- Exception messages that may include user input or downstream payloads.

Truncating a sensitive value or moving it under a generic key does not make it safe.

## Watch for in reviews

- Sensitive values extracted from models and logged as individual strings or numbers.
- Bare dictionaries or lists containing adapter data with unknown field names.
- F-strings, preformatted message variables, or other paths that lose field identity.
- Exception logging that copies adapter source messages or payloads without sanitizing them.
- Logs that assume redaction will recognize every name, income amount, or partial SSN.

For risky paths, exercise successful responses and failures with synthetic sensitive
values and check the emitted logs. Run the existing tests and quality checks.
