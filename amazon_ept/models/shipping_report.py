# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

import time
from datetime import datetime, timedelta
import base64
import csv
from io import StringIO
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.iap.tools import iap_tools
from ..endpoint import DEFAULT_ENDPOINT


class ShippingReportRequestHistory(models.Model):
    _name = "shipping.report.request.history"
    _description = "Shipping Report"
    _inherit = ['mail.thread']
    _order = 'id desc'

    @api.depends('seller_id')
    def _compute_company(self):
        """
        Find Company id on change of seller
        :return:  company_id
        """
        for record in self:
            company_id = record.seller_id.company_id.id if record.seller_id else False
            if not company_id:
                company_id = self.env.company.id
            record.company_id = company_id

    def _compute_total_orders(self):
        """
        Get number of orders processed in the report
        :return:
        """
        self.order_count = len(self.amazon_sale_order_ids.ids)

    def _compute_total_moves(self):
        """
        Find all stock moves assiciated with this report
        :return:
        """
        stock_move_obj = self.env['stock.move']
        self.moves_count = stock_move_obj.search_count([('amz_shipment_report_id', '=', self.id)])

    def _compute_total_logs(self):
        """
        Find all stock moves associated with this report
        :return:
        """
        log_obj = self.env['common.log.book.ept']
        model_id = self.env['ir.model']._get('shipping.report.request.history').id
        self.log_count = log_obj.search_count(
            [('res_id', '=', self.id), ('model_id', '=', model_id)])

    name = fields.Char(size=256)
    state = fields.Selection(
        [('draft', 'Draft'), ('_SUBMITTED_', 'SUBMITTED'), ('_IN_PROGRESS_', 'IN_PROGRESS'),
         ('_CANCELLED_', 'CANCELLED'), ('_DONE_', 'DONE'),
         ('partially_processed', 'Partially Processed'),
         ('_DONE_NO_DATA_', 'DONE_NO_DATA'), ('processed', 'PROCESSED')],
        string='Report Status', default='draft', help="Report Processing States")
    attachment_id = fields.Many2one('ir.attachment', string="Attachment",
                                    help="Find Shipping report from odoo Attachment")
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False,
                                help="Select Seller id from you wanted to get Shipping report")
    report_request_id = fields.Char(size=256, string='Report Request ID',
                                    help="Report request id to recognise unique request")
    report_id = fields.Char(size=256, string='Report ID',
                            help="Unique Report id for recognise report in Odoo")
    report_type = fields.Char(size=256, help="Amazon Report Type")
    start_date = fields.Datetime(help="Report Start Date")
    end_date = fields.Datetime(help="Report End Date")
    requested_date = fields.Datetime(default=time.strftime("%Y-%m-%d %H:%M:%S"),
                                     help="Report Requested Date")
    company_id = fields.Many2one('res.company', string="Company", copy=False,
                                 compute="_compute_company", store=True)
    user_id = fields.Many2one('res.users', string="Requested User",
                              help="Track which odoo user has requested report")
    amazon_sale_order_ids = fields.One2many('sale.order', 'amz_shipment_report_id',
                                            string="Sales Order Ids",
                                            help="For list all Orders created while shipment"
                                                 "report process")
    order_count = fields.Integer(compute="_compute_total_orders", store=False,
                                 help="Count number of processed orders")
    moves_count = fields.Integer(compute="_compute_total_moves", string="Move Count", store=False,
                                 help="Count number of created Stock Move")
    log_count = fields.Integer(compute="_compute_total_logs", store=False,
                               help="Count number of created Stock Move")
    is_fulfillment_center = fields.Boolean(default=False,
                                           help="if missing fulfillment center get then set as True")

    def unlink(self):
        """
        This Method if report is processed then raise UserError.
        """
        for report in self:
            if report.state == 'processed' or report.state == 'partially_processed':
                raise UserError(_('You cannot delete processed report.'))
        return super(ShippingReportRequestHistory, self).unlink()

    @api.constrains('start_date', 'end_date')
    def _check_duration(self):
        """
        Compare Start date and End date, If End date is before start date rate warning.
        @author: Keyur Kanani
        :return:
        """
        if self.start_date and self.end_date < self.start_date:
            raise UserError(_('Error!\nThe start date must be precede its end date.'))
        return True

    @api.model
    def default_get(self, fields):
        """
        Save report type when shipment report created
        @author: Keyur Kanani
        :param fields:
        :return:
        """
        res = super(ShippingReportRequestHistory, self).default_get(fields)
        if not fields:
            return res
        res.update({'report_type': '_GET_AMAZON_FULFILLED_SHIPMENTS_DATA_',
                    })
        return res

    def list_of_sales_orders(self):
        """
        List Amazon Sale Orders in Shipment View
        @author: Keyur Kanani
        :return:
        """
        action = {
            'domain': "[('id', 'in', " + str(self.amazon_sale_order_ids.ids) + " )]",
            'name': 'Amazon Sales Orders',
            'view_mode': 'tree,form',
            'res_model': 'sale.order',
            'type': 'ir.actions.act_window',
        }
        return action

    def list_of_process_logs(self):
        """
        List Shipment Report Log View
        @author: Keyur Kanani
        :return:
        """
        model_id = self.env['ir.model']._get('shipping.report.request.history').id
        action = {
            'domain': "[('res_id', '=', " + str(self.id) + " ), ('model_id','='," + str(
                model_id) + ")]",
            'name': 'Shipment Report Logs',
            'view_mode': 'tree,form',
            'res_model': 'common.log.book.ept',
            'type': 'ir.actions.act_window',
        }
        return action

    def list_of_stock_moves(self):
        """
        List All Stock Moves which is generated in a process
        @author: Keyur Kanani
        :return:
        """
        stock_move_obj = self.env['stock.move']
        records = stock_move_obj.search([('amz_shipment_report_id', '=', self.id)])
        action = {
            'domain': "[('id', 'in', " + str(records.ids) + " )]",
            'name': 'Amazon FBA Order Stock Move',
            'view_mode': 'tree,form',
            'res_model': 'stock.move',
            'type': 'ir.actions.act_window',
        }
        return action

    @api.model
    def create(self, vals):
        """
        Create Sequence for import Shipment Reports
        @author: Keyur Kanani
        :param vals: {}
        :return:
        """
        try:
            sequence = self.env.ref('amazon_ept.seq_import_shipping_report_job')
            if sequence:
                report_name = sequence.next_by_id()
            else:
                report_name = '/'
        except:
            report_name = '/'
        vals.update({'name': report_name})
        return super(ShippingReportRequestHistory, self).create(vals)

    @api.onchange('seller_id')
    def on_change_seller_id(self):
        """
        Set Start and End date of report as per seller configurations
        Default is 3 days
        @author: Keyur Kanani
        """
        if self.seller_id:
            self.start_date = datetime.now() - timedelta(self.seller_id.shipping_report_days)
            self.end_date = datetime.now()

    def prepare_amazon_request_report_kwargs(self, seller):
        """
        Prepare General Amazon Request dictionary.
        @author: Keyur Kanani
        :param seller: amazon.seller.ept()
        :return: {}
        """
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        instances_obj = self.env['amazon.instance.ept']
        instances = instances_obj.search([('seller_id', '=', seller.id)])
        marketplaceids = tuple(map(lambda x: x.market_place_id, instances))

        return {'merchant_id': seller.merchant_id and str(seller.merchant_id) or False,
                'auth_token': seller.auth_token and str(seller.auth_token) or False,
                'app_name': 'amazon_ept',
                'account_token': account.account_token,
                'dbuuid': dbuuid,
                'amazon_marketplace_code': seller.country_id.amazon_marketplace_code or
                                           seller.country_id.code,
                'marketplaceids': marketplaceids,
                }

    def report_start_and_end_date(self):
        """
        Prepare Start and End Date for request reports
        @author: Keyur Kanani
        :return: start_date, end_date
        """
        start_date, end_date = self.start_date, self.end_date
        time_format = "%Y-%m-%d %H:%M:%S.%f" if self._context.get('is_auto_process',
                                                                  '') else "%Y-%m-%d %H:%M:%S"
        if start_date:
            db_import_time = time.strptime(str(start_date), time_format)
            db_import_time = time.strftime("%Y-%m-%dT%H:%M:%S", db_import_time)
            start_date = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(
                time.mktime(time.strptime(db_import_time, "%Y-%m-%dT%H:%M:%S"))))
            start_date = str(start_date) + 'Z'
        else:
            today = datetime.now()
            earlier = today - timedelta(days=30)
            earlier_str = earlier.strftime("%Y-%m-%dT%H:%M:%S")
            start_date = earlier_str + 'Z'

        if end_date:
            db_import_time = time.strptime(str(end_date), time_format)
            db_import_time = time.strftime("%Y-%m-%dT%H:%M:%S", db_import_time)
            end_date = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(
                time.mktime(time.strptime(db_import_time, "%Y-%m-%dT%H:%M:%S"))))
            end_date = str(end_date) + 'Z'
        else:
            today = datetime.now()
            earlier_str = today.strftime("%Y-%m-%dT%H:%M:%S")
            end_date = earlier_str + 'Z'

        return start_date, end_date

    def request_report(self):
        """
        Request _GET_AMAZON_FULFILLED_SHIPMENTS_DATA_ Report from Amazon for specific date range.
        @author: Keyur Kanani
        :return: Boolean
        """
        seller, report_type = self.seller_id, self.report_type
        if not seller:
            raise UserError(_('Please select Seller'))

        start_date, end_date = self.report_start_and_end_date()

        kwargs = self.prepare_amazon_request_report_kwargs(seller)
        kwargs.update({
            'emipro_api': 'shipping_request_report_v13',
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
        })
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs,
                                         timeout=1000)
        if response.get('reason'):
            if self._context.get('is_auto_process'):
                self.amz_search_or_create_logs_ept(response.get('reason'))
            else:
                raise UserError(_(response.get('reason')))
        else:
            result = response.get('result')
            self.update_report_history(result)
        return True

    def update_report_history(self, request_result):
        """
        Update Report History in odoo
        @author: Keyur Kanani
        :param request_result:
        :return:
        """
        report_info = request_result.get('ReportInfo', {})
        report_request_info = request_result.get('ReportRequestInfo', {})
        request_id = report_state = report_id = False
        if report_request_info:
            request_id = str(report_request_info.get('ReportRequestId', {}).get('value', ''))
            report_state = report_request_info.get('ReportProcessingStatus', {}).get('value',
                                                                                     '_SUBMITTED_')
            report_id = report_request_info.get('GeneratedReportId', {}).get('value', False)
        elif report_info:
            report_id = report_info.get('ReportId', {}).get('value', False)
            request_id = report_info.get('ReportRequestId', {}).get('value', False)

        if report_state == '_DONE_' and not report_id:
            self.get_report_list()
        vals = {}
        if not self.report_request_id and request_id:
            vals.update({'report_request_id': request_id})
        if report_state:
            vals.update({'state': report_state})
        if report_id:
            vals.update({'report_id': report_id})
        self.write(vals)
        return True

    def get_report_list(self):
        """
        Call Get report list api from amazon
        @author: Keyur Kanani
        :return:
        """
        self.ensure_one()
        list_of_wrapper = []
        if not self.seller_id:
            raise UserError(_('Please select seller'))

        kwargs = self.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update({'emipro_api': 'get_report_list_v13', 'request_id': [self.request_id]})
        if not self.request_id:
            return True

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            if self._context.get('is_auto_process'):
                message = 'Shipping Report Process' + response.get('reason')
                self.amz_search_or_create_logs_ept(message)
            else:
                raise UserError(_(response.get('reason')))
        else:
            list_of_wrapper = response.get('result')

        for result in list_of_wrapper:
            self.update_report_history(result)
        return True

    def get_report_request_list(self):
        """
        Get Report Requests List from Amazon, Check Status of Process.
        @author: Keyur kanani
        :return: Boolean
        """
        self.ensure_one()
        if not self.seller_id:
            raise UserError(_('Please select Seller'))
        if not self.report_request_id:
            return True
        kwargs = self.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update(
            {'emipro_api': 'get_report_request_list_v13', 'request_ids': (self.report_request_id)})

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if not response.get('reason'):
            list_of_wrapper = response.get('result')
        else:
            raise UserError(_(response.get('reason')))
        for result in list_of_wrapper:
            self.update_report_history(result)
        return True

    def amz_search_or_create_logs_ept(self, message):
        common_log_book_obj = self.env['common.log.book.ept']
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = self.env['ir.model']._get( \
            'shipping.report.request.history').id

        log_rec = common_log_book_obj.search( \
            [('module', '=', 'amazon_ept'), ('model_id', '=', model_id), \
             ('res_id', '=', self.id)])
        if not log_rec:
            log_rec = common_log_book_obj.amazon_create_transaction_log('import', \
                                                                        model_id, self.id)
        if message:
            common_log_line_obj.amazon_create_order_log_line(message, model_id, \
                                                             self.id, False, False, log_rec)

        return log_rec

    def get_report(self):
        """
        Get Shipment Report as an attachment in Shipping reports form view.
        @author: Keyur kanani
        :return:
        """
        self.ensure_one()
        result = {}
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select seller'))
        if not self.report_id:
            return True
        kwargs = self.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update({'emipro_api': 'get_report_v13', 'report_id': self.report_id,
                       'amz_report_type': 'shipment_report'})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('reason'):
            if self._context.get('is_auto_process'):
                message = 'Shipping Report Process' + response.get('reason')
                self.amz_search_or_create_logs_ept(message)
            else:
                raise UserError(_(response.get('reason')))
        else:
            result = response.get('result')
        if result:
            file_name = "Shipment_report_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
            attachment = self.env['ir.attachment'].create({
                'name': file_name,
                'datas': result.encode(),
                'res_model': 'mail.compose.message',
                'type': 'binary'
            })
            self.message_post(body=_("<b>Shipment Report Downloaded</b>"),
                              attachment_ids=attachment.ids)
            """
            Get Missing Fulfillment Center from attachment file
            If get missing Fulfillment Center then set true value of field is_fulfillment_center
            @author: Deval Jagad (09/01/2020)
            """
            unavailable_fulfillment_center = self.get_missing_fulfillment_center(attachment)
            is_fulfillment_center = False
            if unavailable_fulfillment_center:
                is_fulfillment_center = True
            self.write(
                {'attachment_id': attachment.id, 'is_fulfillment_center': is_fulfillment_center})
        return True

    def download_report(self):
        """
        Download Shipment Report from Attachment
        @author: Keyur kanani
        :return: boolean
        """
        self.ensure_one()
        if self.attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % (self.attachment_id.id),
                'target': 'self',
            }
        return True

    def process_shipment_file(self):
        """
        Process Amazon Shipment File from attachment,
        Import FBA Sale Orders and Sale Order lines for specific amazon Instance
        Test Cases: https://docs.google.com/spreadsheets/d/1IcbZM7o7k4V4DccN3nbR_
        QpXnBBWbztjpglhpNQKC_c/edit?usp=sharing
        @author: Keyur kanani
        :return: True
        """
        self.ensure_one()
        ir_cron_obj = self.env['ir.cron']
        if not self._context.get('is_auto_process', False):
            ir_cron_obj.with_context({'raise_warning': True}).find_running_schedulers( \
                'ir_cron_process_amazon_fba_shipment_report_seller_', self.seller_id.id)

        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))

        common_log_line_obj = self.env['common.log.lines.ept']
        stock_move_obj = self.env['stock.move']
        instances = {}
        order_dict = {}
        order_details_dict_list = {}
        outbound_orders_dict = {}
        fulfillment_warehouse = {}
        skip_orders = []
        model_id = self.env['ir.model']._get('shipping.report.request.history').id

        message = 'Shipment Report Import Start'
        log_rec = self.amz_search_or_create_logs_ept(message)
        imp_file = self.decode_amazon_encrypted_attachments_data(self.attachment_id, log_rec)
        reader = csv.DictReader(imp_file, delimiter='\t')

        for row in reader:
            instance = self.get_instance_shipment_report_ept(row, instances)
            if not instance:
                message = 'Skipped Amazon order (%s) because Sales Channel (%s) not found in Odoo. ' % (
                    row.get('amazon-order-id'), row.get('sales-channel'))
                common_log_line_obj.amazon_create_order_log_line(message,
                                                                 model_id, self.id,
                                                                 row.get('amazon-order-id'), False,
                                                                 log_rec)
                continue
            where_clause = (row.get('shipment-id'), instance.id, row.get('amazon-order-id'),
                            row.get('amazon-order-item-id').lstrip('0'),
                            row.get('shipment-item-id'))
            if order_dict.get(where_clause):
                continue
            move_found = stock_move_obj.search(
                [('amazon_shipment_id', '=', row.get('shipment-id')),
                 ('amazon_instance_id', '=', instance.id),
                 ('amazon_order_reference', '=', row.get('amazon-order-id')),
                 ('amazon_order_item_id', '=', row.get('amazon-order-item-id').lstrip('0')),
                 ('amazon_shipment_item_id', '=', row.get('shipment-item-id'))])
            if move_found:
                order_dict.update({where_clause: move_found})
                continue
            row.update({'instance_id': instance.id})

            if row.get('amazon-order-id') not in skip_orders:
                fulfillment_id = row.get('fulfillment-center-id')
                if fulfillment_id not in fulfillment_warehouse:
                    fulfillment_center, fn_warehouse = self.get_warehouse(fulfillment_id, instance)
                    if not fn_warehouse:
                        skip_orders.append(row.get('amazon-order-id'))
                        message = 'Skipped Amazon order %s because Amazon Fulfillment Center not found in Odoo' % ( \
                            row.get('amazon-order-id'))
                        common_log_line_obj.amazon_create_order_log_line(
                            message, model_id, self.id, row.get('amazon-order-id'), False, log_rec)
                        continue
                    fulfillment_warehouse.update(
                        {fulfillment_id: [fn_warehouse, fulfillment_center]})
                warehouse = fulfillment_warehouse.get(fulfillment_id, [False])[0]
                fullfillment_center = fulfillment_warehouse.get(fulfillment_id, [False])[1]
                row.update(
                    {'fulfillment_center': fullfillment_center.id, 'warehouse': warehouse.id})
            if row.get('merchant-order-id', False):
                outbound_orders_dict = self.prepare_amazon_sale_order_line_values(row,
                                                                                  outbound_orders_dict)
            else:
                order_details_dict_list = self.prepare_amazon_sale_order_line_values(row,
                                                                                     order_details_dict_list)
        if outbound_orders_dict:
            self.process_outbound_orders(outbound_orders_dict, log_rec)
        if order_details_dict_list:
            self.process_fba_shipment_orders(order_details_dict_list, log_rec)
        self.write({'state': 'processed'})
        return True

    def get_instance_shipment_report_ept(self, row, instances):
        sale_order_obj = self.env["sale.order"]
        marketplace_obj = self.env['amazon.marketplace.ept']

        if row.get('sales-channel', '') == "Non-Amazon":
            order = sale_order_obj.search([
                ("amz_order_reference", "=", row.get('merchant-order-id', "")),
                ("amz_is_outbound_order", "=", True)])
            instance = order.amz_fulfillment_instance_id
        elif row.get('sales-channel', '') not in instances:
            instance = marketplace_obj.find_instance(self.seller_id,
                                                     row.get('sales-channel', ''))
            instances.update({row.get('sales-channel', ''): instance})
        else:
            instance = instances.get(row.get('sales-channel', ''))
        return instance

    @api.model
    def process_outbound_orders(self, outbound_order_data, job):
        """
        Processes the outbound shipment data from shipping report as of Multi Channel Sale order.
        @author: Maulik Barad on Date 23-Jan-2019.
        @param outbound_order_data: Data of outbound orders.
        @param job: Record of common log book.
        """
        order_obj = self.env["sale.order"]
        amazon_product_obj = self.env["amazon.product.ept"]
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = self.env['ir.model']._get('shipping.report.request.history').id

        for order_ref, lines in outbound_order_data.items():
            available_orders = remain_order = order_obj
            amazon_order = order_obj.search( \
                [("amz_order_reference", "=", order_ref), ("amz_is_outbound_order", "=", True)])
            if not amazon_order:
                message = "Order %s not found in ERP." % (order_ref)
                common_log_line_obj.amazon_create_order_log_line(
                    message, model_id, self.id, order_ref, False, job)
                continue

            amazon_order = amazon_order.filtered(lambda x: x.state == "draft")
            if not amazon_order:
                message = "Order %s is already updated in ERP." % (order_ref)
                common_log_line_obj.amazon_create_order_log_line(
                    message, model_id, self.id, order_ref, False, job)
                continue

            all_lines = amazon_order.order_line.filtered(lambda x: x.product_id.type == "product")
            for line in lines:
                fulfillment_warehouse_id = line.get("warehouse")
                shipped_qty = float(line.get("quantity-shipped"))
                product_sku = line.get("sku", False)
                amazon_product = amazon_product_obj.search_amazon_product(
                    amazon_order.amz_instance_id.id,
                    product_sku, "FBA")
                if not amazon_product:
                    message = "Amazon Product[%s] not found for Instance[%s] in ERP." % (
                        product_sku, amazon_order.amz_instance_id.name)
                    common_log_line_obj.amazon_create_order_log_line(message, model_id, self.id,
                                                                     order_ref, False, job)
                    continue
                product = amazon_product.product_id
                existing_order_line = amazon_order.order_line.filtered(
                    lambda x: x.product_id.id == product.id)
                if amazon_order.warehouse_id.id == fulfillment_warehouse_id:
                    if existing_order_line.product_uom_qty != shipped_qty:
                        new_quantity = existing_order_line.product_uom_qty - shipped_qty
                        if remain_order:
                            existing_order_line.copy(default={'order_id': remain_order.id,
                                                              'product_uom_qty': new_quantity})
                        else:
                            remain_order = self.split_order(
                                {(amazon_order, fulfillment_warehouse_id): {
                                    existing_order_line: new_quantity}})
                        existing_order_line.product_uom_qty = shipped_qty

                    existing_order_line.amazon_order_item_id = line.get("amazon-order-item-id")
                    available_orders |= amazon_order
                else:
                    splitted_order = order_obj.browse()
                    for order in available_orders:
                        if order.warehouse_id.id == fulfillment_warehouse_id:
                            splitted_order = order
                            break

                    if len(all_lines) == 1 and existing_order_line.product_uom_qty == shipped_qty:
                        amazon_order.warehouse_id = fulfillment_warehouse_id
                        existing_order_line.amazon_order_item_id = line.get("amazon-order-item-id")
                        available_orders |= amazon_order

                    elif len(all_lines) > 1:
                        if splitted_order:
                            new_order_line = existing_order_line.copy(
                                default={'order_id': splitted_order.id,
                                         'product_uom_qty': shipped_qty})
                        else:
                            new_order = self.split_order({(amazon_order, fulfillment_warehouse_id):
                                                              {existing_order_line: shipped_qty}})
                            new_order_line = new_order.order_line.filtered(
                                lambda x: x.product_id.id == product.id)
                            available_orders |= new_order

                        new_order_line.amazon_order_item_id = line.get("amazon-order-item-id")
                        existing_order_line.product_uom_qty -= shipped_qty

                        if existing_order_line.product_uom_qty:
                            if remain_order:
                                existing_order_line.copy(\
                                    default={'order_id': remain_order.id,
                                             'product_uom_qty': existing_order_line.product_uom_qty})
                            else:
                                remain_order = self.split_order(
                                    {(amazon_order, fulfillment_warehouse_id): {
                                        existing_order_line: existing_order_line.product_uom_qty}})
                            existing_order_line.product_uom_qty = 0

                    elif len(all_lines) == 1 and existing_order_line.product_uom_qty != shipped_qty:
                        new_quantity = existing_order_line.product_uom_qty - shipped_qty
                        amazon_order.warehouse_id = fulfillment_warehouse_id

                        if remain_order:
                            existing_order_line.copy(default={'order_id': remain_order.id,
                                                              'product_uom_qty': new_quantity})
                        else:
                            remain_order = self.split_order(
                                {(amazon_order, fulfillment_warehouse_id): {
                                    existing_order_line: new_quantity}})
                        existing_order_line.product_uom_qty = shipped_qty
                        existing_order_line.amazon_order_item_id = line.get("amazon-order-item-id")
                        available_orders |= amazon_order

                if existing_order_line.product_uom_qty == 0:
                    existing_order_line.unlink()
            if not amazon_order.order_line:
                available_orders -= amazon_order
                amazon_order.unlink()
            if available_orders:
                available_orders.action_confirm()
                self.attach_amazon_data(available_orders.order_line, lines)
                self.amazon_fba_shipment_report_workflow(available_orders)
        return True

    def attach_amazon_data(self, order_lines, order_line_data):
        """
        Match order line with data and attach all amazon order and shipment data with stock picking
        and moves.
        @author: Maulik Barad on Date 27-Jan-2019.
        @param order_lines: All order lines.
        @param order_line_data: Order line and shipment data.
        """
        for data in order_line_data:
            order_line = order_lines.filtered(
                lambda x: x.amazon_order_item_id == data.get(
                    "amazon-order-item-id") and x.product_uom_qty == float(\
                    data.get("quantity-shipped")) and x.order_id.warehouse_id.id == data.get(\
                    "warehouse"))
            move = order_line.move_ids.filtered(lambda x: x.state in ["confirmed", "assigned"])
            move.write({
                "amazon_shipment_id": data.get("shipment-id"),
                "amazon_instance_id": order_line.order_id.amz_instance_id.id,
                "amazon_order_reference": data.get('merchant-order-id'),
                "amazon_order_item_id": data.get("amazon-order-item-id"),
                "amazon_shipment_item_id": data.get("shipment-item-id"),
                "tracking_number": data.get("tracking-number"),
                "fulfillment_center_id": data.get("fulfillment_center"),
                "amz_shipment_report_id": self.id
            })
            move._action_assign()
            move._set_quantity_done(float(data.get("quantity-shipped")))

            picking = move.picking_id
            if not picking.amazon_shipment_id:
                picking.write({
                    "amazon_shipment_id": data.get("shipment-id"),
                    "is_fba_wh_picking": True,
                    "fulfill_center": data.get("fulfillment_center"),
                    "updated_in_amazon": True
                })
        return True

    def prepare_move_data_ept(self, amazon_order, line):
        """
        Prepare Stock Move data for FBA Process
        @author: Keyur Kanani
        :param amazon_order: sale.order()
        :param line: csv line dictionary
        :return: {}
        """
        return {
            'amazon_shipment_id': line.get('shipment-id'),
            'amazon_instance_id': amazon_order.amz_instance_id.id,
            'amazon_order_reference': line.get('amazon-order-id'),
            'amazon_order_item_id': line.get('amazon-order-item-id').lstrip('0'),
            'amazon_shipment_item_id': line.get('shipment-item-id'),
            'tracking_number': line.get('tracking-number'),
            'fulfillment_center_id': line.get('fulfillment_center'),
            'amz_shipment_report_id': self.id,
            'product_uom_qty': line.get('quantity-shipped')
        }

    @api.model
    def copy_amazon_order(self, amazon_order, warehouse):
        """
        Duplicate the amazon Orders
        @author: Keyur Kanani
        :param amazon_order: sale.order()
        :param warehouse: int
        :return: sale.order()
        """

        if not amazon_order.amz_instance_id.seller_id.is_default_odoo_sequence_in_sales_order_fba:
            new_name = self.get_order_sequence(amazon_order, 1)
            new_sale_order = amazon_order.copy(default={'name': new_name,
                                                        'order_line': None,
                                                        'warehouse_id': warehouse})
        else:
            new_sale_order = amazon_order.copy(default={'order_line': None,
                                                        'warehouse_id': warehouse})
        new_sale_order.onchange_warehouse_id()
        return new_sale_order

    @api.model
    def split_order(self, split_order_line_dict):
        """
        Split Amazon Order
        @author: Keyur Kanani
        :param split_order_line_dict: {}
        :return:
        """
        order_obj = self.env['sale.order']
        new_orders = order_obj.browse()
        for order, lines in split_order_line_dict.items():
            order_record = order[0]
            warehouse = order[1]
            new_amazon_order = self.copy_amazon_order(order_record, warehouse)
            for line, shipped_qty in lines.items():
                line.copy(default={'order_id': new_amazon_order.id,
                                   'product_uom_qty': shipped_qty})
                new_orders += new_amazon_order
        return new_orders

    @api.model
    def get_order_sequence(self, amazon_order, order_sequence):
        """
        Get Order sequence according to seller configurations
        @author: Keyur Kanani
        :param amazon_order: sale.order()
        :param order_sequence:
        :return:
        """
        order_obj = self.env['sale.order']
        new_name = "%s%s" % (\
            amazon_order.amz_instance_id.seller_id.order_prefix and amazon_order.amz_instance_id.seller_id.order_prefix or '',
            amazon_order.amz_order_reference)
        new_name = new_name + '/' + str(order_sequence)
        if order_obj.search([('name', '=', new_name)]):
            order_sequence = order_sequence + 1
            return self.get_order_sequence(amazon_order, order_sequence)
        return new_name

    def process_fba_shipment_orders(self, order_details_dict_list, job):
        """
        Create Sale Orders, order lines and Shipment lines, giftwrap etc..
        Create and Done Stock Move.
        @author: Keyur Kanani
        :param order_details_dict_list: {}
        :return boolean: True
        """
        sale_order_obj = self.env['sale.order']
        sale_order_line_obj = self.env['sale.order.line']
        amz_instance_obj = self.env['amazon.instance.ept']
        stock_location_obj = self.env['stock.location']
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = self.env['ir.model']._get('shipping.report.request.history').id
        pending_orders_dict = {}
        partner_dict = {}
        product_details = {}
        commit_flag = 1
        country_dict = {}
        state_dict = {}
        customers_location = stock_location_obj.search([('usage', '=', 'customer'),
                                                        '|',('company_id', '=', self.seller_id.company_id.id),
                                                        ('company_id', '=', False)], limit=1)
        for order_ref, lines in order_details_dict_list.items():
            skip_order, product_details = self.prepare_amazon_products(lines, product_details, job)
            if skip_order:
                message = 'Skipped Amazon order %s because of products mismatch' % (order_ref)
                common_log_line_obj.amazon_create_order_log_line(message, \
                                                                 model_id, self.id, order_ref,
                                                                 False, job)
                continue
            for order_line in lines:
                instance = amz_instance_obj.browse(order_line.get('instance_id'))
                # # If pending order then unlink that order and create new order
                pending_order = pending_orders_dict.get((order_ref, instance.id))
                if not pending_order:
                    sale_order = sale_order_obj.search([('amz_order_reference', '=', order_ref),
                                                        ('amz_instance_id', '=', instance.id),
                                                        ('amz_fulfillment_by', '=', 'FBA'),
                                                        ('state', '=', 'draft'),
                                                        ('is_fba_pending_order', '=', True)])
                    if sale_order:
                        pending_orders_dict.update({(order_ref, instance.id): sale_order.ids})
                        sale_order.unlink()
                # Search or create customer
                partner_dict, country_dict, state_dict = self.search_or_create_partner(order_line,
                                                                                       instance,
                                                                                       partner_dict,
                                                                                       country_dict,
                                                                                       state_dict)
                amazon_order = sale_order_obj.create_amazon_shipping_report_sale_order(order_line,
                                                                                       partner_dict,
                                                                                       self.id)
                # Create Sale order lines
                so_line = sale_order_line_obj.create_amazon_sale_order_line(amazon_order,
                                                                            order_line,
                                                                            product_details)
                move_data_dict = self.prepare_move_data_ept(amazon_order, order_line)
                self.amazon_fba_stock_move(so_line, customers_location, move_data_dict)
                self.amazon_fba_shipment_report_workflow(amazon_order)
            if commit_flag == 10:
                self.env.cr.commit()
                commit_flag = 0
            commit_flag += 1
        return True

    def amazon_fba_shipment_report_workflow(self, amz_order_list):
        """
        The function is used for create Invoices and Process Stock Move done.
        @author: Keyur Kanani
        :param order: sale.order()
        :return:
        """
        stock_move_obj = self.env['stock.move']
        for order in amz_order_list:
            fba_auto_workflow_id = order.amz_seller_id.fba_auto_workflow_id

            stock_moves = stock_move_obj.search(
                [('amazon_order_reference', '=', order.amz_order_reference),
                 ('amazon_instance_id', '=', order.amz_instance_id.id)])
            stock_moves._action_done()
            order.write({'state': 'sale'})
            if fba_auto_workflow_id.create_invoice:
                # For Update Invoices in Amazon, process to create Invoices as per Shipment id

                shipment_ids = {}
                for move in order.order_line.move_ids:
                    if move.amazon_shipment_id in shipment_ids:
                        shipment_ids.get(move.amazon_shipment_id).append( \
                            move.amazon_shipment_item_id)
                    else:
                        shipment_ids.update(
                            {move.amazon_shipment_id: [move.amazon_shipment_item_id]})
                for shipment, shipment_item in list(shipment_ids.items()):
                    to_invoice = order.order_line.filtered(lambda l: l.qty_to_invoice != 0.0)
                    if to_invoice:
                        invoices = order.with_context( \
                            {'shipment_item_ids': shipment_item})._create_invoices()
                        invoice = invoices.filtered(lambda l: l.line_ids)
                        if invoice:
                            order.validate_invoice_ept(invoice)
                            if fba_auto_workflow_id.register_payment:
                                order.paid_invoice_ept(invoice)
                        else:
                            for inv in invoices:
                                if not inv.line_ids:
                                    inv.unlink()
        return True

    def amazon_fba_stock_move(self, order_line, customers_location, move_vals):
        """
        Create Stock Move according to MRP module and bom products and also for simple product
        variant.
        @author: Keyur Kanani
        :param order_line: sale.order.line() record.
        :param customers_location: stock.location()
        :param move_vals: stock move vals
        :return:
        """

        module_obj = self.env['ir.module.module']
        mrp_module = module_obj.sudo().search([('name', '=', 'mrp'), ('state', '=', 'installed')])
        if mrp_module:
            bom_lines = self.amz_shipment_get_set_product_ept(order_line.product_id)
            if bom_lines:
                for bom_line in bom_lines:
                    stock_move_vals = self.prepare_stock_move_vals(order_line, customers_location,
                                                                   move_vals)
                    stock_move_vals.update({'product_id': bom_line[0].product_id.id,
                                            'product_uom_qty': bom_line[1].get(
                                                'qty') * order_line.product_uom_qty})
                    self.process_shipment_report_stock_move_ept(stock_move_vals)
            else:
                stock_move_vals = self.prepare_stock_move_vals(order_line, customers_location,
                                                               move_vals)
                self.process_shipment_report_stock_move_ept(stock_move_vals)
        else:
            stock_move_vals = self.prepare_stock_move_vals(order_line, customers_location,
                                                           move_vals)
            self.process_shipment_report_stock_move_ept(stock_move_vals)
        return True

    def process_shipment_report_stock_move_ept(self, stock_move_vals):
        stock_move_obj = self.env['stock.move']
        stock_move = stock_move_obj.create(stock_move_vals)
        stock_move._action_assign()
        stock_move._set_quantity_done(stock_move.product_uom_qty)
        return True

    def amz_shipment_get_set_product_ept(self, product):
        """
        Find BOM for phantom type only if Bill of Material type is Make to Order
        then for shipment report there are no logic to create Manufacturer Order.
        Author: Keyur Kanani
        :param product:
        :return:
        """
        try:
            bom_obj = self.env['mrp.bom']
            bom_point = bom_obj.sudo()._bom_find(product=product, company_id=self.company_id.id,
                                                 bom_type='phantom')
            from_uom = product.uom_id
            to_uom = bom_point.product_uom_id
            factor = from_uom._compute_quantity(1, to_uom) / bom_point.product_qty
            bom, lines = bom_point.explode(product, factor, picking_type=bom_point.picking_type_id)
            return lines
        except:
            return {}

    def prepare_stock_move_vals(self, order_line, customers_location, move_vals):
        """
        Prepare stock move data for create stock move while validating sale order
        @author: Keyur kanani
        :param order_line:
        :param customers_location:
        :param move_vals:
        :return:
        """
        return {
            'name': _('Amazon move : %s') % order_line.order_id.name,
            'company_id': self.company_id.id,
            'product_id': order_line.product_id.id,
            'product_uom_qty': move_vals.get('product_uom_qty',
                                             False) or order_line.product_uom_qty,
            'product_uom': order_line.product_uom.id,
            'location_id': order_line.order_id.warehouse_id.lot_stock_id.id,
            'location_dest_id': customers_location.id,
            'state': 'confirmed',
            'sale_line_id': order_line.id,
            'seller_id': self.seller_id.id,
            'amazon_shipment_id': move_vals.get('amazon_shipment_id'),
            'amazon_instance_id': move_vals.get('amazon_instance_id'),
            'amazon_order_reference': move_vals.get('amazon_order_reference'),
            'amazon_order_item_id': move_vals.get('amazon_order_item_id'),
            'amazon_shipment_item_id': move_vals.get('amazon_shipment_item_id'),
            'tracking_number': move_vals.get('tracking_number'),
            'fulfillment_center_id': move_vals.get('fulfillment_center_id'),
            'amz_shipment_report_id': move_vals.get('amz_shipment_report_id')
        }

    @staticmethod
    def prepare_ship_partner_vals(row, instance):
        """
        Prepare Shipment Partner values
        @author: Keyur kanani
        :param row: {}
        :param instance: amazon.instance.ept()
        :return: {}
        """
        street2 = "%s %s" % (row.get('ship-address-2', ''), row.get('ship-address-3', '')) \
            if row.get('ship-address-2') or row.get('ship-address-3') else False
        partner_vals = {
            'street': row.get('ship-address-1', False),
            'street2': street2,
            'city': row.get('ship-city', False),
            'phone': row.get('ship-phone-number', False),
            'email': row.get('buyer-email', False),
            'zip': row.get('ship-postal-code', False),
            'lang': instance.lang_id and instance.lang_id.code,
            'company_id': instance.company_id.id,
            'is_amz_customer': True,
        }
        if instance.amazon_property_account_payable_id:
            partner_vals.update( \
                {'property_account_payable_id': instance.amazon_property_account_payable_id.id})
        if instance.amazon_property_account_receivable_id:
            partner_vals.update({
                'property_account_receivable_id': instance.amazon_property_account_receivable_id.id})
        return partner_vals

    def search_or_create_partner(self, row, instance, partner_dict, country_dict, state_dict):
        """
        Search existing partner from order lines, if not exist then create New partner and
        if shipping partner is different from invoice partner then create new partner for shipment
        @author: Keyur Kanani
        :param row: {}
        :param instance:amazon.instance.ept()
        :param partner_dict: {}
        :return: {}
        """

        res_partner_obj = self.env['res.partner']
        buyer_name = row.get('buyer-name')
        recipient_name = row.get('recipient-name')
        country_obj = country_dict.get(row.get('ship-country'))
        if not country_obj:
            country_obj = self.env['res.country'].search( \
                ['|', ('code', '=', row.get('ship-country')),
                 ('name', '=', row.get('ship-country'))],
                limit=1)
            country_dict.update({row.get('ship-country'): country_obj})
        if recipient_name == 'CONFIDENTIAL':
            partner = res_partner_obj.with_context(is_amazon_partner=True).search( \
                [('email', '=', row.get('buyer-email')), ('name', '=', row.get('buyer-name')),
                 ('country_id', '=', country_obj.id)], limit=1)
            if not partner:
                partner_vals = {}
                if instance.amazon_property_account_payable_id:
                    partner_vals.update(
                        {
                            'property_account_payable_id': instance.amazon_property_account_payable_id.id})
                if instance.amazon_property_account_receivable_id:
                    partner_vals.update( \
                        {
                            'property_account_receivable_id': instance.amazon_property_account_receivable_id.id})
                partner = res_partner_obj.with_context(tracking_disable=True).create({
                    'name': buyer_name,
                    'country_id': country_obj.id,
                    'type': 'invoice',
                    'lang': instance.lang_id and instance.lang_id.code,
                    'is_amz_customer': True,
                    **partner_vals
                })
            return {'invoice_partner': partner.id,
                    'shipping_partner': partner.id}, country_dict, state_dict

        ship_vals = self.prepare_ship_partner_vals(row, instance)
        state = state_dict.get(row.get('ship-state'), False)
        if not state and country_obj and row.get('ship-state') != '--':
            state = res_partner_obj.create_or_update_state_ept(country_obj.code,
                                                               row.get('ship-state'),
                                                               ship_vals.get('zip'), country_obj)
            state_dict.update({row.get('ship-state'): state})
        ship_vals.update(
            {'state_id': state and state.id or False,
             'country_id': country_obj and country_obj.id or False})

        street2 = ship_vals.get('street2', False)
        partner = res_partner_obj.with_context(is_amazon_partner=True).search(
            [('email', '=', row.get('buyer-email')), '|', ('company_id', '=', False),
             ('company_id', '=', instance.company_id.id)], limit=1)
        if not partner:
            partnervals = {'name': buyer_name, 'type': 'invoice', **ship_vals}
            partner = res_partner_obj.create(partnervals)
            partner_dict.update({'invoice_partner': partner.id})
            invoice_partner = partner
        elif (buyer_name and partner.name != buyer_name):
            partner.is_company = True
            invoice_partner = res_partner_obj.with_context(tracking_disable=True).create({
                'parent_id': partner.id,
                'name': buyer_name,
                'type': 'invoice',
                **ship_vals
            })
        else:
            invoice_partner = partner

        delivery = invoice_partner if (invoice_partner.name == recipient_name) else None
        if not delivery:
            delivery = res_partner_obj.with_context(is_amazon_partner=True).search( \
                [('name', '=', recipient_name), ('street', '=', ship_vals.get('street')),
                 '|', ('street2', '=', False), ('street2', '=', street2),
                 ('zip', '=', ship_vals.get('zip')),
                 ('city', '=', ship_vals.get('city')),
                 ('country_id', '=', ship_vals.get('country_id')),
                 ('state_id', '=', ship_vals.get('state_id')),
                 '|', ('company_id', '=', False), ('company_id', '=', instance.company_id.id)],
                limit=1)
            if not delivery:
                invoice_partner.is_company = True
                delivery = res_partner_obj.with_context(tracking_disable=True).create({
                    'name': recipient_name,
                    'type': 'delivery',
                    'parent_id': invoice_partner.id,
                    'is_amz_customer': True,
                    **ship_vals, })
        return {'invoice_partner': invoice_partner.id,
                'shipping_partner': delivery.id}, country_dict, state_dict

    def get_warehouse(self, fulfillment_center_id, instance):
        """
        Get Amazon fulfillment center and FBA warehouse id from current instance
        @author: Keyur Kanani
        :param fulfillment_center_id:
        :param instance: amazon.instance.ept()
        :return: fulfillment_center, warehouse
        """
        fulfillment_center_obj = self.env['amazon.fulfillment.center']
        fulfillment_center = fulfillment_center_obj.search( \
            [('center_code', '=', fulfillment_center_id),
             ('seller_id', '=', instance.seller_id.id)])
        fulfillment_center = fulfillment_center and fulfillment_center[0]
        warehouse = fulfillment_center and fulfillment_center.warehouse_id or \
                    instance.fba_warehouse_id and instance.fba_warehouse_id or \
                    instance.warehouse_id or False
        return fulfillment_center, warehouse

    @staticmethod
    def prepare_amazon_sale_order_line_values(row, order_details_dict_list):
        """
        Prepare Sale Order lines vals for amazon orders
        @author: Keyur Kanani
        :param row:{}
        :return:{}
        """
        if row.get('merchant-order-id', False):
            if order_details_dict_list.get(row.get('merchant-order-id', False)):
                order_details_dict_list.get(row.get('merchant-order-id', False)).append(row)
            else:
                order_details_dict_list.update({row.get('merchant-order-id', False): [row]})
        else:
            if order_details_dict_list.get(row.get('amazon-order-id', False)):
                order_details_dict_list.get(row.get('amazon-order-id', False)).append(row)
            else:
                order_details_dict_list.update({row.get('amazon-order-id', False): [row]})
        return order_details_dict_list

    def prepare_amazon_products(self, lines, product_dict, job):
        """
        Prepare Amazon Product values
        @author: Keyur Kanani
        :param lines: order lines
        :param product_dict: {}
        :param job: log record.
        :return: {boolean, product{}}

        If odoo product founds and amazon product not found then no need to
        check anything and create new amazon product and create log for that
        , if odoo product not found then go to check configuration which
        action has to be taken for that.
        There are following situations managed by code.
        In any situation log that event and action.

        1). Amazon product and odoo product not found
            => Check seller configuration if allow to create new product
            then create product.
            => Enter log details with action.
        2). Amazon product not found but odoo product is there.
            => Created amazon product with log and action.
        """

        amazon_product_obj = self.env['amazon.product.ept']
        odoo_product_obj = self.env['product.product']
        amz_instance_obj = self.env['amazon.instance.ept']
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = self.env['ir.model']._get('shipping.report.request.history').id
        skip_order = False
        for row in lines:
            seller_sku = row.get('sku')
            instance = amz_instance_obj.browse(row.get('instance_id'))
            odoo_product = product_dict.get((seller_sku, instance.id))
            if odoo_product:
                continue

            amazon_product = amazon_product_obj.search_amazon_product(instance.id, seller_sku, 'FBA')
            if not amazon_product:
                odoo_product = amazon_product_obj.search_product(seller_sku)

                if odoo_product:
                    message = 'Odoo Product is already exists. System have created new Amazon ' \
                              'Product %s ' \
                              'for %s instance' % (seller_sku, instance.name)
                    common_log_line_obj.amazon_create_product_log_line(message, model_id,
                                                                       odoo_product, seller_sku,
                                                                       job)
                elif not instance.seller_id.create_new_product:
                    skip_order = True
                    message = 'Product %s not found for %s instance' % (seller_sku, instance.name)
                    common_log_line_obj.amazon_create_product_log_line(message, model_id,
                                                                       False, seller_sku, job)
                else:
                    # #Create Odoo Product
                    erp_prod_vals = {
                        'name': row.get('product-name'),
                        'default_code': seller_sku,
                        'type': 'product',
                        'purchase_ok': True,
                        'sale_ok': True,
                    }
                    odoo_product = odoo_product_obj.create(erp_prod_vals)
                    message = 'System have created new Odoo Product %s for %s instance' % (
                        seller_sku, instance.name)
                    common_log_line_obj.amazon_create_product_log_line(message, model_id,
                                                                       odoo_product, seller_sku,
                                                                       job)

                if not skip_order:
                    sku = seller_sku or (odoo_product and odoo_product[0].default_code) or False
                    # #Prepare Product Values
                    prod_vals = self.prepare_amazon_prod_vals(instance, row, sku, odoo_product)
                    # #Create Amazon Product
                    amazon_product_obj.create(prod_vals)
                if odoo_product:
                    product_dict.update({(seller_sku, instance.id): odoo_product})
            else:
                product_dict.update({(seller_sku, instance.id): amazon_product.product_id})
        return skip_order, product_dict

    @staticmethod
    def prepare_amazon_prod_vals(instance, order_line, sku, odoo_product):
        """
        Prepare Amazon Product Values
        @author: Keyur Kanani
        :param instance: amazon.instance.ept()
        :param order_line: {}
        :param sku: string
        :param odoo_product: product.product()
        :return: {}
        """
        prod_vals = {}
        prod_vals.update({
            'name': order_line.get('product-name', False),
            'instance_id': instance.id,
            'product_asin': order_line.get('ASIN', False),
            'seller_sku': sku,
            'product_id': odoo_product and odoo_product.id or False,
            'exported_to_amazon': True, 'fulfillment_by': 'FBA'
        })
        return prod_vals

    @api.model
    def auto_import_shipment_report(self, args):
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].browse(int(seller_id))
            if seller.shipping_report_last_sync_on:
                start_date = seller.shipping_report_last_sync_on
                start_date = datetime.strptime(str(start_date), '%Y-%m-%d %H:%M:%S.%f')
                start_date = start_date - timedelta(hours=10)
            else:
                today = datetime.now()
                start_date = today - timedelta(days=30)
            start_date = start_date + timedelta(days=seller.shipping_report_days * -1 or -3)
            end_date = datetime.now()

            report_type = '_GET_AMAZON_FULFILLED_SHIPMENTS_DATA_'
            if not seller.is_another_soft_create_fba_shipment:
                if not self.search([('start_date', '=', start_date),
                                    ('end_date', '=', end_date),
                                    ('seller_id', '=', seller_id),
                                    ('report_type', '=', report_type)]):
                    shipment_report = self.create({'report_type': report_type,
                                                   'seller_id': seller_id,
                                                   'state': 'draft',
                                                   'start_date': start_date,
                                                   'end_date': end_date,
                                                   'requested_date': time.strftime(
                                                       "%Y-%m-%d %H:%M:%S")
                                                   })
                    shipment_report.with_context(is_auto_process=True).request_report()
            else:
                date_start = start_date.strftime("%Y-%m-%dT%H:%M:%SZ")
                date_end = end_date.strftime("%Y-%m-%dT%H:%M:%SZ")
                list_of_wrapper = self.get_reports_from_other_softwares(seller, report_type,
                                                                        date_start, date_end)
                for reports in list_of_wrapper:
                    for report in reports.get('ReportRequestInfo', {}):
                        report_id = report.get('GeneratedReportId', {}).get('value')
                        request_id = report.get('ReportRequestId', {}).get('value')
                        if not self.search([('report_id', '=', report_id),
                                            ('report_request_id', '=', request_id),
                                            ('report_type', '=', report_type)]):
                            start = report.get('StartDate', {}).get('value', {}).split('+')
                            end = report.get('EndDate', {}).get('value', {}).split('+')
                            self.create({
                                'seller_id': seller_id,
                                'state': report.get('ReportProcessingStatus', {}).get('value'),
                                'start_date': datetime.strptime(start[0], '%Y-%m-%dT%H:%M:%S'),
                                'end_date': datetime.strptime(end[0], '%Y-%m-%dT%H:%M:%S'),
                                'report_type': report.get('ReportType', {}).get('value'),
                                'report_id': report.get('GeneratedReportId', {}).get('value'),
                                'report_request_id': report.get('ReportRequestId', {}).get('value'),
                                'requested_date': time.strftime("%Y-%m-%d %H:%M:%S")
                            })
            seller.write({'shipping_report_last_sync_on': end_date})

        return True

    def auto_process_shipment_report(self, args={}):
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].browse(seller_id)
            ship_reports = self.search([('seller_id', '=', seller.id),
                                        ('state', 'in',
                                         ['_SUBMITTED_', '_IN_PROGRESS_', '_DONE_'])])
            for report in ship_reports:
                if report.state != '_DONE_':
                    report.get_report_request_list()
                if report.report_id and report.state == '_DONE_':
                    report.with_context(is_auto_process=True).get_report()
                if report.attachment_id:
                    report.with_context(is_auto_process=True).process_shipment_file()
                self._cr.commit()
        return True

    def get_reports_from_other_softwares(self, seller, report_type, start_date, end_date):
        kwargs = self.prepare_amazon_request_report_kwargs(seller)
        kwargs.update({'emipro_api': 'get_shipping_or_inventory_report_v13',
                       'report_type': report_type,
                       'start_date': start_date,
                       'end_date': end_date})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs,
                                         timeout=1000)
        if not response.get('reason'):
            list_of_wrapper = response.get('result')
        else:
            raise UserError(_(response.get('reason')))
        return list_of_wrapper

    def get_missing_fulfillment_center(self, attachment_id):
        """
        All Fulfillment Center from attachment file and find in ERP
        If Fulfillment Center doesn't exist in ERP then it will return in list
        @:param - attachment_id - shipping report attachment
        @:return - unavailable_fulfillment_center - return missing fulfillment center from ERP
        @author: Deval Jagad (09/01/2020)
        """
        fulfillment_center_obj = self.env['amazon.fulfillment.center']
        unavailable_fulfillment_center = []
        log = self.amz_search_or_create_logs_ept(message='')
        imp_file = self.decode_amazon_encrypted_attachments_data(attachment_id, log)
        reader = csv.DictReader(imp_file, delimiter='\t')
        fulfillment_centers = [row.get('fulfillment-center-id') for row in reader]
        fulfillment_center_list = fulfillment_centers and list(set(fulfillment_centers))
        seller_id = self.seller_id.id

        for fulfillment_center in fulfillment_center_list:
            amz_fulfillment_center_id = fulfillment_center_obj.search(
                [('center_code', '=', fulfillment_center),
                 ('seller_id', '=', seller_id)])
            if not amz_fulfillment_center_id:
                unavailable_fulfillment_center.append(fulfillment_center)
        return unavailable_fulfillment_center

    def configure_missing_fulfillment_center(self):
        """
        Open wizard with load missing fulfillment center from ERP
        @author: Deval Jagad (07/01/2020)
        """
        view = self.env.ref('amazon_ept.view_configure_shipment_report_fulfillment_center_ept')
        context = dict(self._context)
        country_ids = self.seller_id.amz_warehouse_ids.mapped('partner_id').mapped('country_id')
        context.update({'shipment_report_id': self.id, 'country_ids': country_ids.ids})

        return {
            'name': _('Amazon Shipment Report - Configure Missing Fulfillment Center'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'shipment.report.configure.fulfillment.center.ept',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'context': context,
        }

    def decode_amazon_encrypted_attachments_data(self, attachment_id, job):
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        req = {'dbuuid': dbuuid, 'report_id': self.report_id,
               'datas': attachment_id.datas.decode(), 'amz_report_type': 'shipment_report'}
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/decode_data', params=req, timeout=1000)
        if response.get('result'):
            imp_file = StringIO(base64.b64decode(response.get('result')).decode())
        elif self._context.get('is_auto_process', False):
            job.log_lines.create({'message': 'Error found in Decryption of Data %s' % response.get('error', '')})
            return True
        else:
            raise Warning(response.get('error'))
        return imp_file
