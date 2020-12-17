# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added class and methods to request for VCS tax report, import and process that report.
"""

import time
import base64
from io import StringIO
import csv
import logging
import json
from datetime import datetime, timedelta
from odoo import models, fields, api, _
from odoo.exceptions import UserError
from odoo.addons.iap.tools import iap_tools
from ..endpoint import DEFAULT_ENDPOINT

_logger = logging.getLogger("Amazon")


class VcsTaxReport(models.Model):
    """
    Added class to import amazon VCS tax report.
    """
    _name = 'amazon.vcs.tax.report.ept'
    _description = 'Amazon VCS Tax Report'
    _inherit = ['mail.thread']
    _order = 'id desc'

    def _compute_log_count(self):
        """
        Sets count of log lines for the VCS report.
        @change: By Maulik Barad on Date 20-Jan-2019.
        """
        log_line_obj = self.env['common.log.lines.ept']
        model_id = log_line_obj.get_model_id('amazon.vcs.tax.report.ept')
        records = log_line_obj.search_read([('model_id', '=', model_id), ('res_id', '=', self.id)],
                                           ["id"])
        self.log_count = len(records)

    def _compute_no_of_invoices(self):
        """
        This method is used to count the number of invoices created via VCS tax report.
        """
        for record in self:
            record.invoice_count = len(record.invoice_ids)

    name = fields.Char(size=256)
    start_date = fields.Datetime(help="Report Start Date")
    end_date = fields.Datetime(help="Report End Date")
    report_request_id = fields.Char(size=256, string='Report Request ID',
                                    help="Report request id to recognise unique request")
    report_id = fields.Char(size=256, string='Report ID',
                            help="Unique Report id for recognise report in Odoo")
    report_type = fields.Char(size=256, help="Amazon Report Type")
    seller_id = fields.Many2one('amazon.seller.ept', string='Seller', copy=False)
    state = fields.Selection(
        [('draft', 'Draft'), ('_SUBMITTED_', 'SUBMITTED'), ('_IN_PROGRESS_', 'IN_PROGRESS'),
         ('_CANCELLED_', 'CANCELLED'), ('_DONE_', 'DONE'),
         ('partially_processed', 'Partially Processed'),
         ('_DONE_NO_DATA_', 'DONE_NO_DATA'), ('processed', 'PROCESSED')
         ],
        string='Report Status', default='draft')
    attachment_id = fields.Many2one('ir.attachment', string="Attachment")
    auto_generated = fields.Boolean('Auto Generated Record ?', default=False)
    log_count = fields.Integer(compute="_compute_log_count")
    invoice_count = fields.Integer(compute="_compute_no_of_invoices",
                                   string="Invoices Count")
    invoice_ids = fields.Many2many('account.move', 'vcs_processed_invoices', string="Invoices")

    def unlink(self):
        """
        This method is inherited to do not allow to delete te processed report.
        """
        for report in self:
            if report.state == 'processed':
                raise UserError(_('You cannot delete processed report.'))
        return super(VcsTaxReport, self).unlink()

    @api.model
    def default_get(self, fields):
        """
        inherited to update the report type.
        """
        res = super(VcsTaxReport, self).default_get(fields)
        if not fields:
            return res
        res.update({'report_type': '_SC_VAT_TAX_REPORT_',})
        return res

    @api.model
    def create(self, vals):
        """
        inherited to update the name of VCS tax report.
        """
        try:
            sequence = self.env.ref('amazon_ept.seq_import_vcs_report_job')
            if sequence:
                report_name = sequence.next_by_id()
            else:
                report_name = '/'
        except:
            report_name = '/'
        vals.update({'name': report_name})
        return super(VcsTaxReport, self).create(vals)

    @api.onchange('seller_id')
    def on_change_seller_id(self):
        """
        Based on seller it will update the start and end date.
        """
        value = {}
        if self.seller_id:
            start_date = datetime.now() + timedelta(
                days=self.seller_id.fba_vcs_report_days * -1 or -3)
            value.update({'start_date': start_date, 'end_date': datetime.now()})
        return {'value': value}

    def download_report(self):
        """
        This method is used to download VCS tax report.
        """
        self.ensure_one()
        if self.attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % self.attachment_id.id,
                'target': 'download',
            }
        return True

    def list_of_logs(self):
        """
        This method is used to display the number of logs from the VCS tax report.
        """
        log_line_obj = self.env['common.log.lines.ept']
        model_id = log_line_obj.get_model_id('amazon.vcs.tax.report.ept')
        records = log_line_obj.search(
            [('model_id', '=', model_id), ('res_id', '=', self.id)])
        action = {
            'domain': "[('id', 'in', " + str(records.ids) + " )]",
            'name': 'Mismatch Details',
            'view_mode': 'tree',
            'res_model': 'common.log.lines.ept',
            'type': 'ir.actions.act_window',
        }
        return action

    def report_start_and_end_date(self):
        """
        This method will return the report start and end date.
        """
        start_date, end_date = self.start_date, self.end_date
        if start_date:
            db_import_time = time.strptime(str(start_date), "%Y-%m-%d %H:%M:%S")
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
            db_import_time = time.strptime(str(end_date), "%Y-%m-%d %H:%M:%S")
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
        This method will request for the VCS tax report and update report history in odoo.
        """
        common_log_book_obj = self.env["common.log.book.ept"]
        seller, report_type, start_date, end_date = self.seller_id, self.report_type, \
                                                    self.start_date, self.end_date
        if not seller:
            raise UserError(_('Please select Seller'))

        start_date, end_date = self.report_start_and_end_date()

        kwargs = self.prepare_amazon_request_report_kwargs(seller)
        kwargs.update({
            'emipro_api': 'request_report_v13',
            'report_type': report_type,
            'start_date': start_date,
            'end_date': end_date,
        })
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            if self._context.get('is_auto_process'):
                common_log_book_obj.create({
                    'type': 'import',
                    'module': 'amazon_ept',
                    'active': True,
                    'log_lines': [(0, 0, {'message': response.get('reason')})]
                })
            else:
                raise UserError(_(response.get('reason')))
        else:
            result = response.get('result')
            self.update_report_history(result)
        return True

    def update_report_history(self, request_result):
        """
        Update Report History in odoo
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
        This method is used to get report data based on VCS report request id and process
        response and update report request history in odoo.
        """
        self.ensure_one()
        common_log_book_obj = self.env['common.log.book.ept']
        list_of_wrapper = []
        if not self.seller_id:
            raise UserError(_('Please select seller'))
        if not self.request_id:
            return True

        kwargs = self.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update({'emipro_api': 'get_report_list_v13',
                       'request_id': [self.request_id]})

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            if self._context.get('is_auto_process'):
                common_log_book_obj.create({
                    'type': 'import',
                    'module': 'amazon_ept',
                    'active': True,
                    'log_lines': [(0, 0,
                                   {'message': 'VCS Report Process ' + response.get('reason')})]
                })
            else:
                raise UserError(_(response.get('reason')))
        else:
            list_of_wrapper = response.get('result')

        for result in list_of_wrapper:
            self.update_report_history(result)
        return True

    def get_report_request_list(self):
        """
        This method will request for get report request list based on report_request_id
        and process response and update report history in odoo.
        """
        self.ensure_one()
        if not self.seller_id:
            raise UserError(_('Please select Seller'))
        if not self.report_request_id:
            return True

        kwargs = self.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update({'emipro_api': 'get_report_request_list_v13',
                       'request_ids': (self.report_request_id)})

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if not response.get('reason'):
            list_of_wrapper = response.get('result')
        else:
            raise UserError(_(response.get('reason')))
        for result in list_of_wrapper:
            self.update_report_history(result)
        return True

    def get_report(self):
        """
        This method is used to get vcs tax report and create attachments and post the message.
        """
        self.ensure_one()
        common_log_book_obj = self.env['common.log.book.ept']
        result = {}
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select seller'))
        if not self.report_id:
            return True

        kwargs = self.prepare_amazon_request_report_kwargs(self.seller_id)
        kwargs.update({'emipro_api': 'get_report_v13',
                       'report_id': self.report_id,
                       'amz_report_type': 'vcs_tax_report'})
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs, timeout=1000)
        if response.get('reason'):
            if self._context.get('is_auto_process'):
                common_log_book_obj.create({
                    'type': 'import',
                    'module': 'amazon_ept',
                    'active': True,
                    'log_lines': [
                        (0, 0, {'message': 'VCS Report Process ' + response.get('reason')})]
                })
            else:
                raise UserError(_(response.get('reason')))
        else:
            result = response.get('result')
        if result:
            file_name = "VCS_Tax_report_" + time.strftime("%Y_%m_%d_%H%M%S") + '.csv'
            attachment = self.env['ir.attachment'].create({
                'name': file_name,
                'datas': result.encode(),
                'res_model': 'mail.compose.message',
                'type': 'binary'
            })
            self.message_post(body=_("<b>VCS Tax Report Downloaded</b>"),
                              attachment_ids=attachment.ids)
            self.write({'attachment_id': attachment.id})
        return True

    def prepare_amazon_request_report_kwargs(self, seller):
        """
        Define common method to request for VCX tax report operations.
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

    def auto_import_vcs_tax_report(self, args={}):
        """
        Define method to auto process for import vcs tax report.
        """
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].search([('id', '=', seller_id)])
            start_date = datetime.now() + timedelta(days=seller.fba_vcs_report_days * -1 or -3)
            date_end = datetime.now()
            vcs_report = self.create({'report_type': '_SC_VAT_TAX_REPORT_',
                                      'seller_id': seller_id,
                                      'start_date': start_date,
                                      'end_date': date_end,
                                      'state': 'draft',
                                      'requested_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                                      'auto_generated': True,
                                      })
            vcs_report.request_report()
            seller.write({'vcs_report_last_sync_on': date_end})
        return True

    def process_vcs_tax_report_file(self):
        """
        @change: By Maulik Barad on Date 20-Jan-2019.

        Updated  by Twinkalc on 30-sep-2020
        Optimise the code and changes related
        update taxes in invoice after existing invoice reset to draft and
        also displayed the invoice records into the VCS report once
        taxes updated in invoice which is exist.
        """
        self.ensure_one()
        country_dict = {}
        instance_dict = {}
        ship_from_country_dict = {}
        warehouse_country_dict = {}
        amazon_prod_dict = {}
        order_id = False
        refund_data = {}
        line_no = 1

        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']
        model_id = log_line_obj.get_model_id('amazon.vcs.tax.report.ept')

        log_vals = {
            'model_id': model_id,
            'module': 'amazon_ept',
            'type': 'import',
        }
        log = log_obj.create(log_vals)

        log_line_vals = {
            'model_id': model_id,
            'res_id': self.id,
            'log_book_id': log.id
        }

        try:
            amazon_seller = self.seller_id or False
            if not self.attachment_id:
                raise UserError(_("There is no any report are attached with this record."))

            imp_file = self.decode_amazon_encrypted_vcs_attachments_data(self.attachment_id, log)
            reader = csv.DictReader(imp_file, delimiter=',')

            for row in reader:
                line_no += 1
                order_id = row.get('Order ID', False)
                if order_id:
                    log_line_vals.update({'order_ref': order_id})
                vat_number = row.get('Buyer Tax Registration', False)
                tax_rate = float(row.get('Tax Rate', 0.0)) * 100

                marketplace_id = row.get('Marketplace ID', False)
                invoice_type = row.get('Transaction Type', False)
                sku = row.get('SKU', False)

                is_skip = self.check_vcs_report_file_data_ept(row, log_line_vals, line_no)
                if is_skip:
                    continue

                if invoice_type == 'SHIPMENT':
                    invoice_type = 'out_invoice'
                    invoice_date = row.get('Tax Calculation Date', False)
                else:
                    invoice_type = 'out_refund'
                    invoice_date = row.get('Shipment Date', False)
                invoice_date = datetime.strptime(invoice_date[:11], "%d-%b-%Y").date()

                country = self.find_vcs_country_ept(country_dict, marketplace_id, log_line_vals,
                                                    line_no)
                if not country:
                    continue

                instance = self.find_vcs_instance_ept(country, amazon_seller, instance_dict)
                if not instance:
                    message = 'Instance with %s Country and %s Seller not found in line %d' \
                              % (country.name, amazon_seller.name, line_no)
                    self.create_log(log_line_obj, log_line_vals, message)
                    continue

                sale_order = self.find_amazon_vcs_sale_order_ept(row, instance, \
                                                                 ship_from_country_dict,
                                                                 warehouse_country_dict)
                if not sale_order:
                    message = 'Sale Order - %s not found in line %d' % (order_id, line_no)
                    self.create_log(log_line_obj, log_line_vals, message)
                    continue

                if sale_order.state == 'draft':
                    message = "Sale Order isn't Confirmed, Draft Quotation - %s found in line %d" \
                              % (order_id, line_no)
                    self.create_log(log_line_obj, log_line_vals, message)
                    continue

                fulfillment_by = sale_order.amz_fulfillment_by
                if tax_rate != 0.0 and not vat_number:
                    self.process_b2c_amazon_order_ept(row, sale_order, invoice_date)
                else:
                    tax = self.find_b2b_amazon_vcs_tax_ept(row, sale_order, amazon_seller,
                                                           log_line_vals, line_no)
                    if not tax:
                        message = 'B2B Amazon Tax Id not found for %s, Please check Configurations.' % (
                            row.get('Seller Tax Registration Jurisdiction'))
                        self.create_log(log_line_obj, log_line_vals, message)
                        continue

                    self.process_b2b_amazon_order_ept(row, sale_order, tax, invoice_date)

                    partner = sale_order.partner_id
                    partner.write({'vat': vat_number})
                    _logger.info("Processed line %s in VCS Tax Report." % line_no)

                if invoice_type == 'out_refund':
                    amz_prod = self.find_amazon_vcs_product_ept(amazon_prod_dict, sku, instance,
                                                                fulfillment_by)
                    if not amz_prod:
                        message = 'Amazon Product with %s Seller SKU not found in line %d' % (
                            sku, line_no)
                        self.create_log(log_line_obj, log_line_vals, message)
                        continue

                    product = amz_prod.product_id
                    if product:
                        refund_data = self.prepare_vcs_refund_data_ept(row, sale_order, product,
                                                                       refund_data)

            draft_invoices = self.invoice_ids.filtered(lambda inv: inv.state == 'draft')
            for invoice in draft_invoices:
                invoice.action_post()
            self.process_refund(refund_data, log_obj, log_line_vals)
            self.write({'state': 'processed'})

        except Exception as e:
            log.write({'message': 'Exception Raised'})
            message = "%s with Line no %s" % (str(e), line_no) or ''
            self.create_log(log_line_obj, log_line_vals, message, order_id and order_id or '')
        return True

    def process_b2b_amazon_order_ept(self, row, sale_order, tax, invoice_date):
        if sale_order.order_line:
            order_lines = sale_order.order_line.filtered(lambda line: line.tax_id != tax)

            for order_line in order_lines:
                order_line.write({'tax_id': [(6, 0, [tax.id])]})
                order_line._compute_amount()

        self.create_or_find_b2b_invoices_and_process_ept( \
                row, sale_order, invoice_date, tax)
        return True

    def process_b2c_amazon_order_ept(self, row, sale_order, invoice_date):
        """
        Added by twinkalc to process for b2c orders and prepare vcs refund data and return that.
        """
        invoice_number = row.get('VAT Invoice Number', False)
        invoice_url = row.get('Invoice Url', '')

        invoices = sale_order.invoice_ids.filtered(
                lambda x: x.type == 'out_invoice' and x.state != 'cancel')
        if not invoices:
            lines = sale_order.order_line.filtered(lambda line: line.qty_to_invoice > 0)
            if not lines:
                return False
            invoices = sale_order.with_context({'vcs_invoice_number': invoice_number})._create_invoices()
        self.write({'invoice_ids': [(4, invoices and invoices.id)]})

        for invoice in invoices:
            invoice_vals = {}
            invoice_vals.update({'date': invoice_date, 'invoice_url': invoice_url})
            if invoice.state == 'draft' and \
                    sale_order.amz_seller_id.is_invoice_number_same_as_vcs_report:
                invoice_vals.update({'name': invoice_number})
            invoice.write(invoice_vals)
        return True

    def find_vcs_instance_ept(self, country, amazon_seller, instance_dict):
        """
        Added by Twinkalc on 30-sep-2020
        :param country: country record
        :param amazon_seller : amazon seller record
        :param instance_dict : instance dict
        This method will find the instance based on passed country.
        """
        instance_obj = self.env['amazon.instance.ept']
        instance = instance_obj.browse( \
            instance_dict.get((country.id, amazon_seller.id), False))
        if not instance:
            instance = amazon_seller.instance_ids.filtered( \
                lambda x: x.country_id.id == country.id)
            if instance:
                instance_dict.update( \
                    {(country.id, amazon_seller.id): instance.id})
        return instance

    def check_vcs_report_file_data_ept(self, row, log_line_vals, line_no):
        """
        Added by Twinkalc on 30-sep-2020
        :param row: VCS file data
        :param log_line_vals : log lines dict
        :param line_no : processing line no of file
        :return: This method will check the required data exist to process for
        update taxes in order and invoice lines.
        """
        marketplace_id = row.get('Marketplace ID', False)
        invoice_type = row.get('Transaction Type', False)
        order_id = row.get('Order ID', False)
        sku = row.get('SKU', False)
        qty = int(row.get('Quantity', 0)) if row.get('Quantity', 0) else 0.0
        ship_from_country = row.get('Ship From Country', False)
        log_line_obj = self.env['common.log.lines.ept']

        if not order_id:
            message = 'Order Id not found in line %d' % line_no
            self.create_log(log_line_obj, log_line_vals, message)
            return True

        if not marketplace_id:
            message = 'Marketplace Id not found in line %d' % line_no
            self.create_log(log_line_obj, log_line_vals, message)
            return True

        if not invoice_type:
            message = 'Invoice Type not found in line %d' % line_no
            self.create_log(log_line_obj, log_line_vals, message)
            return True

        if not sku:
            message = 'SKU not found in line %d' % line_no
            self.create_log(log_line_obj, log_line_vals, message)
            return True

        if invoice_type != 'SHIPMENT' and not qty:
            message = 'Qty to refund not found in line %d' % line_no
            self.create_log(log_line_obj, log_line_vals, message)
            return True

        if not ship_from_country:
            message = 'Ship from country not found in line %d' % line_no
            self.create_log(log_line_obj, log_line_vals, message)
            return True

        return False

    def find_vcs_country_ept(self, country_dict, marketplace_id, log_line_vals, line_no):
        """
        Added by Twinkalc on 30-sep-2020
        :param country_dict : country dict
        :param marketplace_id: marketplace id
        :param  log_line_vals : log line data
        :param line_no : processing line no of file
        :return: This method wil find the country based on amazon_marketplace_code
         and also update the country dict.
        """

        log_line_obj = self.env['common.log.lines.ept']
        res_country_obj = self.env['res.country']

        country = res_country_obj.browse( \
            country_dict.get(marketplace_id, False))
        if not country:
            country = res_country_obj.search( \
                [('amazon_marketplace_code', '=', marketplace_id)], limit=1)
            if not country:
                country = res_country_obj.search( \
                    [('code', '=', marketplace_id)], limit=1)
            if country:
                country_dict.update({marketplace_id: country.id})
        if not country:
            message = 'Country with code %s not found in line %d' % (
                marketplace_id, line_no)
            self.create_log(log_line_obj, log_line_vals, message)
        return country

    def create_or_find_b2b_invoices_and_process_ept(self, row, sale_order, invoice_date, tax):
        """
        Added by Twinkalc on 30-sep-2020
        :param row : file line data which is in process
        :param sale_order: sale order record
        :param  invoice_date : invoice date
        :param tax : tax which needs to update into the invoice line
        :return: This method wil find or create invoices and process
        to update tax in invoices.
        """

        vat_number = row.get('Buyer Tax Registration', False)
        invoice_number = row.get('VAT Invoice Number', False)

        invoices = sale_order.invoice_ids.filtered(
                lambda x: x.type == 'out_invoice' and x.state != 'cancel')
        if not invoices:
            lines = sale_order.order_line.filtered(lambda line: line.qty_to_invoice > 0)
            if not lines:
                return False
            invoices = sale_order._create_invoices()
        self.write({'invoice_ids': [(4, invoices and invoices.id)]})

        for invoice in invoices:
            if not invoice.partner_id.vat:
                invoice.partner_id.vat = vat_number

            payments_lines = []
            if invoice.invoice_payments_widget != 'false':
                payments_dict = json.loads(invoice.invoice_payments_widget)
                payments_content = payments_dict.get('content', [])
                for line in payments_content:
                    payments_lines.append(line.get('payment_id', False))

            invoice_line = invoice.mapped('invoice_line_ids').filtered(\
                lambda line: line.tax_ids != tax)
            if invoice_line:
                invoice.button_draft()
                invoice.write({'ref': invoice_number, 'date': invoice_date})

                if len(invoice_line) > 1:
                    for line in invoice_line:
                        line.with_context({'check_move_validity': False}).write( \
                            {'tax_ids': [(6, 0, [tax.id])]})
                else:
                    invoice_line.with_context({'check_move_validity': False}).write( \
                        {'tax_ids': [(6, 0, [tax.id])]})

                invoice.with_context({'check_move_validity': False})._recompute_tax_lines( \
                    recompute_tax_base_amount=True)
                invoice.action_post()
                for line in payments_lines:
                    invoice.js_assign_outstanding_line(line)

        return True

    def find_amazon_vcs_product_ept(self, amazon_prod_dict, sku, instance, fulfillment_by):
        """
        Added by Twinkalc on 30-sep-2020
        :param amazon_prod_dict : product data dict.
        :param sku: sku
        :param  instance : instance recorc
        :param fulfillment_by : fulfillment_by
        This method will fine tha amazon product based on instance, sku
        and fulfillment_by and update the amazon product dict
        """

        amz_prod_obj = self.env['amazon.product.ept']

        amz_prod = amz_prod_obj.browse( \
            amazon_prod_dict.get((sku, instance.id, fulfillment_by), False))
        if not amz_prod:
            amz_prod = amz_prod_obj.search( \
                [('seller_sku', '=', sku), ('instance_id', '=', instance.id),
                 ('fulfillment_by', '=', fulfillment_by)], limit=1)
            if amz_prod:
                amazon_prod_dict.update( \
                    {(sku, instance.id, fulfillment_by): amz_prod.id})
        return amz_prod

    def find_b2b_amazon_vcs_tax_ept(self, row, sale_order, amazon_seller, log_line_vals, line_no):
        """
        Added by Twinkalc on 30-sep-2020
        :param row : product data dict.
        :param sale_order: sale order record
        :param  amazon_seller : amazon seller record
        :param  log_line_vals : log line data
        :param line_no : processing line no of file
        This method will find the tax based on done the config in seller.
        """

        log_line_obj = self.env['common.log.lines.ept']
        vat_number = row.get('Buyer Tax Registration', False)
        tax_rate = float(row.get('Tax Rate', 0.0)) * 100
        is_outside_eu = row.get('Export Outside EU', False)
        seller_vat_number = row.get('Seller Tax Registration', False)

        tax = False
        if tax_rate == 0.0 or vat_number:
            vat_config = self.env["vat.config.ept"].search(
                [("company_id", "=", sale_order.company_id.id)])
            vat_config_line = vat_config.vat_config_line_ids.filtered(
                lambda x: x.vat == seller_vat_number)
            if vat_config_line:
                tax_country = vat_config_line.country_id
                outside_europe = True if ( \
                            is_outside_eu == 'true' or is_outside_eu == 'TRUE') else False
                tax = amazon_seller.mapped('b2b_amazon_tax_ids').filtered( \
                    lambda
                        x: x.jurisdiction_country_id == tax_country and x.is_outside_eu == outside_europe).mapped( \
                    'tax_id')
            else:
                message = 'No VAT Configuration found for line %d' % (line_no)
                self.create_log(log_line_obj, log_line_vals, message)
        return tax

    def find_amazon_vcs_sale_order_ept(self, row, instance, ship_from_country_dict,
                                       warehouse_country_dict):
        """
        Added by Twinkalc on 30-sep-2020
        :param row : file line data
        :param ship_from_country_dict: ship from country dict
        :param  warehouse_country_dict : warehouse data dict based
        on ship from country
        This method will find the sale order.
        return : sale order record.
        """

        res_country_obj = self.env['res.country']
        order_id = row.get('Order ID', False)
        sale_order_obj = self.env['sale.order']
        stock_warehouse_obj = self.env['stock.warehouse']

        ship_from_country = row.get('Ship From Country', False)

        sale_order = sale_order_obj.search(
            [('amz_instance_id', '=', instance.id),
             ('amz_order_reference', '=', order_id)])
        if len(sale_order) > 1:
            country = res_country_obj.browse(
                ship_from_country_dict.get(ship_from_country, False))
            if not country:
                country = res_country_obj.search( \
                    [('code', '=', ship_from_country)], limit=1)
                if country:
                    ship_from_country_dict.update( \
                        {ship_from_country: country.id})

            warehouses = stock_warehouse_obj.browse( \
                warehouse_country_dict.get(country.id, False))
            if not warehouses:
                warehouses = stock_warehouse_obj.search( \
                    [('partner_id.country_id', '=', country.id)])
                if warehouses:
                    warehouse_country_dict.update({country.id: warehouses.ids})

            sale_order = sale_order_obj.search(
                [('amz_instance_id', '=', instance.id),
                 ('amz_order_reference', '=', order_id),
                 ('warehouse_id', 'in', warehouses.ids)],
                limit=1)

        return sale_order

    def prepare_vcs_refund_data_ept(self, row, sale_order, product, refund_data):
        """
        Added by Twinkalc on 30-sep-2020
        :param sale_order : sale order record
        :param product: product record
        :param  qty : qty needs to process for refund
        :param refund_data : refund data dict
        This method will prepare the refund data to process for
        refund.
        """
        invoice_url = row.get('Invoice Url', '')
        invoice_number = row.get('VAT Invoice Number', False)
        qty = int(row.get('Quantity', 0)) if row.get('Quantity', 0) else 0.0

        if sale_order not in refund_data:
            refund_data.update({sale_order: {product: qty,
                                             'invoice_url': invoice_url,
                                             'vcs_invoice_number': invoice_number}})
        else:
            if product not in refund_data.get(sale_order):
                refund_data.get(sale_order).update({product: qty,
                                                    'invoice_url': invoice_url,
                                                    'vcs_invoice_number': invoice_number})
            else:
                existing_qty = refund_data.get(sale_order).get(product)
                refund_data.get(sale_order).update({product: existing_qty + qty})

        return refund_data

    def process_refund(self, refund_data, log_obj, log_line_vals):
        """
        @change: By Maulik Barad on Date 20-Jan-2019.
        """
        for order, data in refund_data.items():
            refund_vals = {}
            invoice = order.invoice_ids.filtered(
                lambda x: x.type == 'out_invoice' and x.state != 'cancel')

            if not invoice:
                message = 'invoice not found for order %s' % order.name
                self.create_log(log_obj, log_line_vals, message)
                continue
            if len(invoice) > 1:
                message = 'More than one invoice found for order %s' % order.name
                self.create_log(log_obj, log_line_vals, message, amazon_reference=order.name)
                continue

            refund_invoice = order.invoice_ids.filtered(
                lambda x: x.type == 'out_refund' and x.state != 'cancel')
            if len(refund_invoice) > 1:
                message = 'More than one refund invoice found for order %s' % order.name
                self.create_log(log_obj, log_line_vals, message, amazon_reference=order.name)
                continue
            if refund_invoice and refund_invoice.state in ('open', 'paid'):
                self.write({'invoice_ids': [(4, refund_invoice.id)],})
                refund_invoice.write({'invoice_url': data.get('invoice_url')})
                continue

            if not refund_invoice:
                date = invoice.date

                refund_obj = self.env['account.move.reversal']
                refund_process = refund_obj.create({
                    'move_id': invoice.id,
                    'reason': 'Refund Process Amazon Settlement Report'
                })
                refund_action = refund_process.reverse_moves()
                refund_invoice = self.env['account.move'].browse(refund_action['res_id'])
                refund_vals.update({'date': date,
                                    'invoice_url': data.get('invoice_url'),
                                    'ref': ('Refund - ' + invoice.ref),})
                products_to_be_refund = list(data.keys())

                if order.amz_seller_id.is_invoice_number_same_as_vcs_report:
                    refund_vals.update({'name': data.get('vcs_invoice_number')})

                refund_invoice.write(refund_vals)
                extra_invoice_lines = refund_invoice.invoice_line_ids.filtered(
                    lambda x: x.product_id not in products_to_be_refund)
                if extra_invoice_lines:
                    extra_invoice_lines.unlink()

                for product_id, qty in data.items():
                    exact_lines = refund_invoice.invoice_line_ids.filtered(
                        lambda x: x.product_id == product_id)
                    if len(exact_lines) > 1:
                        exact_line = exact_lines[0]
                        exact_line.write({'quantity': qty})
                        other_lines = exact_lines - exact_lines[0]
                        other_lines.unlink()
                    else:
                        exact_lines.with_context({'check_move_validity': False}).write(
                            {'quantity': qty})
                refund_invoice.with_context({'check_move_validity': False})._recompute_tax_lines(\
                    recompute_tax_base_amount=True)
                refund_invoice.action_post()
                self.write({'invoice_ids': [(4, refund_invoice.id)]})
        return True

    def create_log(self, log_line_obj, log_common_vals, message,
                   amazon_reference=''):
        """
        Use: Create Logs if there is any mismatch or exception raise
        Params: Log vals, Log Type, Action, Message, Amazon Reference
        Return: {}
        """
        log_common_vals.update({
            'message': message
        })
        if amazon_reference and not log_common_vals.get('amazon_order_reference', False):
            log_common_vals.update({'order_ref': amazon_reference or ''})
        log_line_obj.create(log_common_vals)
        return True

    def re_process_vcs_tax_report_file(self):
        """
        Added method is used to re process the vcs tax report file.
        """
        log_line_obj = self.env['common.log.lines.ept']
        model_id = log_line_obj.get_model_id('amazon.vcs.tax.report.ept')
        records = log_line_obj.search([('model_id', '=', model_id), ('res_id', '=', self.id)])
        records.unlink()
        self.process_vcs_tax_report_file()
        return True

    def auto_process_vcs_tax_report(self, args={}):
        """
        This method is used to auto process the vcs tax report.
        """
        seller_id = args.get('seller_id', False)
        if seller_id:
            seller = self.env['amazon.seller.ept'].search([('id', '=', seller_id)])
            vcs_reports = self.search(
                [('seller_id', '=', seller.id), ('state', 'in', ['_SUBMITTED_', '_IN_PROGRESS_'])])
            if vcs_reports:
                total_length = len(vcs_reports.ids)
                for x in range(0, total_length, 20):
                    reports = vcs_reports[x:x + 20]
                    for report in reports:
                        report.get_report_request_list()
                        if report.filtered(lambda r: r.state == '_DONE_' and r.report_id != False):
                            try:
                                report.get_report()

                            except Exception as e:
                                raise UserError(e)
                            time.sleep(2)
                        report.process_vcs_tax_report_file()
                        self._cr.commit()
                        time.sleep(3)

            else:
                reports = self.search([('seller_id', '=', seller.id),
                                       ('state', '=', '_DONE_'),
                                       ], order='id asc')
                for report in reports:
                    if not report.attachment_id:
                        while True:
                            try:
                                report.get_report()
                                break
                            except Exception as e:
                                raise UserError(e)
                    try:
                        report.process_vcs_tax_report_file()
                        self._cr.commit()
                    except:
                        continue
                    time.sleep(3)
        return True

    def open_invoices(self):
        """
        Opens the tree view of Invoices.
        @author: Maulik Barad on Date 20-Jan-2019.
        """
        return {
            'domain': "[('id', 'in', " + str(self.invoice_ids.ids) + " )]",
            'name': 'Invoices',
            'view_mode': 'tree,form',
            'res_model': 'account.move',
            'type': 'ir.actions.act_window',
        }

    def decode_amazon_encrypted_vcs_attachments_data(self, attachment_id, job):
        """
        Added method to decode the encrypted VCS attachments data.
        """
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        req = {'dbuuid': dbuuid, 'report_id': self.report_id,
            'datas': attachment_id.datas.decode(), 'amz_report_type': 'vcs_tax_report'}
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/decode_data', params=req, timeout=1000)
        if response.get('result'):
            imp_file = StringIO(base64.b64decode(response.get('result')).decode('ISO-8859-1'))
        elif self._context.get('is_auto_process', False):
            job.log_lines.create({'message': 'Error found in Decryption of Data %s' % response.get('error', '')})
            return True
        else:
            raise Warning(response.get('error'))
        return imp_file
