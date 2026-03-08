from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from datetime import timedelta
import secrets


class FlowforgeApprovalRequest(models.Model):
    _name = 'flowforge.approval.request'
    _description = 'Approval Request'
    _inherit = ['mail.thread', 'mail.activity.mixin']
    _order = 'create_date desc, id desc'
    _rec_name = 'name'

    name = fields.Char(required=True, default=lambda self: _('New'), tracking=True)
    company_id = fields.Many2one('res.company', default=lambda self: self.env.company, index=True)
    rule_id = fields.Many2one('flowforge.approval.rule', required=True, ondelete='restrict', tracking=True)
    res_model = fields.Char(required=True, index=True)
    res_id = fields.Integer(required=True, index=True)
    res_ref = fields.Reference(selection='_referenceable_models', compute='_compute_res_ref', store=False)
    requested_by_id = fields.Many2one('res.users', required=True, default=lambda self: self.env.user, tracking=True)
    state = fields.Selection([
        ('draft', 'Draft'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('changes_requested', 'Changes Requested'),
        ('cancelled', 'Cancelled'),
    ], default='draft', tracking=True, index=True)
    current_level = fields.Integer(default=1, tracking=True)
    line_ids = fields.One2many('flowforge.approval.line', 'request_id', copy=False)
    log_ids = fields.One2many('flowforge.approval.log', 'request_id', copy=False)
    due_date = fields.Datetime(tracking=True)
    token = fields.Char(default=lambda self: secrets.token_urlsafe(24), copy=False)
    target_display_name = fields.Char(compute='_compute_target_display_name')
    pending_user_ids = fields.Many2many('res.users', compute='_compute_pending_users')
    can_current_user_approve = fields.Boolean(compute='_compute_can_current_user_approve')

    @api.depends('res_model', 'res_id')
    def _compute_target_display_name(self):
        for rec in self:
            target = rec.get_target_record(safe=True)
            rec.target_display_name = target.display_name if target else '%s,%s' % (rec.res_model, rec.res_id)

    @api.depends('line_ids.state', 'line_ids.user_id', 'state')
    def _compute_pending_users(self):
        for rec in self:
            rec.pending_user_ids = rec.line_ids.filtered(lambda l: l.state == 'pending').mapped('user_id')

    @api.depends('pending_user_ids', 'state')
    def _compute_can_current_user_approve(self):
        user = self.env.user
        for rec in self:
            rec.can_current_user_approve = rec.state == 'pending' and user in rec.pending_user_ids

    def _referenceable_models(self):
        models = self.env['ir.model'].sudo().search([])
        return [(m.model, m.name) for m in models]

    def _compute_res_ref(self):
        for rec in self:
            rec.res_ref = '%s,%s' % (rec.res_model, rec.res_id) if rec.res_model and rec.res_id else False

    def get_target_record(self, safe=False):
        self.ensure_one()
        record = self.env[self.res_model].browse(self.res_id)
        if not safe and not record.exists():
            raise UserError(_('The target record no longer exists.'))
        return record.exists() if safe else record

    def _bootstrap_lines(self):
        for request in self:
            target = request.get_target_record()
            lines = []
            for stage in request.rule_id.stage_ids.sorted('sequence'):
                approvers = stage._resolve_approvers(target)
                if not approvers:
                    raise ValidationError(_('No approvers resolved for stage %s') % stage.name)
                for user in approvers:
                    lines.append((0, 0, {
                        'stage_id': stage.id,
                        'sequence': stage.sequence,
                        'user_id': user.id,
                        'state': 'pending' if stage.sequence == request.rule_id.stage_ids.sorted('sequence')[0].sequence else 'waiting',
                        'deadline': fields.Datetime.now() + timedelta(hours=stage.deadline_hours or 24),
                    }))
            request.line_ids = lines
            current_stage = request.rule_id.get_stage_for_level(1)
            request.due_date = fields.Datetime.now() + timedelta(hours=current_stage.deadline_hours or 24)

    def _notify_current_approvers(self):
        for request in self:
            for user in request.pending_user_ids:
                request.activity_schedule(
                    'mail.mail_activity_data_todo',
                    user_id=user.id,
                    summary=_('Approval required: %s') % request.target_display_name,
                    note=_('Please review the approval request %s.') % request.name,
                )
                request.message_post(body=_('Approval request awaiting action from %s') % user.display_name)

    def _log_event(self, action, note=''):
        for request in self:
            self.env['flowforge.approval.log'].create({
                'request_id': request.id,
                'action': action,
                'user_id': self.env.user.id,
                'note': note,
            })

    def _ensure_can_approve(self):
        for request in self:
            if self.env.user not in request.pending_user_ids and not self.env.user.has_group('flowforge_approvals_enterprise.group_flowforge_admin'):
                raise AccessError(_('You are not allowed to approve this request.'))

    def action_approve(self, comment=False):
        self._ensure_can_approve()
        for request in self:
            pending_lines = request.line_ids.filtered(lambda l: l.user_id == self.env.user and l.state == 'pending')
            if not pending_lines:
                raise UserError(_('No pending approval line found for your user.'))
            pending_lines.write({'state': 'approved', 'comment': comment or False, 'action_date': fields.Datetime.now()})
            request._log_event('approved', comment or _('Approved by %s') % self.env.user.display_name)
            request._advance_if_stage_complete()
        return True

    def action_reject(self, comment=False):
        self._ensure_can_approve()
        for request in self:
            current_stage = request._current_stage()
            if current_stage.require_comment_on_reject and not comment:
                raise UserError(_('A rejection comment is required.'))
            request.line_ids.filtered(lambda l: l.user_id == self.env.user and l.state == 'pending').write({
                'state': 'rejected', 'comment': comment or False, 'action_date': fields.Datetime.now()
            })
            request.line_ids.filtered(lambda l: l.state in ('pending', 'waiting')).write({'state': 'cancelled'})
            request.state = 'rejected'
            request._log_event('rejected', comment or _('Rejected by %s') % self.env.user.display_name)
            request.message_post(body=_('Approval rejected by %s') % self.env.user.display_name)
        return True

    def action_request_changes(self, comment=False):
        self._ensure_can_approve()
        for request in self:
            if not request.rule_id.allow_request_changes:
                raise UserError(_('This rule does not allow requesting changes.'))
            request.line_ids.filtered(lambda l: l.user_id == self.env.user and l.state == 'pending').write({
                'state': 'changes_requested', 'comment': comment or False, 'action_date': fields.Datetime.now()
            })
            request.line_ids.filtered(lambda l: l.state == 'waiting').write({'state': 'cancelled'})
            request.state = 'changes_requested'
            request._log_event('changes_requested', comment or _('Changes requested by %s') % self.env.user.display_name)
        return True

    def action_cancel(self):
        for request in self:
            if self.env.user != request.requested_by_id and not self.env.user.has_group('flowforge_approvals_enterprise.group_flowforge_admin'):
                raise AccessError(_('Only the requester or an administrator can cancel this request.'))
            request.line_ids.filtered(lambda l: l.state in ('pending', 'waiting')).write({'state': 'cancelled'})
            request.state = 'cancelled'
            request._log_event('cancelled', _('Request cancelled.'))
        return True

    def action_resubmit(self):
        for request in self.filtered(lambda r: r.state == 'changes_requested'):
            request.line_ids.unlink()
            request.state = 'pending'
            request.current_level = 1
            request._bootstrap_lines()
            request._notify_current_approvers()
            request._log_event('resubmitted', _('Request resubmitted after changes.'))
        return True

    def _current_stage(self):
        self.ensure_one()
        return self.rule_id.get_stage_for_level(self.current_level)

    def _advance_if_stage_complete(self):
        for request in self:
            stage = request._current_stage()
            stage_lines = request.line_ids.filtered(lambda l: l.sequence == stage.sequence)
            approved_count = len(stage_lines.filtered(lambda l: l.state == 'approved'))
            if stage.approval_type == 'all' and approved_count < len(stage_lines):
                continue
            if stage.approval_type == 'any' and approved_count < 1:
                continue
            if stage.approval_type == 'min' and approved_count < stage.min_approvals:
                continue
            waiting_same_stage = stage_lines.filtered(lambda l: l.state in ('pending', 'waiting'))
            waiting_same_stage.write({'state': 'skipped'})
            next_stage = request.rule_id.get_stage_for_level(request.current_level + 1)
            if next_stage:
                request.current_level += 1
                next_lines = request.line_ids.filtered(lambda l: l.sequence == next_stage.sequence and l.state == 'waiting')
                next_lines.write({'state': 'pending'})
                request.due_date = fields.Datetime.now() + timedelta(hours=next_stage.deadline_hours or 24)
                request.message_post(body=_('Workflow advanced to stage: %s') % next_stage.name)
                request._notify_current_approvers()
            else:
                request.state = 'approved'
                request.due_date = False
                request.message_post(body=_('Approval workflow completed.'))
                request._log_event('completed', _('Request fully approved.'))
                for action in request.rule_id.action_ids.sorted('sequence'):
                    action.execute(request)

    @api.model
    def cron_process_escalations(self):
        overdue_requests = self.search([('state', '=', 'pending'), ('due_date', '!=', False), ('due_date', '<', fields.Datetime.now())])
        for request in overdue_requests:
            request.message_post(body=_('Approval SLA breached for stage %s') % request._current_stage().name)
            request._log_event('escalated', _('Escalation triggered by scheduled job.'))


class FlowforgeApprovalLine(models.Model):
    _name = 'flowforge.approval.line'
    _description = 'Approval Line'
    _order = 'sequence, id'

    request_id = fields.Many2one('flowforge.approval.request', required=True, ondelete='cascade')
    stage_id = fields.Many2one('flowforge.approval.stage', required=True)
    sequence = fields.Integer(index=True)
    user_id = fields.Many2one('res.users', required=True, index=True)
    state = fields.Selection([
        ('waiting', 'Waiting'),
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
        ('changes_requested', 'Changes Requested'),
        ('cancelled', 'Cancelled'),
        ('skipped', 'Skipped'),
    ], default='waiting', index=True)
    deadline = fields.Datetime()
    action_date = fields.Datetime()
    comment = fields.Text()
