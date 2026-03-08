from odoo import fields, models


class FlowforgeDelegateWizard(models.TransientModel):
    _name = 'flowforge.delegate.wizard'
    _description = 'Delegate Approval Wizard'

    request_id = fields.Many2one('flowforge.approval.request', required=True)
    delegate_user_id = fields.Many2one('res.users', required=True)
    note = fields.Text()

    def action_delegate(self):
        self.ensure_one()
        lines = self.request_id.line_ids.filtered(lambda l: l.user_id == self.env.user and l.state == 'pending')
        if lines:
            lines.write({'user_id': self.delegate_user_id.id, 'comment': self.note or False})
            self.request_id._log_event('submitted', 'Delegated by %s to %s' % (self.env.user.display_name, self.delegate_user_id.display_name))
        return {'type': 'ir.actions.act_window_close'}
