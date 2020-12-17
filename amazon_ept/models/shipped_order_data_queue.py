# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added shipped order data queue class to check the imported shipped order data and processed orders
from the shipped queue record.
"""

from odoo import models, fields, api


class ShippedOrderDataQueue(models.Model):
    """
    Added class to store the shipped order information and process  shipped orders via created via
    """
    _name = "shipped.order.data.queue.ept"
    _description = 'Shipped Order Data Queue Ept'
    _order = "create_date desc"

    def _compute_queue_line_record(self):
        """
        This is used for count of total record of product queue line.
        :return: count
        """
        for order_queue in self:
            order_queue.queue_line_total_record = len(order_queue.shipped_order_data_queue_lines)
            order_queue.queue_line_draft_record = len(
                order_queue.shipped_order_data_queue_lines.filtered(lambda x: x.state == 'draft'))
            order_queue.queue_line_fail_record = len(
                order_queue.shipped_order_data_queue_lines.filtered(lambda x: x.state == 'failed'))
            order_queue.queue_line_done_record = len(
                order_queue.shipped_order_data_queue_lines.filtered(lambda x: x.state == 'done'))

    def _compute_total_logs(self):
        """
        Find all stock moves associated with this report
        :return:
        """
        model_id = self.env['ir.model']._get('shipped.order.data.queue.ept').id
        log_obj = self.env['common.log.book.ept']
        self.log_count = log_obj.search_count( \
            [('res_id', '=', self.id), ('model_id', '=', model_id)])

    name = fields.Char(size=120, string='Name')
    amz_seller_id = fields.Many2one('amazon.seller.ept', string='Amazon Seller',
                                    help="Unique Amazon Seller name")
    state = fields.Selection(
        [('draft', 'Draft'), ('partially_completed', 'Partially Completed'),
         ('completed', 'Completed')],
        default='draft')
    shipped_order_data_queue_lines = fields.One2many('shipped.order.data.queue.line.ept',
                                                     'shipped_order_data_queue_id',
                                                     string="Shipped Order Queue Lines")
    log_lines = fields.One2many('common.log.lines.ept', 'order_queue_data_id',
                                compute="_compute_log_lines", string="Log Lines")

    queue_line_total_record = fields.Integer(string='Total Records',
                                             compute='_compute_queue_line_record')
    queue_line_draft_record = fields.Integer(string='Draft Records',
                                             compute='_compute_queue_line_record')
    queue_line_fail_record = fields.Integer(string='Fail Records',
                                            compute='_compute_queue_line_record')
    queue_line_done_record = fields.Integer(string='Done Records',
                                            compute='_compute_queue_line_record')
    log_count = fields.Integer(compute="_compute_total_logs", string="Move Count",
                               help="Count number of created Stock Move", store=False)

    @api.model
    def create(self, vals):
        """
        This method used to create a sequence for Shipped Order data.
        :param vals: value from base method
        :return: True
        """
        seq = self.env['ir.sequence'].next_by_code(
            'fbm_shipped_order_data_queue_ept_sequence') or '/'
        vals['name'] = seq
        return super(ShippedOrderDataQueue, self).create(vals)

    def action_product_queue_record_count(self):
        """
        This method used to display the product queue records.
        """
        return True

    def _compute_log_lines(self):
        """
        List Shipped Orders Logs
        @author: Twinkal Chandarana
        :return:
        """
        for queue in self:
            log_book_obj = self.env['common.log.book.ept']
            model_id = self.env['ir.model']._get('shipped.order.data.queue.ept').id
            domain = [('res_id', '=', queue.id), ('model_id', '=', model_id)]
            log_book_id = log_book_obj.search(domain)
            queue.log_lines = log_book_id and log_book_id.log_lines.ids or False

    def process_orders(self):
        """
        This method is process the orders that are in queue.
        :return:
        """
        sale_order_obj = self.env['sale.order']
        common_log_book_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('shipped.order.data.queue.ept').id
        if not self:
            shipped_order_data_queues = self.search([('state', '=', 'draft')])
        else:
            shipped_order_data_queues = self
        for data_queue in shipped_order_data_queues:
            log_book = common_log_book_obj.search( \
                [('model_id', '=', model_id),
                 ('res_id', '=', data_queue.id)])
            if not log_book:
                log_book = common_log_book_obj.amazon_create_transaction_log( \
                    'import', model_id, data_queue.id)

            sale_order_obj.amz_create_sales_order(data_queue, log_book)
            status = data_queue.shipped_order_data_queue_lines.filtered(lambda x: x.state != 'done')
            if status:
                # Delete Done data queue lines for compliance of Amazon Rules
                data_queue.shipped_order_data_queue_lines.filtered(
                    lambda x: x.state == 'done').unlink()
                data_queue.write({'state': 'partially_completed'})
            else:
                # Delete Processed Data Queue
                data_queue.unlink()
            self._cr.commit()
        return True
