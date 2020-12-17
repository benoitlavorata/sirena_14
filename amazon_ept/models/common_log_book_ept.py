# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Inherited class to add common method to create amazon transaction logs
"""

from odoo import models


class CommonLogBookEpt(models.Model):
    """
    Inherited class to store define the common method to create log
    """
    _inherit = 'common.log.book.ept'

    def amazon_create_transaction_log(self, type, model_id, res_id):
        """
        will create an amazon log rec
        """
        log_vals = {
            'active': True,
            'model_id': model_id,
            'type': type,
            'res_id': res_id,
            'module': 'amazon_ept'
        }
        log_rec = self.create(log_vals)
        return log_rec
