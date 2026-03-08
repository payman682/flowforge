from odoo import api, fields, models, _
from odoo.exceptions import UserError, ValidationError
import json
import logging

_logger = logging.getLogger(__name__)


class FlowforgeApprovalRule(models.Model):
    _name = 'flowforge.approval.rule'
    _description = 'Approval Rule'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'sequence, id'

    name = fields.Char(required=True, tracking=True)
    active = fields.Boolean(default=True, tracking=True)
    sequence = fields.Integer(default=10)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    model_id = fields.Many2one('ir.model', required=True, ondelete='cascade', tracking=True)
    model_name = fields.Char(related='model_id.model', store=True)
    description = fields.Html()
    trigger = fields.Selection([
        ('create', 'On Create'),
        ('write', 'On Update'),
        ('manual', 'Manual Submission'),
    ], default='manual', required=True)
    domain = fields.Char(
        string='Rule Domain',
        help="Python-like domain in JSON form. Example: [['amount_total', '>', 1000]]",
        tracking=True,
    )
    mandatory_before_action = fields.Boolean(default=True, tracking=True)
    auto_submit = fields.Boolean(default=False)
    lock_record = fields.Boolean(default=True)
    allow_delegate = fields.Boolean(default=True)
    allow_request_changes = fields.Boolean(default=True)
    approval_mode = fields.Selection([
        ('sequential', 'Sequential'),
        ('parallel', 'Parallel'),
    ], default='sequential', required=True)
    stage_ids = fields.One2many('flowforge.approval.stage', 'rule_id', string='Stages', copy=True)
    action_ids = fields.One2many('flowforge.approval.action', 'rule_id', string='Post Approval Actions', copy=True)
    template_id = fields.Many2one('flowforge.approval.template')
    request_count = fields.Integer(compute='_compute_request_count')

    @api.depends('model_id')
    def _compute_request_count(self):
        grouped = self.env['flowforge.approval.request'].read_group(
            [('rule_id', 'in', self.ids)], ['rule_id'], ['rule_id']
        )
        mapping = {g['rule_id'][0]: g['rule_id_count'] for g in grouped}
        for rec in self:
            rec.request_count = mapping.get(rec.id, 0)

    @api.constrains('stage_ids')
    def _check_stage_ids(self):
        for rule in self:
            if not rule.stage_ids:
                raise ValidationError(_('Each rule must define at least one stage.'))
            seqs = rule.stage_ids.mapped('sequence')
            if len(seqs) != len(set(seqs)):
                raise ValidationError(_('Stage sequence values must be unique per rule.'))

    def action_open_requests(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Approval Requests'),
            'res_model': 'flowforge.approval.request',
            'view_mode': 'list,form',
            'domain': [('rule_id', '=', self.id)],
        }

    def _parse_domain(self):
        self.ensure_one()
        if not self.domain:
            return []
        try:
            parsed = json.loads(self.domain)
        except Exception as exc:
            raise ValidationError(_('Invalid JSON domain on rule %s: %s') % (self.display_name, exc))
        if not isinstance(parsed, list):
            raise ValidationError(_('Domain must be a JSON list.'))
        return parsed

    def matches_record(self, record):
        self.ensure_one()
        if self.model_name != record._name:
            return False
        domain = self._parse_domain()
        if not domain:
            return True
        return bool(record.search_count([('id', '=', record.id)] + domain))

    def get_stage_for_level(self, level):
        self.ensure_one()
        stages = self.stage_ids.sorted('sequence')
        return stages[level - 1] if level <= len(stages) else False

    def submit_record_for_approval(self, record):
        self.ensure_one()
        if not self.matches_record(record):
            raise UserError(_('This rule does not match the selected record.'))
        existing = self.env['flowforge.approval.request'].search([
            ('res_model', '=', record._name),
            ('res_id', '=', record.id),
            ('rule_id', '=', self.id),
            ('state', 'in', ['draft', 'pending', 'changes_requested'])
        ], limit=1)
        if existing:
            return existing
        request = self.env['flowforge.approval.request'].create({
            'name': self.env['ir.sequence'].next_by_code('flowforge.approval.request') or _('New'),
            'rule_id': self.id,
            'company_id': record.company_id.id if hasattr(record, 'company_id') and record.company_id else self.env.company.id,
            'res_model': record._name,
            'res_id': record.id,
            'requested_by_id': self.env.user.id,
            'state': 'pending',
            'current_level': 1,
        })
        request._bootstrap_lines()
        request._notify_current_approvers()
        request._log_event('submitted', _('Approval request submitted.'))
        return request


class FlowforgeApprovalStage(models.Model):
    _name = 'flowforge.approval.stage'
    _description = 'Approval Stage'
    _order = 'sequence, id'

    rule_id = fields.Many2one('flowforge.approval.rule', required=True, ondelete='cascade')
    name = fields.Char(required=True)
    sequence = fields.Integer(default=10)
    min_approvals = fields.Integer(default=1)
    approval_type = fields.Selection([
        ('all', 'All Approvers Must Approve'),
        ('min', 'Minimum Number of Approvals'),
        ('any', 'Any One Approver'),
    ], default='all', required=True)
    approver_source = fields.Selection([
        ('users', 'Specific Users'),
        ('groups', 'Group Users'),
        ('manager', 'Employee Manager'),
        ('field_user', 'User from Record Field'),
    ], default='users', required=True)
    approver_ids = fields.Many2many('res.users', 'flowforge_stage_user_rel', 'stage_id', 'user_id')
    group_ids = fields.Many2many('res.groups', 'flowforge_stage_group_rel', 'stage_id', 'group_id')
    user_field_name = fields.Char(help='Technical name of many2one field to res.users on target model')
    deadline_hours = fields.Integer(default=24)
    allow_delegate = fields.Boolean(default=True)
    require_comment_on_reject = fields.Boolean(default=True)
    notify_template = fields.Char(help='Optional mail template XML ID for custom notifications')

    @api.constrains('min_approvals', 'approval_type')
    def _check_min(self):
        for rec in self:
            if rec.approval_type == 'min' and rec.min_approvals < 1:
                raise ValidationError(_('Minimum approvals must be at least 1.'))

    def _resolve_approvers(self, target_record):
        self.ensure_one()
        users = self.env['res.users']
        if self.approver_source == 'users':
            users |= self.approver_ids
        elif self.approver_source == 'groups':
            users |= self.group_ids.mapped('users')
        elif self.approver_source == 'manager':
            partner = getattr(target_record, 'employee_id', False) or getattr(target_record, 'employee_ids', False)
            employee = partner[:1] if partner else False
            users |= employee.parent_id.user_id if employee and employee.parent_id and employee.parent_id.user_id else self.env['res.users']
        elif self.approver_source == 'field_user' and self.user_field_name:
            candidate = getattr(target_record, self.user_field_name, False)
            if candidate and candidate._name == 'res.users':
                users |= candidate
        return users.filtered(lambda u: u.active)


class FlowforgeApprovalAction(models.Model):
    _name = 'flowforge.approval.action'
    _description = 'Approval Action'
    _order = 'sequence, id'

    rule_id = fields.Many2one('flowforge.approval.rule', required=True, ondelete='cascade')
    sequence = fields.Integer(default=10)
    name = fields.Char(required=True)
    action_type = fields.Selection([
        ('activity', 'Create Activity'),
        ('email', 'Post Chatter Message'),
        ('write', 'Write Field Value'),
        ('server', 'Execute Server Action'),
    ], default='activity', required=True)
    field_name = fields.Char()
    value_text = fields.Char(help='Used for write actions')
    activity_type_id = fields.Many2one('mail.activity.type')
    summary = fields.Char()
    server_action_id = fields.Many2one('ir.actions.server')

    def execute(self, request):
        request.ensure_one()
        target = request.get_target_record()
        for action in self:
            if action.action_type == 'activity':
                target.activity_schedule(
                    activity_type_id=action.activity_type_id.id or self.env.ref('mail.mail_activity_data_todo').id,
                    summary=action.summary or _('Approved workflow follow-up'),
                    user_id=request.requested_by_id.id,
                )
            elif action.action_type == 'email':
                body = action.summary or _('Approval workflow completed for %s') % target.display_name
                target.message_post(body=body, subtype_xmlid='mail.mt_note')
            elif action.action_type == 'write':
                if not action.field_name:
                    raise UserError(_('Field name is required for write actions.'))
                target.sudo().write({action.field_name: action.value_text})
            elif action.action_type == 'server':
                if action.server_action_id:
                    action.server_action_id.with_context(active_model=target._name, active_id=target.id, active_ids=[target.id]).run()
