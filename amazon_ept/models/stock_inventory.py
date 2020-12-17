# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Inherited stock inventory class to relate with the amazon instance and fba live stock report.
"""

from odoo import models, fields


class StockInventory(models.Model):
    """
    Inherited stock inventory class to relate with the amazon instance and fba live stock report.
    """
    _inherit = 'stock.inventory'

    amazon_instance_id = fields.Many2one('amazon.instance.ept', string='Instance')
    fba_live_stock_report_id = fields.Many2one('amazon.fba.live.stock.report.ept',
                                               "FBA Live Inventory Report")
