from odoo import fields, models


class FlowforgeBulkApprovalWizard(models.TransientModel):
    _name = 'flowforge.bulk.approval.wizard'
    _description = 'Bulk Approval Wizard'

    request_ids = fields.Many2many('flowforge.approval.request')
    action = fields.Selection([('approve', 'Approve'), ('reject', 'Reject')], required=True, default='approve')
    comment = fields.Text()

    def action_apply(self):
        for request in self.request_ids:
            if self.action == 'approve':
                request.action_approve(comment=self.comment)
            else:
                request.action_reject(comment=self.comment)
        return {'type': 'ir.actions.act_window_close'}
