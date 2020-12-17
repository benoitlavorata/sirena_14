"""
This File will perform the settlement report's  bank statement operations and inherited
methods to update the settlement report state when bank statement state is updated.
"""

# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields


class AccountBankStatement(models.Model):
    """
    Inherited AccountBankStatement class to process settlement report's statement
    """
    _inherit = 'account.bank.statement'

    settlement_ref = fields.Char(size=350, string='Amazon Settlement Ref')

    def button_validate_or_action(self):
        """
        Migration done by twinkalc on 28 sep, 2020,Inherited to update the state of settlement
        report to validated.
        """
        if self.settlement_ref:
            settlement = self.env['settlement.report.ept'].search([('statement_id', '=', self.id)])
            settlement.write({'state': 'confirm'})
        return super(AccountBankStatement, self).button_validate_or_action()

    def button_reprocess(self):
        """
        Added by twinkalc on 28 sep, 2020, Inherited to update the state of settlement report to
        processed if bank statement is reprocessed.
        """
        if self.settlement_ref:
            settlement = self.env['settlement.report.ept'].search([('statement_id', '=', self.id)])
            settlement.write({'state': 'processed'})
        return super(AccountBankStatement, self).button_reprocess()

    def button_reopen(self):
        """
        Added by twinkalc on 28 sep, 2020,Inherited to update the state of settlement report to
        imported if bank statement is reopened.
        """
        if self.settlement_ref:
            settlement = self.env['settlement.report.ept'].search([('statement_id', '=', self.id)])
            settlement.write({'state': 'imported'})
        return super(AccountBankStatement, self).button_reopen()
