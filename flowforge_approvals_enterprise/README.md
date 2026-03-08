# FlowForge Approvals Enterprise

Enterprise-grade universal approval workflow engine for Odoo 19.

## Highlights
- Universal approvals across any model
- Sequential and parallel stages
- Dynamic approver resolution
- Secure email/portal approval links
- Delegation, SLA escalation, and audit trail
- Dashboard and reusable templates

## Installation
1. Copy `flowforge_approvals_enterprise` into your custom addons path.
2. Update Apps list.
3. Install **FlowForge Approvals Enterprise**.
4. Assign security groups.
5. Configure rules and stages.

## QA checklist
- Install on a clean Odoo 19 database.
- Validate access rights for user, manager, admin.
- Create a sample rule on `sale.order` or `purchase.order`.
- Submit, approve, reject, request changes, and resubmit.
- Verify cron escalation and portal approval route.
- Review chatter messages and immutable audit logs.

## Security notes
- Uses group-based access and record rules.
- Secure public token for approval links.
- No direct SQL.
- Business actions run through ORM only.

## Known implementation notes
This package is production-style scaffolding. Final deployment should include:
- model-specific submit hooks for each business flow,
- mail templates,
- a richer JS workflow builder,
- broader automated tests on the target Odoo build.
