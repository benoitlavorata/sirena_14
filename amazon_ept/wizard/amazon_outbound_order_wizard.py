# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.
"""
Added class and method to process for outbound order operations and added method to
create and update fulfillment.
"""

from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError

from ..endpoint import DEFAULT_ENDPOINT


class AmazonOutboundOrderWizard(models.TransientModel):
    """
    Added class to create outbound orders.
    """
    _name = "amazon.outbound.order.wizard"
    _description = 'Amazon Outbound Order Wizard'

    help_fulfillment_action = """
        Ship - The fulfillment order ships now
        Hold - An order hold is put on the fulfillment order.3
        Default: Ship in Create Fulfillment
        Default: Hold in Update Fulfillment    
    """

    help_fulfillment_policy = """
        FillOrKill - If an item in a fulfillment order is determined to be unfulfillable before any 
                    shipment in the order moves to the Pending status (the process of picking units 
                    from inventory has begun), then the entire order is considered unfulfillable. 
                    However, if an item in a fulfillment order is determined to be unfulfillable 
                    after a shipment in the order moves to the Pending status, Amazon cancels as 
                    much of the fulfillment order as possible
        FillAll - All fulfillable items in the fulfillment order are shipped. 
                The fulfillment order remains in a processing state until all items are either 
                shipped by Amazon or cancelled by the seller
        FillAllAvailable - All fulfillable items in the fulfillment order are shipped. 
            All unfulfillable items in the order are cancelled by Amazon.
        Default: FillOrKill
    """

    instance_id = fields.Many2one("amazon.instance.ept", "Instance", help="Unique Amazon Instance")
    fba_warehouse_id = fields.Many2one("stock.warehouse", "Warehouse", help="Amazon FBA Warehouse")

    sale_order_ids = fields.Many2many("sale.order", "convert_sale_order_bound_rel", "wizard_id",
                                      "sale_id", "Sales Orders",
                                      help="Sale Orders for create outbound shipments")
    fulfillment_action = fields.Selection([('Ship', 'Ship'), ('Hold', 'Hold')],
                                          default="Hold", help=help_fulfillment_action)
    displayable_date_time = fields.Date("Displayable Order Date", required=False,
                                        help="Display Date in package")
    fulfillment_policy = fields.Selection( \
        [('FillOrKill', 'FillOrKill'), ('FillAll', 'FillAll'),
         ('FillAllAvailable', 'FillAllAvailable')],
        default="FillOrKill", required=True,
        help=help_fulfillment_policy)
    shipment_service_level_category = fields.Selection( \
        [('Expedited', 'Expedited'), ('NextDay', 'NextDay'), ('SecondDay', 'SecondDay'),
         ('Standard', 'Standard'),
         ('Priority', 'Priority'), ('ScheduledDelivery', 'ScheduledDelivery')], "Shipment Category",
        default='Standard')
    delivery_start_time = fields.Datetime(help="Delivery Estimated Start Time")
    delivery_end_time = fields.Datetime(help="Delivery Estimated End Time")
    notify_by_email = fields.Boolean(default=False,
                                     help="If true then system will notify by email to followers")
    is_displayable_date_time_required = fields.Boolean("Displayable Date Required ?", default=True)
    note = fields.Text(help="To set note in outbound order")

    def create_outbound_order(self):
        """
        Create Outbound orders for amazon in ERP
        @author: Keyur Kanani
        :return: True
        """
        amazon_sale_order_ids = []
        amazon_product_obj = self.env['amazon.product.ept']
        for amazon_order in self.sale_order_ids:
            if not amazon_order.order_line:
                continue

            if not amazon_order.amz_fulfillment_instance_id:
                amazon_order.write({'amz_instance_id': self.instance_id.id,
                                    "amz_seller_id": self.instance_id.seller_id.id,
                                    'amz_fulfillment_instance_id': self.instance_id.id,
                                    'amz_fulfillment_action': self.fulfillment_action,
                                    'warehouse_id': self.instance_id.fba_warehouse_id.id,
                                    'pricelist_id': self.instance_id.pricelist_id.id,
                                    'amz_displayable_date_time': self.displayable_date_time or
                                                                 amazon_order.date_order or False,
                                    'amz_fulfillment_policy': self.fulfillment_policy,
                                    'amz_shipment_service_level_category': self.shipment_service_level_category,
                                    'amz_is_outbound_order': True,
                                    'notify_by_email': self.notify_by_email,
                                    'amz_order_reference': amazon_order.name,
                                    'note': self.note or amazon_order.name,
                                    })
                for line in amazon_order.order_line:
                    if line.product_id.type == 'service':
                        continue
                    if line.product_id:
                        amz_product = amazon_product_obj.search(
                            [('product_id', '=', line.product_id.id),
                             ('instance_id', '=', self.instance_id.id),
                             ('fulfillment_by', '=', 'FBA')], limit=1)
                        if not amz_product:
                            amz_product = amazon_product_obj.search(
                                [('product_id', '=', line.product_id.id),
                                 ('instance_id', 'in', self.instance_id.seller_id.instance_ids.ids),
                                 ('fulfillment_by', '=', 'FBA')], limit=1)
                        line.write(
                            {'amazon_product_id': amz_product.id})
            amazon_sale_order_ids.append(amazon_order.id)
        return True

    def wizard_view(self, created_id):
        """
        Added method to return the outbound order wizard.
        """
        view = self.env.ref('amazon_ept.amazon_outbound_order_wizard')
        return {
            'name': _('Amazon Outbound Orders'),
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'amazon.outbound.order.wizard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': created_id and created_id.id or False,
            'context': self._context,
        }

    def create_fulfillment(self):
        """
        Create Outbound Shipment in Amazon for selected orders
        @author: Keyur Kanani
        :return: boolean
        """
        iap_account_obj = self.env['iap.account']
        ir_config_obj = self.env['ir.config_parameter']
        amazon_instance_obj = self.env['amazon.instance.ept']
        sale_order_obj = self.env['sale.order']

        active_ids = self._context.get('active_ids')
        draft_orders = sale_order_obj.search( \
            [('id', 'in', active_ids), ('amz_is_outbound_order', '=', True),
             ('state', '=', 'draft'),
             ('exported_in_amazon', '=', False)])
        if not draft_orders:
            return True

        account = iap_account_obj.search([('service_name', '=', 'amazon_ept')])
        dbuuid = ir_config_obj.sudo().get_param('database.uuid')
        for order in draft_orders:
            if not order.amz_shipment_service_level_category:
                raise UserError(_(
                    "Required field Shipment Category is not set for order %s" % (order.name)))
            if not order.note:
                raise UserError(
                    _("Required field Displayable Order Comment is not set for order %s" % (
                        order.name)))
            if not order.amz_fulfillment_action:
                raise UserError(
                    _("Required field Order Fulfillment Action is not set for order %s" % (
                        order.name)))
            if not order.amz_displayable_date_time:
                raise UserError(
                    _("Required field Order Fulfillment Action is not set for order %s" % (
                        order.name)))
            if not order.amz_fulfillment_policy:
                raise UserError(_(
                    "Required field Fulfillment Policy is not set for order %s" % (order.name)))

        instances = amazon_instance_obj.search([('fba_warehouse_id', '!=', False)])
        filtered_orders = draft_orders.filtered(lambda x: x.amz_instance_id in instances)
        for order in filtered_orders:
            data = order.get_data()
            kwargs = {
                'merchant_id': order.amz_instance_id.merchant_id and str(
                    order.amz_instance_id.merchant_id) or False,
                'auth_token': order.amz_instance_id.auth_token and str(
                    order.amz_instance_id.auth_token) or False,
                'app_name': 'amazon_ept',
                'account_token': account.account_token,
                'emipro_api': 'auto_create_outbound_order',
                'dbuuid': dbuuid,
                'amazon_marketplace_code': order.amz_instance_id.country_id.amazon_marketplace_code or
                                           order.amz_instance_id.country_id.code,
                'data': data
            }

            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                raise UserError(_(response.get('reason')))

            order.write({'exported_in_amazon': True})
            self._cr.commit()

        return True

    def update_fulfillment(self):
        """
        Update fulfillment for Outbound Orders
        @author: Keyur Kanani
        :return: boolean
        """
        iap_account_obj = self.env['iap.account']
        ir_config_obj = self.env['ir.config_parameter']
        amazon_instance_obj = self.env['amazon.instance.ept']
        sale_order_obj = self.env['sale.order']

        active_ids = self._context.get('active_ids')
        progress_orders = sale_order_obj.search(
            [('id', 'in', active_ids), ('amz_is_outbound_order', '=', True),
             ('state', '=', 'draft'),
             ('exported_in_amazon', '=', True)])
        if not progress_orders:
            return True

        account = iap_account_obj.search([('service_name', '=', 'amazon_ept')])
        dbuuid = ir_config_obj.sudo().get_param('database.uuid')
        instances = amazon_instance_obj.search([('fba_warehouse_id', '!=', False)])
        filtered_orders = progress_orders.filtered(lambda x: x.amz_instance_id in instances)
        for order in filtered_orders:
            data = order.get_data()
            # update_fulillment_v13 incomplete in v13 MWS.
            kwargs = {
                'merchant_id': order.amz_instance_id.merchant_id and str(
                    order.amz_instance_id.merchant_id) or False,
                'auth_token': order.amz_instance_id.auth_token and str(
                    order.amz_instance_id.auth_token) or False,
                'app_name': 'amazon_ept',
                'account_token': account.account_token,
                'emipro_api': 'update_fulfillment',
                'dbuuid': dbuuid,
                'amazon_marketplace_code': order.amz_instance_id.country_id.amazon_marketplace_code or
                                           order.amz_instance_id.country_id.code,
                'data': data, }

            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                raise UserError(_(response.get('reason')))
            self._cr.commit()
        return True

    def cancel_fulfillment(self):
        """
        Cancel fulfillment for outbound order
        @author: Keyur Kanani
        :return: boolean
        """
        iap_account_obj = self.env['iap.account']
        ir_config_obj = self.env['ir.config_parameter']
        amazon_instance_obj = self.env['amazon.instance.ept']
        sale_order_obj = self.env['sale.order']

        active_ids = self._context.get('active_ids')
        progress_orders = sale_order_obj.search(
            [('id', 'in', active_ids), ('amz_is_outbound_order', '=', True),
             ('state', '=', 'cancel'),
             ('exported_in_amazon', '=', True)])
        if not progress_orders:
            return True

        account = iap_account_obj.search([('service_name', '=', 'amazon_ept')])
        dbuuid = ir_config_obj.sudo().get_param('database.uuid')

        instances = amazon_instance_obj.search([('fba_warehouse_id', '!=', False)])
        filtered_orders = progress_orders.filtered(lambda x: x.amz_instance_id in instances)
        for order in filtered_orders:
            # action_cancel_v13 is incomplete in MWS
            kwargs = {
                'merchant_id': order.amz_instance_id.merchant_id and str(
                    order.amz_instance_id.merchant_id) or False,
                'auth_token': order.amz_instance_id.auth_token and str(
                    order.amz_instance_id.auth_token) or False,
                'app_name': 'amazon_ept',
                'account_token': account.account_token,
                'emipro_api': 'action_cancel',
                'dbuuid': dbuuid,
                'amazon_marketplace_code': order.amz_instance_id.country_id.amazon_marketplace_code or
                                           order.amz_instance_id.country_id.code,
                'order_name': order.name}

            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                raise UserError(_(response.get('reason')))
            self._cr.commit()
        return True

    @api.model
    def auto_create_outbound_orders(self):
        """
        Gets draft orders which has FBA warehouse and creates outbound order object.
        Prepare the sale orders for creating outbound orders in amazon.
        Creates outbound shipment in Amazon for the prepared sale orders.
        @author: Maulik Barad on Date 21-Jan-2019.
        """
        sale_orders = self.env["sale.order"].search([("state", "=", "draft"),
                                                     ("amz_fulfillment_by", "!=", "FBA"),
                                                     ("is_fba_pending_order", "=", False),
                                                     ("exported_in_amazon", "=", False)])
        fba_orders = sale_orders.filtered(lambda x: x.order_has_fba_warehouse)
        sellers = fba_orders.warehouse_id.seller_id
        for seller in sellers:
            if seller.allow_auto_create_outbound_orders:
                instance_id = seller.instance_ids[0].id
                orders = fba_orders.filtered(lambda x: x.warehouse_id.seller_id == seller)
                outbound_order_vals = {"instance_id": instance_id,
                                       "sale_order_ids": [(6, 0, orders[0:30].ids)],
                                       "fulfillment_action": seller.fulfillment_action,
                                       "fulfillment_policy": seller.fulfillment_policy,
                                       "shipment_service_level_category": seller.shipment_category,
                                       "is_displayable_date_time_required": False}
                outbound_order = self.create(outbound_order_vals)
                outbound_order.create_outbound_order()
                outbound_order.with_context(active_ids=orders.ids).create_fulfillment()
        return True
