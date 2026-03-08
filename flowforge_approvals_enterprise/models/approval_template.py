from odoo import fields, models


class FlowforgeApprovalTemplate(models.Model):
    _name = 'flowforge.approval.template'
    _description = 'Approval Template'
    _inherit = ['mail.thread']

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True)
    category = fields.Selection([
        ('finance', 'Finance'),
        ('sales', 'Sales'),
        ('purchase', 'Purchase'),
        ('hr', 'Human Resources'),
        ('operations', 'Operations'),
        ('generic', 'Generic'),
    ], default='generic', required=True)
    note = fields.Html()
    rule_ids = fields.One2many('flowforge.approval.rule', 'template_id')
