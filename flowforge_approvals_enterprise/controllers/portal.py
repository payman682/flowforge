from odoo import http, _
from odoo.http import request


class FlowforgeApprovalPortal(http.Controller):

    @http.route('/flowforge/approval/<string:token>', type='http', auth='public', website=True)
    def approval_portal(self, token, action=None, **kwargs):
        approval = request.env['flowforge.approval.request'].sudo().search([('token', '=', token)], limit=1)
        if not approval:
            return request.not_found()
        if action in ('approve', 'reject', 'changes'):
            if action == 'approve':
                approval.with_user(approval.pending_user_ids[:1]).action_approve(comment=_('Approved via secure link'))
            elif action == 'reject':
                approval.with_user(approval.pending_user_ids[:1]).action_reject(comment=_('Rejected via secure link'))
            else:
                approval.with_user(approval.pending_user_ids[:1]).action_request_changes(comment=_('Changes requested via secure link'))
        return request.render('flowforge_approvals_enterprise.portal_approval_page', {'approval': approval})
