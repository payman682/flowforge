from odoo import api, fields, models


class FlowforgeApprovalDashboard(models.TransientModel):
    _name = 'flowforge.approval.dashboard'
    _description = 'Approval Dashboard'

    pending_count = fields.Integer(readonly=True)
    approved_count = fields.Integer(readonly=True)
    rejected_count = fields.Integer(readonly=True)
    overdue_count = fields.Integer(readonly=True)

    @api.model
    def default_get(self, field_names):
        res = super().default_get(field_names)
        Request = self.env['flowforge.approval.request']
        res.update({
            'pending_count': Request.search_count([('state', '=', 'pending')]),
            'approved_count': Request.search_count([('state', '=', 'approved')]),
            'rejected_count': Request.search_count([('state', '=', 'rejected')]),
            'overdue_count': Request.search_count([('state', '=', 'pending'), ('due_date', '<', fields.Datetime.now())]),
        })
        return res
