from odoo.tests.common import TransactionCase


class TestFlowforgeApproval(TransactionCase):

    def test_rule_creation(self):
        model = self.env['ir.model']._get('res.partner')
        rule = self.env['flowforge.approval.rule'].create({
            'name': 'Partner Approval',
            'model_id': model.id,
            'stage_ids': [(0, 0, {
                'name': 'Admin Approval',
                'sequence': 1,
                'approver_source': 'users',
                'approver_ids': [(6, 0, [self.env.user.id])],
            })],
        })
        self.assertTrue(rule)
