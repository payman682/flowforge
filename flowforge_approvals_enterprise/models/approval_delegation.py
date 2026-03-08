from odoo import api, fields, models, _
from odoo.exceptions import ValidationError


class FlowforgeApprovalDelegation(models.Model):
    _name = 'flowforge.approval.delegation'
    _description = 'Approval Delegation'
    _order = 'date_from desc, id desc'

    user_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user)
    delegate_user_id = fields.Many2one('res.users', required=True)
    date_from = fields.Datetime(required=True)
    date_to = fields.Datetime(required=True)
    active = fields.Boolean(default=True)
    note = fields.Text()

    @api.constrains('date_from', 'date_to', 'user_id', 'delegate_user_id')
    def _check_dates(self):
        for rec in self:
            if rec.date_to <= rec.date_from:
                raise ValidationError(_('End date must be after start date.'))
            if rec.user_id == rec.delegate_user_id:
                raise ValidationError(_('You cannot delegate approvals to yourself.'))
