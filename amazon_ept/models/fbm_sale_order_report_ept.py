# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.
"""
Define class to process for FBM sale orders
"""

import base64
import csv
import time
from io import StringIO

import pytz
from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError

from ..endpoint import DEFAULT_ENDPOINT

utc = pytz.utc


class FbmSaleOrderReportEpt(models.Model):
    """
    Added class to get FBM sale order report file and process FBM sale order report file
    to import FBM sale report
    """
    _name = "fbm.sale.order.report.ept"
    _description = "FBM Sale Order Report Ept"
    _inherit = ['mail.thread']
    _order = 'name desc'

    seller_id = fields.Many2one('amazon.seller.ept', string='Seller',
                                help="Select Amazon Seller Name listed in odoo")
    company_id = fields.Many2one('res.company', string="Company",
                                 related="seller_id.company_id", store=False)
    name = fields.Char(size=256, readonly=True)
    attachment_id = fields.Many2one('ir.attachment', string='Attachment')
    report_type = fields.Char(size=256)
    report_request_id = fields.Char(size=256, string='Report Request ID')
    report_id = fields.Char(size=256, string='Report ID')
    requested_date = fields.Datetime(default=time.strftime("%Y-%m-%d %H:%M:%S"))
    state = fields.Selection(\
        [('draft', 'Draft'), ('_SUBMITTED_', 'SUBMITTED'),
         ('_IN_PROGRESS_', 'IN_PROGRESS'),
         ('_CANCELLED_', 'CANCELLED'), ('_DONE_', 'DONE'),
         ('_DONE_NO_DATA_', 'DONE_NO_DATA'), ('processed', 'PROCESSED'),
         ('imported', 'Imported'),
         ('partially_processed', 'Partially Processed'), ('closed', 'Closed')
         ],
        string='Report Status', default='draft')
    user_id = fields.Many2one('res.users', string="Requested User")
    sales_order_report_ids = fields.One2many('sale.order',
                                             'amz_sales_order_report_id',
                                             string="Sale Orders")
    sales_order_count = fields.Integer(compute='_compute_order_count',
                                       string='# of Orders')
    child_sales_order_report_id = fields.Many2one('fbm.sale.order.report.ept',
                                                  string='Unshipped Sales Order Report')
    is_parent = fields.Boolean('Is Parent Report', default=True)

    @api.model
    def auto_import_unshipped_order_report(self, seller):
        """
        This method is used to auto import unshipped order report
        param seller : seller record
        """
        if seller.id:
            sale_order_report = self.create(
                {'report_type': '_GET_FLAT_FILE_ORDER_REPORT_DATA_',
                 'seller_id': seller.id,
                 'state': 'draft',
                 'requested_date': time.strftime("%Y-%m-%d %H:%M:%S")
                 })
            sale_order_report.with_context( \
                is_auto_process=True).request_report()
        return True

    @api.model
    def auto_process_unshipped_order_report(self, seller):
        """
        This method is used to auto process unshipped order report
        param seller : seller record
        """
        seller_id = seller.id
        if seller_id:
            sale_order_reports = self.search([('seller_id', '=', seller.id),
                                              ('state', 'in', ['_SUBMITTED_', '_IN_PROGRESS_'])])
            for sale_order_report in sale_order_reports:
                sale_order_report.with_context(
                    is_auto_process=True).get_report_request_list()
            sale_order_reports = self.search([('seller_id', '=', seller.id),
                                              ('state', 'in',
                                               ['_DONE_', '_SUBMITTED_', '_IN_PROGRESS_']),
                                              ('report_id', '!=', False)])
            for sale_order_report in sale_order_reports:
                sale_order_report.with_context(
                    is_auto_process=True).get_report()
                sale_order_report.process_fbm_sale_order_file()
                self._cr.commit()
        return True

    @api.model
    def create(self, vals):
        """
        will set the fbm sale order report name
        """
        seq = self.env['ir.sequence'].next_by_code(
            'fbm_shipped_sale_order_report_ept_sequence') or '/'
        vals['name'] = seq
        return super(FbmSaleOrderReportEpt, self).create(vals)

    @api.model
    def default_get(self, fields):
        """
        inherited to update the report type
        """
        res = super(FbmSaleOrderReportEpt, self).default_get(fields)
        if not fields:
            return res
        res.update({'report_type': '_GET_FLAT_FILE_ORDER_REPORT_DATA_',
                    })
        return res

    def _compute_order_count(self):
        """
        This method Calculate the Total sales order with Sale order Report Id.
        :return: True
        """
        sale_order_obj = self.env['sale.order']
        self.sales_order_count = sale_order_obj.search_count( \
            [('amz_sales_order_report_id', '=', self.id)])

    def action_view_sales_order(self):
        """
        This method show the Sales order connected with particular report.
        :return:action
        """
        action = {
            'name': 'Sales Orders',
            'view_type': 'form',
            'view_mode': 'tree,form',
            'res_model': 'sale.order',
            'type': 'ir.actions.act_window',
        }

        orders = self.env['sale.order'].search(
            [('amz_sales_order_report_id', '=', self.id)])
        if len(orders) > 1:
            action['domain'] = [('id', 'in', orders.ids)]
        elif orders:
            action['views'] = [
                (self.env.ref('sale.view_order_form').id, 'form')]
            action['res_id'] = orders.id
        return action

    def request_report(self):
        """
        This method request in Amazon for unshipped Sales Orders.
        :return:True
        """
        seller = self.seller_id
        report_type = self.report_type
        instances = seller.instance_ids
        marketplace_ids = tuple(map(lambda x: x.market_place_id, instances))

        if not seller:
            raise UserError(_('Please select Seller'))

        kwargs = self.prepare_fbm_unshipped_data_request_ept('request_report_fbm_v13')
        kwargs.update({'report_type': report_type,
                       'marketplace_ids': marketplace_ids,
                       'ReportOptions': "ShowSalesChannel=true"})

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request',
                                         params=kwargs, timeout=1000)
        if response.get('reason'):
            raise UserError(_(response.get('reason')))
        result = response.get('result')
        self.update_report_history(result)
        return True

    def create_record_for_all_orders(self):
        """
        This method create the child records.
        :return: record object
        """
        sales_report_object = self.env['fbm.sale.order.report.ept']
        sales_report_values = {
            'seller_id': self.seller_id.id,
            'report_type': '_GET_FLAT_FILE_ACTIONABLE_ORDER_DATA_',
        }
        record = sales_report_object.create(sales_report_values)
        return record

    def get_report_request_list(self):
        """
        This method check the status of the Report.
        :return:True
        """
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select Seller'))

        if not self.report_request_id:
            return True

        kwargs = self.prepare_fbm_unshipped_data_request_ept('get_report_request_list_v13')
        kwargs.update({'request_ids': (self.report_request_id,)})

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request',
                                         params=kwargs)
        if response.get('reason'):
            raise UserError(_(response.get('reason')))
        list_of_wrapper = response.get('result')
        for result in list_of_wrapper:
            self.update_report_history(result)

        return True

    def get_report(self):
        """
        This method get the report and store in one csv file and attached with one attachment.
        :return:True
        """
        seller = self.seller_id
        if not seller:
            raise UserError(_('Please select seller'))
        if not self.report_id:
            return True

        kwargs = self.prepare_fbm_unshipped_data_request_ept('get_report_v13')
        kwargs.update({'report_id': self.report_id,
                       'amz_report_type': 'fbm_report', })

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request',
                                         params=kwargs, timeout=1000)
        if response.get('reason'):
            raise UserError(_(response.get('reason')))
        result = response.get('result')
        file_name = "FBM_Sale_Order_" + time.strftime(
            "%Y_%m_%d_%H%M%S") + '.csv'

        attachment = self.env['ir.attachment'].create({
            'name': file_name,
            'datas': result.encode(),
            'res_model': 'mail.compose.message',
            'type': 'binary'
        })
        self.message_post(body=_("<b>FBM Sale Order Report Downloaded</b>"),
                          attachment_ids=attachment.ids)
        self.write({'attachment_id': attachment.id})
        return True

    @api.model
    def update_report_history(self, request_result):
        """
        used to set the report state and report id from the result
        """
        report_info = request_result.get('ReportInfo', {})
        report_request_info = request_result.get('ReportRequestInfo', {})
        request_id = report_state = report_id = False
        if report_request_info:
            request_id = str(
                report_request_info.get('ReportRequestId', {}).get('value', ''))
            report_state = report_request_info.get('ReportProcessingStatus',
                                                   {}).get('value',
                                                           '_SUBMITTED_')
            report_id = report_request_info.get('GeneratedReportId', {}).get( \
                'value', False)
        elif report_info:
            report_id = report_info.get('ReportId', {}).get('value', False)
            request_id = report_info.get('ReportRequestId', {}).get('value',
                                                                    False)

        if report_state == '_DONE_' and not report_id:
            self.get_report_request_list()
        vals = {}
        if not self.report_request_id and request_id:
            vals.update({'report_request_id': request_id})
        if report_state:
            vals.update({'state': report_state})
        if report_id:
            vals.update({'report_id': report_id})
        self.write(vals)
        return True

    def download_report(self):
        """
        Through this method, user can download the report.
        :return:True
        """
        self.ensure_one()
        if self.attachment_id:
            return {
                'type': 'ir.actions.act_url',
                'url': '/web/content/%s?download=true' % (
                    self.attachment_id.id),
                'target': 'self',
            }
        return True

    def prepare_fbm_customer_vals(self, row):
        """
        This method prepare the customer vals
        :param row: row of data
        :return: customer vals
        """
        return {
            'BuyerEmail': row.get('buyer-email'),
            'BuyerName': row.get('buyer-name'),
            'BuyerNumber': row.get('buyer-phone-number'),
            'AddressLine1': row.get('ship-address-1'),
            'AddressLine2': row.get('ship-address-2'),
            'AddressLine3': row.get('ship-address-3'),
            'City': row.get('ship-city'),
            'ShipName': row.get('recipient-name'),
            'CountryCode': row.get('ship-country'),
            'StateOrRegion': row.get('ship-state') or False,
            'PostalCode': row.get('ship-postal-code'),
            'ShipNumber': row.get('ship-phone-number'),
            'vat-number': row.get('vat-number', '')
        }

    def prepare_fbm_unshipped_data_request_ept(self, emipro_api):
        """
        This method will prepare the FBM unshipped data request.
        """
        account = self.env['iap.account'].search( \
            [('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        seller_id = self.seller_id

        return {'merchant_id': seller_id.merchant_id and str(seller_id.merchant_id) or False,
                'auth_token': seller_id.auth_token and str(seller_id.auth_token) or False,
                'app_name': 'amazon_ept',
                'account_token': account.account_token,
                'emipro_api': emipro_api,
                'dbuuid': dbuuid,
                'amazon_marketplace_code': seller_id.country_id.amazon_marketplace_code or
                                           seller_id.country_id.code}

    def process_fbm_sale_order_file(self):
        """
        This method process the attached file with record and create Sales orders.
        :return:True
        """
        self.ensure_one()
        ir_cron_obj = self.env['ir.cron']
        common_log_book_obj = self.env['common.log.book.ept']
        common_log_line_obj = self.env['common.log.lines.ept']

        if not self._context.get('is_auto_process', False):
            ir_cron_obj.with_context({'raise_warning': True}).find_running_schedulers( \
                'ir_cron_process_amazon_unshipped_orders_seller_', self.seller_id.id)

        marketplaceids = tuple(map(lambda x: x.market_place_id, self.seller_id.instance_ids))
        if not marketplaceids:
            raise UserError(
                "There is no any instance is configured of seller %s" % (self.seller_id.name))
        if not self.attachment_id:
            raise UserError(_("There is no any report are attached with this record."))

        file_order_list = self.get_unshipped_order()
        unshipped_order_list = []
        business_prime_dict = {}

        kwargs = self.prepare_fbm_unshipped_data_request_ept('get_order_v13')
        kwargs.update({'marketplaceids': marketplaceids})
        model_id = self.env['ir.model']._get('fbm.sale.order.report.ept').id

        log_book = common_log_book_obj.amazon_create_transaction_log('import',
                                                                     model_id,
                                                                     self.id)

        for x in range(0, len(file_order_list), 50):
            sale_orders_list = file_order_list[x:x + 50]
            kwargs.update({'sale_order_list': sale_orders_list})
            # TODO: Max_request_quota = 6, restore_rate = 1req/min
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs,
                                             timeout=1000)
            if response.get('reason'):
                if self._context.get('is_auto_process'):
                    message = 'FBM Sale Order Report Auto Process'
                    common_log_line_obj.amazon_create_order_log_line(message, model_id, self.id,
                                                                     False, False,
                                                                     log_book)
                else:
                    raise UserError(_(response.get('reason')))
            else:
                unshipped_order_list, business_prime_dict = self.process_fbm_shipped_order_response_ept(
                    response, unshipped_order_list, business_prime_dict)

        self.process_prepare_unshipped_order_list_ept(unshipped_order_list, business_prime_dict,
                                                      log_book)
        if not log_book.log_lines:
            log_book.unlink()
        self.write({'state': 'processed'})
        return True

    def process_prepare_unshipped_order_list_ept(self, unshipped_order_list,
                                                 business_prime_dict, log_book):
        marketplace_obj = self.env['amazon.marketplace.ept']
        common_log_line_obj = self.env['common.log.lines.ept']

        imp_file = self.decode_amazon_encrypted_fbm_attachments_data( \
            self.attachment_id, log_book)
        reader = csv.DictReader(imp_file, delimiter='\t')
        order_dict = dict()
        marketplace_dict = {}
        amazon_instance_dict = {}
        order_skip_list = []

        message = 'FBM Sale Order Report'
        model_id = self.env['ir.model']._get('fbm.sale.order.report.ept').id
        common_log_line_obj.amazon_create_order_log_line(message, model_id, self.id, False, False,
                                                         log_book)

        for row in reader:
            if not row.get('sku'):
                continue
            if not row.get('order-id') in unshipped_order_list:
                continue
            amz_ref = row.get('order-id')
            marketplace_record = marketplace_dict.get(row.get('sales-channel'))
            if not marketplace_record:
                marketplace_record = marketplace_obj.search(
                    [('name', '=', row.get('sales-channel')),
                     ('seller_id', '=', self.seller_id.id)])
                marketplace_dict.update({row.get('sales-channel'): marketplace_record})

            instance = amazon_instance_dict.get((self.seller_id, marketplace_record))
            if not instance:
                instance = self.seller_id.instance_ids.filtered(
                    lambda l: l.marketplace_id.id == marketplace_record.id)
                amazon_instance_dict.update(
                    {(self.seller_id, marketplace_record): instance})

            if (amz_ref, instance.id) in order_skip_list:
                continue
            order = self.check_order_exist_in_odoo(amz_ref, instance.id)
            if order:
                order_skip_list.append((amz_ref, instance.id))
                continue
            order_dict = self.prepare_order_dict(order_dict, amz_ref,
                                                 instance.id, row)

        self.process_fbm_unshipped_order_dict(order_dict, business_prime_dict,
                                              log_book)
        return True

    def process_fbm_unshipped_order_dict(self, order_dict, business_prime_dict, log_book):
        amazon_instance_obj = self.env['amazon.instance.ept']

        state_dict = {}
        country_dict = {}
        dict_product_details = {}

        count_order_number = 0
        for order_ref, order_details in order_dict.items():
            skip_order, dict_product_details = self.create_or_find_amazon_fbm_product( \
                order_ref, order_details, dict_product_details, log_book)
            if skip_order:
                continue

            customer_vals = self.prepare_fbm_customer_vals(order_details[0])
            instance = amazon_instance_obj.browse(order_ref[1])
            partner = self.get_partner(customer_vals, state_dict, country_dict,
                                       instance)
            order = self.create_amazon_fbm_unshipped_order(instance, partner,
                                                           order_ref,
                                                           order_details,
                                                           business_prime_dict)
            self.create_amazon_fbm_unshipped_order_lines(order, instance, order_details,
                                                         dict_product_details)
            order.process_orders_and_invoices_ept()
            count_order_number += 1
            if count_order_number >= 10:
                self._cr.commit()
                count_order_number = 0
        return True

    def create_amazon_fbm_unshipped_order(self, instance, partner, order_ref,
                                          order_details, business_prime_dict):
        sale_order_obj = self.env['sale.order']
        seller = self.seller_id
        order_values = {'PurchaseDate': {
            'value': order_details[0].get('purchase-date') or False}, \
            'AmazonOrderId': {'value': order_ref[0] or False}}
        vals = sale_order_obj.prepare_amazon_sale_order_vals(instance,
                                                             partner,
                                                             order_values)
        ordervals = sale_order_obj.create_sales_order_vals_ept(vals)
        if not seller.is_default_odoo_sequence_in_sales_order:
            name = seller.order_prefix + order_ref[
                0] if seller.order_prefix else order_ref[0]
            ordervals.update({'name': name})
        updated_ordervals = self.prepare_updated_ordervals(instance,
                                                           order_ref)
        if business_prime_dict.get(order_ref[0], False):
            updated_ordervals.update(
                {'is_business_order': business_prime_dict.get(
                    order_ref[0]).get('is_business_order'),
                 'is_prime_order': business_prime_dict.get(
                     order_ref[0]).get('is_prime_order')})
        ordervals.update(updated_ordervals)
        order = sale_order_obj.create(ordervals)
        return order

    def process_fbm_shipped_order_response_ept(self, response,
                                               unshipped_order_list,
                                               business_prime_dict):
        """
        This method will process response and prepare unshipped order list and business prime dict
        param response : order response
        param unshipped_order_list : list of unshipped order
        param business_prime_dict : business prime dict data
        return : unshipped_order_list and business_prime_dict
        """
        result = []
        if response.get('result'):
            result = [response.get('result')]
            time.sleep(4)

        for wrapper_obj in result:
            orders = []
            if not isinstance(wrapper_obj.get('Orders', {}).get('Order', []),
                              list):
                orders.append(wrapper_obj.get('Orders', {}).get('Order', {}))
            else:
                orders = wrapper_obj.get('Orders', {}).get('Order', [])
            for order in orders:
                order_status = order.get('OrderStatus').get('value')
                amazon_order_ref = order.get('AmazonOrderId', {}).get('value',
                                                                      False)
                if not amazon_order_ref:
                    continue
                is_business_order = True if order.get('IsBusinessOrder',
                                                      {}).get('value', '').lower() in ['true',
                                                                                       't'] else False
                is_prime_order = True if order.get('IsPrime', {}).get('value', '').lower() in [
                    'true', 't'] else False

                if order_status == 'Unshipped':
                    if not amazon_order_ref in unshipped_order_list:
                        unshipped_order_list.append(amazon_order_ref)
                        if is_business_order or is_prime_order:
                            business_prime_dict.update({amazon_order_ref: { \
                                'is_business_order': is_business_order, \
                                'is_prime_order': is_prime_order}})

        return unshipped_order_list, business_prime_dict

    def get_unshipped_order(self):
        """
        Give the list of unshipped orders.
        :return: unshipped order list
        """
        file_order_list = []
        imp_file = self.decode_amazon_encrypted_fbm_attachments_data( \
            self.attachment_id, job=False)
        reader = csv.DictReader(imp_file, delimiter='\t')
        for row in reader:
            file_order_list.append(row.get('order-id'))
        return file_order_list

    def prepare_order_dict(self, order_dict, amz_ref, instance_id, row):
        """
        This method prepare the order dictionary.
        :param order_dict: order dictionary
        :param amz_ref: amazon order id
        :param instance_id : instance record
        :param row: file line
        :return: order dictionary
        """

        fbm_order_dict = {
            'order-item-id': row.get('order-item-id'),
            'purchase-date': row.get('purchase-date'),
            'buyer-email': row.get('buyer-email'),
            'buyer-name': row.get('buyer-name'),
            'buyer-phone-number': row.get('buyer-phone-number'),
            'ship-phone-number': row.get('ship-phone-number'),
            'sku': row.get('sku'),
            'product-name': row.get('product-name'),
            'quantity-purchased': row.get('quantity-purchased'),
            'item-price': row.get('item-price'),
            'item-tax': row.get('item-tax'),
            'shipping-price': row.get('shipping-price'),
            'shipping-tax': row.get('shipping-tax'),
            'recipient-name': row.get('recipient-name'),
            'ship-address-1': row.get('ship-address-1'),
            'ship-address-2': row.get('ship-address-2'),
            'ship-city': row.get('ship-city'),
            'ship-state': row.get('ship-state'),
            'ship-postal-code': row.get('ship-postal-code'),
            'ship-country': row.get('ship-country'),
            'item-promotion-discount': row.get( \
                'item-promotion-discount'),
            'ship-promotion-discount': row.get( \
                'ship-promotion-discount'),
            'sales-channel': row.get('sales-channel'),
            'vat-number': row.get('buyer-tax-registration-id', '')}

        if order_dict.get((amz_ref, instance_id)):
            fbm_order_dict.update({'promise-date': row.get('promise-date'), })
            order_dict.get((amz_ref, instance_id)).append(fbm_order_dict)
        else:
            order_dict.update({(amz_ref, instance_id): [fbm_order_dict]})
        return order_dict

    def check_order_exist_in_odoo(self, amz_ref, instance_id):
        """
        This method check that the order is already exist in odoo or not.
        :param amz_ref: Amazon Order Reference
        :param instance_id : amazon instance record.
        :return: True or False
        """
        sale_order_obj = self.env['sale.order']
        order = sale_order_obj.search( \
            [('amz_instance_id', '=', instance_id),
             ('amz_order_reference', '=', amz_ref),
             ('amz_fulfillment_by', '=', 'FBM')])
        return order

    def get_partner(self, vals, state_dict, country_dict, instance):
        """
        This method is find the partner and if it's not found than it create the new partner.
        :param vals: {}
        :param state_dict: {}
        :param country_dict: {}
        :param instance: amazon.instance.ept()
        :return: Partner {}
        """
        partner_obj = self.env['res.partner']
        country, state = self.get_fbm_order_state_and_country_ept( \
            vals, country_dict, state_dict)
        email = vals.get('BuyerEmail', '')
        buyer_name = vals.get('BuyerName', '')
        shipping_address_name = vals.get('ShipName', '')
        street = vals.get('AddressLine1', '')
        address_line2 = vals.get('AddressLine2', '')
        address_line3 = vals.get('AddressLine3', '')
        street2 = "%s %s" % (address_line2, address_line3) \
            if address_line2 or address_line3 else False
        city = vals.get('City', '')
        zip_code = vals.get('PostalCode', '')
        phone = vals.get('ShipNumber', '')
        vat = vals.get('vat-number', '')

        new_partner_vals = {
            'street': street,
            'street2': street2,
            'zip': zip_code,
            'city': city,
            'country_id': country.id if country else False,
            'state_id': state.id if state else False,
            'phone': phone,
            'company_id': instance.company_id.id,
            'email': email,
            'lang': instance.lang_id and instance.lang_id.code,
            'is_amz_customer': True,
            'vat': vat
        }

        partner, invoice_partner = self.search_amazon_fbm_invoice_and_partner_ept(
            instance, buyer_name, new_partner_vals)

        delivery = invoice_partner if ( \
                    invoice_partner.name == shipping_address_name and invoice_partner.street == street \
                    and (not invoice_partner.street2 or invoice_partner.street2 == street2) \
                    and invoice_partner.zip == zip_code and invoice_partner.city == city \
                    and invoice_partner.country_id == country \
                    and invoice_partner.state_id == state) else False
        if not delivery:
            delivery = partner_obj.with_context(is_amazon_partner=True).search(
                [('name', '=', shipping_address_name), ('street', '=', street),
                 '|', ('street2', '=', False), ('street2', '=', street2),
                 ('zip', '=', zip_code),
                 ('city', '=', city),
                 ('country_id', '=', country.id if country else False),
                 ('state_id', '=', state.id if state else False),
                 '|', ('company_id', '=', False),
                 ('company_id', '=', instance.company_id.id)], limit=1)
            if not delivery:
                delivery = partner_obj.with_context(
                    tracking_disable=True).create({ \
                    'name': shipping_address_name, \
                    'type': 'delivery', \
                    'parent_id': partner.id, \
                    **new_partner_vals, \
                    })
        return {'invoice_partner': invoice_partner.id,
                'shipping_partner': delivery.id}

    def get_fbm_order_state_and_country_ept(self, vals, country_dict,
                                            state_dict):
        """
        This method is used to get the FBM order state and country
        """
        partner_obj = self.env['res.partner']
        country = country_dict.get(vals.get('CountryCode'), False)
        if not country:
            country = partner_obj.get_country(vals.get('CountryCode'))
            country_dict.update({vals.get('CountryCode'): country})

        state = state_dict.get(vals.get('StateOrRegion'), False)
        if not state and country and vals.get('StateOrRegion') != '--':
            state = partner_obj.create_or_update_state_ept( \
                country.code, vals.get('StateOrRegion'), vals.get('PostalCode'), country)
            state_dict.update({vals.get('StateOrRegion'): state})

        return country, state

    def search_amazon_fbm_invoice_and_partner_ept(self, instance, buyer_name,
                                                  new_partner_vals):
        """
        This method is used to search the amazon FBM partner and invoice partner
        """
        partner_obj = self.env['res.partner']
        email = new_partner_vals.get('email')

        if instance.amazon_property_account_payable_id:
            new_partner_vals.update({
                'property_account_payable_id': instance.amazon_property_account_payable_id.id})
        if instance.amazon_property_account_receivable_id:
            new_partner_vals.update({
                'property_account_receivable_id': instance.amazon_property_account_receivable_id.id})

        city = new_partner_vals.get('city', '')
        state_id = new_partner_vals.get('state_id', False)
        country_id = new_partner_vals.get('country_id', False)

        if not email and buyer_name == 'Amazon':
            partner = partner_obj.with_context(is_amazon_partner=True).search( \
                [('name', '=', buyer_name), ('is_company', '=', False), ('city', '=', city),
                 ('state_id', '=', state_id), ('country_id', '=', country_id),
                 '|', ('company_id', '=', False), ('company_id', '=', instance.company_id.id)],
                limit=1)
        else:
            partner = partner_obj.with_context(is_amazon_partner=True).search( \
                [('email', '=', email), ('is_company', '=', False),
                 '|', ('company_id', '=', False),
                 ('company_id', '=', instance.company_id.id)], limit=1)

        if not partner:
            partner = partner_obj.with_context(tracking_disable=True).create({
                'name': buyer_name,
                'type': 'invoice',
                'is_company': False,
                **new_partner_vals,
            })
            invoice_partner = partner
        elif buyer_name and partner.name != buyer_name:
            invoice_partner = partner_obj.with_context(
                tracking_disable=True).create({ \
                'parent_id': partner.id, \
                'name': buyer_name, \
                'type': 'invoice', \
                **new_partner_vals, \
                })
        else:
            invoice_partner = partner

        return partner, invoice_partner

    def create_or_find_amazon_fbm_product(self, order_ref, order_details,
                                          product_details, job):
        """
        This method is find product in odoo based on sku. If not found than create new product.
        :param sku:Product SKU
        :param product_name:Product name or Description
        :param seller_id:Seller Object
        :param instance: instance Object
        :return: Odoo Product Object
        """
        product_obj = self.env['product.product']
        amz_product_obj = self.env['amazon.product.ept']
        instance_obj = self.env['amazon.instance.ept']
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = self.env['ir.model']._get('amazon.product.ept').id

        instance_id = instance_obj.browse(order_ref[1])
        skip_order = False
        for order_detail in order_details:
            sku = order_detail.get('sku')
            amz_product = amz_product_obj.search_amazon_product( \
                order_ref[1], sku, 'FBM')
            if not amz_product:
                odoo_product = product_obj.search([('default_code', '=', sku)])
                if not odoo_product and instance_id.seller_id.create_new_product:
                    odoo_product = product_obj.create({
                        'name': order_detail.get('product-name'),
                        'description_sale': order_detail.get('product-name'),
                        'default_code': sku,
                        'type': 'product'})
                    amazon_product_id = amz_product_obj.create(
                        {'name': odoo_product.name, \
                         'product_id': odoo_product.id, \
                         'seller_sku': odoo_product.default_code, \
                         'fulfillment_by': 'FBM', \
                         'instance_id': order_ref[1]})
                    message = 'Product is not available in Amazon Odoo Connector and Odoo,' \
                              'So it\'ll created in both.'
                    common_log_line_obj.amazon_create_order_log_line( \
                        message, model_id, amazon_product_id, \
                        order_ref[0], order_detail.get('sku'), job)

                elif odoo_product:
                    amz_product_obj.create({'name': odoo_product.name,
                                            'product_id': odoo_product.id,
                                            'seller_sku': odoo_product.default_code,
                                            'fulfillment_by': 'FBM',
                                            'instance_id': order_ref[1]})
                else:
                    skip_order = True
                    message = 'Order skipped due to product is not available.'
                    common_log_line_obj.amazon_create_order_log_line( \
                        message, model_id, False, order_ref[0], \
                        order_detail.get('sku'), job)
            else:
                odoo_product = amz_product.product_id
            product_details.update({(sku, order_ref[1]): odoo_product})
        return skip_order, product_details

    def check_order_line_exist(self, instance, amz_ref, order_line_ref,
                               sale_order_obj):
        """
        This method find the order line is exist in Sales order or not.
        :param instance:instance object
        :param amz_ref:Order Reference
        :param order_line_ref: Order Line reference
        :param sale_order_obj:Sale order Object
        :return: Order line or False
        """
        order = sale_order_obj.search(
            [('amz_instance_id', '=', instance.id),
             ('amz_order_reference', '=', amz_ref)])
        order_line = order.order_line.filtered(
            lambda x: x.amazon_order_item_id == order_line_ref)
        if order_line:
            return order_line
        else:
            return False

    def prepare_updated_ordervals(self, instance, order_ref):
        """
        This method prepare the order vals.
        :param expected_delivery_date: Expected Delivery Date
        :param instance: instance object
        :param seller: seller object
        :param order_ref: order reference
        :return: Order Vals
        """
        ordervals = {
            'amz_sales_order_report_id': self.id,
            'amz_instance_id': instance and instance.id or False,
            'amz_seller_id': instance.seller_id.id,
            'amz_fulfillment_by': 'FBM',
            'amz_order_reference': order_ref[0] or False,
            'auto_workflow_process_id': instance.seller_id.fbm_auto_workflow_id.id
        }
        return ordervals

    def create_amazon_fbm_unshipped_order_lines(self, order, instance, order_details,
                                                dict_product_details):
        """
        This method prepare order lines.
        :param order: order Object
        :param instance: instance object
        :param order_details: sale order line from dictionary
        :param sale_order_line_obj: sale order line object
        :return: True
        """
        sale_order_line_obj = self.env['sale.order.line']

        for order_detail in order_details:
            if not order_detail.get('sku'):
                continue
            taxargs = {}
            product = dict_product_details.get(
                (order_detail.get('sku'), instance.id))
            item_price = self.get_item_price(order_detail, instance)
            unit_price = item_price / float(
                order_detail.get('quantity-purchased'))
            item_tax = float(order_detail.get('item-tax'))
            if instance.is_use_percent_tax:  # country_id.code == 'US':
                item_tax_percent = (item_tax * 100) / unit_price
                amz_tax_id = order.amz_instance_id.amz_tax_id
                taxargs = {'line_tax_amount_percent': item_tax_percent,
                           'tax_id': [(6, 0, [amz_tax_id.id])]}
            line_vals = {
                'order_id': order.id,
                'product_id': product.id,
                'company_id': instance.company_id.id or False,
                'name': order_detail.get('product-name'),
                'order_qty': order_detail.get('quantity-purchased'),
                'price_unit': unit_price,
                'discount': False,
                'shipping-price': order_detail.get('shipping-price', 0.0),
                'shipping-tax': order_detail.get('shipping-tax', 0.0)
            }
            order_line_vals = sale_order_line_obj.create_sale_order_line_ept( \
                line_vals)
            order_line_vals.update({
                'amazon_order_item_id': order_detail.get('order-item-id'),
                'line_tax_amount': item_tax,
                **taxargs})
            sale_order_line_obj.create(order_line_vals)
            self.create_fbm_unshipped_chargable_order_line_ept(instance, order, \
                                                               order_detail)
        return True

    def get_fbm_unshipped_order_line_vals(self, instance, order, product_id, price_unit,
                                          order_detail):
        """
        This method will prepare the FBM unshipped order line vals
        """
        unshipped_order_line_vals = {
            'order_id': order.id,
            'product_id': product_id.id,
            'company_id': instance.company_id.id or False,
            'name': product_id.description_sale or product_id.name,
            'product_uom_qty': '1.0',
            'price_unit': price_unit,
            'discount': False,
            'amazon_order_item_id': order_detail.get('order-item-id')}
        return unshipped_order_line_vals

    def amz_find_product(self, order_detail):
        """
        This method find the odoo product.
        :param order_detail: order line
        :return: odoo product object
        """
        amz_product_obj = self.env['amazon.product.ept']
        amz_product = amz_product_obj.search(
            [('seller_sku', '=', order_detail.get('sku'))])
        product = amz_product.product_id
        return product

    def create_fbm_unshipped_chargable_order_line_ept(self, instance, order, order_detail):
        """
        This method is used to create FBM unshipped chargeable order line
        """
        sale_order_line_obj = self.env['sale.order.line']
        if float(order_detail.get( \
                'shipping-price')) > 0 and instance.seller_id.shipment_charge_product_id:
            shipping_price = self.get_shipping_price(order_detail, instance)
            shipment_charge_product_id = instance.seller_id.shipment_charge_product_id
            charges_vals = self.get_fbm_unshipped_order_line_vals(instance, order,
                                                                  shipment_charge_product_id,
                                                                  shipping_price, order_detail)
            if instance.is_use_percent_tax:
                shipping_tax = order_detail.get('shipping-tax', 0.0)
                ship_tax_percent = (float(shipping_tax) * 100) / float(shipping_price)
                amz_tax_id = order.amz_instance_id.amz_tax_id
                taxargs = {'line_tax_amount': shipping_tax,
                           'line_tax_amount_percent': ship_tax_percent,
                           'tax_id': [(6, 0, [amz_tax_id.id])]}
                charges_vals.update(taxargs)
            sale_order_line_obj.create(charges_vals)
        if float(order_detail.get(
                'item-promotion-discount') or 0) > 0 and instance.seller_id.promotion_discount_product_id:
            item_discount = float(
                order_detail.get('item-promotion-discount')) * (-1)

            promotion_discount_product_id = instance.seller_id.promotion_discount_product_id
            item_promotion_vals = self.get_fbm_unshipped_order_line_vals( \
                instance, order, promotion_discount_product_id, item_discount,
                order_detail)
            sale_order_line_obj.create(item_promotion_vals)
        if float(order_detail.get( \
                'ship-promotion-discount') or 0) > 0 and instance.seller_id.ship_discount_product_id:
            ship_discount = float( \
                order_detail.get('ship-promotion-discount')) * (-1)
            ship_discount_product_id = instance.seller_id.ship_discount_product_id
            ship_promotion_vals = self.get_fbm_unshipped_order_line_vals( \
                instance, order, ship_discount_product_id, ship_discount,
                order_detail)
            sale_order_line_obj.create(ship_promotion_vals)

        return True

    def prepare_updated_orderline_vals(self, order_line_vals, order_detail):
        """
        This method prepare updated order line vals.
        :param order_line_vals: old order line vals
        :param order_detail: order line
        :return:order_line_vals
        """
        order_line_vals.update({
            'amazon_order_item_id': order_detail.get('order-item-id')
        })
        return order_line_vals

    def get_item_price(self, order_detail, instance):
        """
        This method addition the price and tax of product item cost.
        :param unit_price: item price
        :param tax: item tax
        :return: sum of price and tax.
        """
        unit_price = float(order_detail.get('item-price'))
        tax = float(order_detail.get('item-tax'))
        if self.seller_id.is_vcs_activated or (instance.amz_tax_id and not instance.amz_tax_id.price_include):
            return unit_price
        return unit_price + tax

    def get_shipping_price(self, order_detail, instance):
        """
        This method addition the price and tax of shipping cost.
        :param shipping_price: shipping price
        :param shipping_tax: shipping tax
        :return: sum of price and tax
        """
        shipping_price = float(order_detail.get('shipping-price', 0.0))
        shipping_tax = float(order_detail.get('shipping-tax', 0.0))
        if self.seller_id.is_vcs_activated or (instance.amz_tax_id and not instance.amz_tax_id.price_include):
            return shipping_price
        return shipping_price + shipping_tax

    def decode_amazon_encrypted_fbm_attachments_data(self, attachment_id, job):
        """
        This method is used to decode the amazon attachments data
        """
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        req = {'dbuuid': dbuuid, 'report_id': self.report_id,
            'datas': attachment_id.datas.decode(), 'amz_report_type': 'fbm_report'}
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/decode_data', params=req, timeout=1000)
        if response.get('result'):
            imp_file = StringIO(base64.b64decode(response.get('result')).decode())
        elif self._context.get('is_auto_process', False):
            job.log_lines.create({'message': 'Error found in Decryption of Data %s' % response.get('error', '')})
            return True
        else:
            raise UserError(response.get('error'))
        return imp_file
