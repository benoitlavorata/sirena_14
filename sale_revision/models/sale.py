# -*- coding: utf-8 -*-

from odoo import fields, models, api, _
from datetime import datetime


class SaleOrder(models.Model):
    _inherit = "sale.order"

    state = fields.Selection(selection_add=[('revise', 'Revised')])
    revision_no = fields.Integer('Revision Number', default=0, copy=False)
    revised_so_id = fields.Many2one('sale.order', 'Revised From', copy=False)
    new_revised_so_id = fields.Many2one('sale.order', 'Revised To', copy=False)

    def revise_sale_order(self):
        if self.revised_so_id:
            name = self.name.split('-')[0]+'-R'+str(self.revision_no+1)
        else:
            name = self.name+'-'+'R'+str(self.revision_no+1)
        values = {
            'state': 'draft',
            'name': name,
            'revised_so_id': self.id,
            'revision_no': self.revision_no+1,
        }
        rev_order_id = self.copy(default=values)
        self.write({
            'state': 'revise',
            'new_revised_so_id': self.id
        })
        return {
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'sale.order',
            'res_id' : rev_order_id.id,
            'type': 'ir.actions.act_window',
        }

