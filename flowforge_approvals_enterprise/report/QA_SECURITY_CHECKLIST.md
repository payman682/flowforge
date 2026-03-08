# QA & Security Checklist

## Functional QA
- Install and upgrade module on Odoo 19.
- Create rules on core models and a custom model.
- Validate sequential and parallel stage completion.
- Verify approve, reject, request changes, resubmit, cancel.
- Verify post-approval action execution.
- Confirm dashboard counters and logs.

## Security QA
- Verify group access boundaries.
- Confirm tokenized portal links cannot enumerate records.
- Confirm no direct SQL usage.
- Review record rule on requests.
- Review cron escalation behavior.

## Release QA
- Run unit tests.
- Validate icon, README, manifest metadata, and screenshots.
- Check XML data loads with no missing dependencies.
- Review code style and translations.
