from odoo import fields, models


class FlowforgeApprovalLog(models.Model):
    _name = 'flowforge.approval.log'
    _description = 'Approval Log'
    _order = 'create_date desc, id desc'

    request_id = fields.Many2one('flowforge.approval.request', required=True, ondelete='cascade', index=True)
    action = fields.Selection([
        ('submitted', 'Submitted'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('changes_requested', 'Changes Requested'),
        ('resubmitted', 'Resubmitted'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
        ('escalated', 'Escalated'),
    ], required=True)
    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    note = fields.Text()
