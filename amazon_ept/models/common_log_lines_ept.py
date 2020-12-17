# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Inherited class to create log lines and relate with the queue log record
"""
from odoo import models, fields, api, _


class CommonLogLineEpt(models.Model):
    """
    Inherited class to add common method to create order and product log lines and relate with
    the order queue
    """
    _inherit = "common.log.lines.ept"

    order_queue_data_id = fields.Many2one('shipped.order.data.queue.ept',
                                          string='Shipped Order Data Queue')

    def amazon_create_product_log_line(self, message, model_id, product_id, default_code, log_rec):
        """
        will creates and product log line
        """
        transaction_vals = {'default_code': default_code,
                            'model_id': model_id,
                            'product_id': product_id and product_id.id or False,
                            'res_id': product_id and product_id.id or False,
                            'message': message,
                            'log_book_id': log_rec and log_rec.id or False}
        log_line = self.create(transaction_vals)
        return log_line

    def amazon_create_order_log_line(self, message, model_id, res_id, order_ref, default_code,
                                     log_rec):
        """
        will creates an order log line
        """
        transaction_vals = {'message': message,
                            'model_id': model_id,
                            'res_id': res_id or False,
                            'order_ref': order_ref,
                            'default_code': default_code,
                            'log_book_id': log_rec and log_rec.id or False}
        log_line = self.create(transaction_vals)
        return log_line

    def amazon_create_common_log_line_ept(self, message, model_id, res_id, log_rec):
        transaction_vals = {'message': message,
                            'model_id': model_id,
                            'res_id': res_id or False,
                            'log_book_id': log_rec and log_rec.id or False}
        log_line = self.create(transaction_vals)
        return log_line
