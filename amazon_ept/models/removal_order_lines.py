# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

from odoo import models, fields, api


class RemovalOrderLines(models.Model):
    _name = "removal.orders.lines.ept"
    _description = "removal.orders.lines.ept"

    amazon_product_id = fields.Many2one('amazon.product.ept', string='Product',
                                        domain=[('fulfillment_by', '=', 'FBA')])
    seller_sku = fields.Char(size=120, string='Seller SKU', related="amazon_product_id.seller_sku",
                             readonly=True)
    sellable_quantity = fields.Float(digits="Product UoS")
    unsellable_quantity = fields.Float(digits="Product UoS")
    sellable_stock = fields.Float(digits="Product UoS",
                                  compute="_compute_sellable_unsellable_stock",
                                  multi="get_multi_stock", readonly=True)
    unsellable_stock = fields.Float(digits="Product UoS",
                                    compute="_compute_sellable_unsellable_stock",
                                    multi="get_multi_stock", readonly=True)
    removal_order_id = fields.Many2one("amazon.removal.order.ept", string="Removal Order")
    removal_disposition = fields.Selection([('Return', 'Return'), ('Disposal', 'Disposal')])

    def _compute_sellable_unsellable_stock(self):
        """
        This Method relocates get stock using line of amazon product id with context passed location
        of removal order of warehouse
        """
        for line in self:
            line.sellable_stock = line.amazon_product_id.product_id.with_context( \
                {
                    'location': line.removal_order_id.instance_id.warehouse_id.lot_stock_id.id}).qty_available
            line.unsellable_stock = line.amazon_product_id.product_id.with_context({
                'location': line.removal_order_id.instance_id.fba_warehouse_id.unsellable_location_id.id}).qty_available

    def onchange_product_id(self, removal_disposition):
        """
        This Method relocates if change product id check removal disposition and update sellable
         quantity.
        :param removal_disposition: This arguments relocates type of disposition(Return/Disposal).
        :return: This Method return updated value of sellable quantity.
        """
        vals = {'removal_disposition': removal_disposition}
        if removal_disposition == 'Disposal':
            vals.update({'sellable_quantity': 0.0})
        return {'value': vals}
