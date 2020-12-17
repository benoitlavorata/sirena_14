# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added Amazon Fulfillment center class to store the amazon center details
"""
from odoo import models, fields, api


class AmazonFulfillmentCenter(models.Model):
    """
    Added class to store the fulfillment center details
    """
    _name = "amazon.fulfillment.center"
    _description = 'amazon.fulfillment.center'
    _rec_name = 'center_code'

    @api.depends('warehouse_id', 'warehouse_id.seller_id')
    def _compute_seller_id(self):
        if self.warehouse_id and self.warehouse_id.seller_id:
            self.seller_id = self.warehouse_id.seller_id.id

    center_code = fields.Char(size=50, string='Fulfillment Center Code', required=True)
    warehouse_id = fields.Many2one('stock.warehouse', string='Warehouse')
    seller_id = fields.Many2one('amazon.seller.ept', string='Amazon Seller',
                                compute="_compute_seller_id", store=True,
                                readonly=True)

    _sql_constraints = [('fulfillment_center_unique_constraint', 'unique(seller_id,center_code)',
                         "Fulfillment center must be unique by seller.")]
