# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Added class, methods and fields to process to create or update inbound shipment.
"""

import base64
import os
import time
import zipfile
from datetime import datetime

import dateutil.parser
from odoo import models, fields, api, _
from odoo.addons.iap.tools import iap_tools
from odoo.exceptions import UserError

try:
    from _collections import defaultdict
except ImportError:
    pass
from ..endpoint import DEFAULT_ENDPOINT
from .utils import xml2dict

shipment_status_help = """
WORKING - The shipment was created by the seller, but has not yet shipped.
SHIPPED - The shipment was picked up by the carrier.
IN_TRANSIT - The carrier has notified the Amazon fulfillment center that it is aware of the shipment.
DELIVERED - The shipment was delivered by the carrier to the Amazon fulfillment center.
CHECKED_IN - The shipment was checked-in at the receiving dock of the Amazon fulfillment center.
RECEIVING - The shipment has arrived at the Amazon fulfillment center, but not all items have been marked as received.
CLOSED - The shipment has arrived at the Amazon fulfillment center and all items have been marked as received.
CANCELLED - The shipment was cancelled by the seller after the shipment was sent to the Amazon fulfillment center.
DELETED - The shipment was cancelled by the seller before the shipment was sent to the Amazon fulfillment center.
ERROR - There was an error with the shipment and it was not processed by Amazon."""

transport_status = [('draft', 'Draft'), ('WORKING', 'WORKING'),
                    ('ERROR_ON_ESTIMATING', 'ERROR_ON_ESTIMATING'),
                    ('ESTIMATING', 'ESTIMATING'),
                    ('ESTIMATED', 'ESTIMATED'),
                    ('ERROR_ON_CONFIRMING', 'ERROR_ON_CONFIRMING'),
                    ('CONFIRMING', 'CONFIRMING'),
                    ('CONFIRMED', 'CONFIRMED'),
                    ('VOIDING', 'VOIDING'),
                    ('VOIDED', 'VOIDED'),
                    ('ERROR_IN_VOIDING', 'ERROR_IN_VOIDING')]

transport_status_list = ['WORKING', 'ERROR_ON_ESTIMATING', 'ESTIMATING', 'ESTIMATED',
                         'ERROR_ON_CONFIRMING', 'CONFIRMING', 'CONFIRMED', 'VOIDING', 'VOIDED',
                         'ERROR_IN_VOIDING']


class InboundShipmentEpt(models.Model):
    """
    Added class to process to create or update inbound shipment.
    """
    _name = "amazon.inbound.shipment.ept"
    _description = "Inbound Shipment"
    _inherit = ['mail.thread']
    _order = 'id desc'

    @api.depends('partnered_ltl_ids.weight_unit', 'partnered_ltl_ids.weight_value')
    def _compute_shipment_weight(self):
        """
        This method will calculate the amazon shipment weight
        """
        for shipment in self:
            if shipment.is_partnered:
                if shipment.partnered_ltl_ids and shipment.transport_type == 'partnered_ltl_data':
                    weight_unit_kg = weight_unit_pound = 0
                    weight_kg = weight_pound = 0.0
                    for parcel in shipment.partnered_ltl_ids:
                        if parcel.weight_unit == 'kilograms':
                            weight_unit_kg += 1
                            weight_kg += parcel.weight_value
                        elif parcel.weight_unit == 'pounds':
                            weight_unit_pound += 1
                            weight_pound += parcel.weight_value
                    weight_unit = max(weight_unit_kg, weight_unit_pound)
                    if weight_unit == weight_unit_kg:
                        # Convert Weight Pounds to Kilograms
                        weight_kg += (weight_pound * 0.453592)
                        shipment.amazon_shipment_weight = weight_kg
                        shipment.amazon_shipment_weight_unit = 'kilograms'
                    else:
                        # Convert Weight Kilograms to Pounds
                        weight_pound += (weight_kg * 2.20462)
                        shipment.amazon_shipment_weight = weight_pound
                        shipment.amazon_shipment_weight_unit = 'pounds'
            else:
                shipment.amazon_shipment_weight = 0.0
                shipment.amazon_shipment_weight_unit = ''

    @api.depends('picking_ids.state', 'picking_ids.updated_in_amazon')
    def _compute_amazon_status(self):
        """
        This method is used to  set value of updated_in_amazon based on picking.
        """
        self.updated_in_amazon = True if self.picking_ids else False
        for picking in self.picking_ids:
            if picking.state == 'cancel':
                continue
            if picking.picking_type_id.code != 'outgoing':
                continue
            if not picking.updated_in_amazon:
                self.updated_in_amazon = False
                break

    state = fields.Selection([('draft', 'Draft'), ('WORKING', 'WORKING'), ('SHIPPED', 'SHIPPED'),
                              ('IN_TRANSIT', 'IN_TRANSIT'), ('DELIVERED', 'DELIVERED'),
                              ('CHECKED_IN', 'CHECKED_IN'), ('RECEIVING', 'RECEIVING'),
                              ('CLOSED', 'CLOSED'), ('CANCELLED', 'CANCELLED'),
                              ('DELETED', 'DELETED'), ('ERROR', 'ERROR'),
                              ],
                             string='Shipment Status', default='WORKING', help=shipment_status_help)
    name = fields.Char(size=120, readonly=True, required=False, index=True)
    shipment_id = fields.Char(size=120, string='Shipment ID', index=True)
    shipment_plan_id = fields.Many2one('inbound.shipment.plan.ept', string='Shipment Plan')
    amazon_reference_id = fields.Char(size=50, help="A unique identifier created by Amazon that "
                                                    "identifies this Amazon-partnered, Less Than "
                                                    "Truckload/Full Truckload (LTL/FTL) shipment.")
    intended_box_contents_source = fields.Selection(
        [('FEED', 'FEED')], default='FEED', readonly=1,
        help="If your instance is USA then you must set box content, "
             "other wise amazon will collect per piece fee",
        string="Intended BoxContents Source")
    address_id = fields.Many2one('res.partner', string='Ship To Address')
    label_prep_type = fields.Char(size=120, string='LabelPrepType', readonly=True,
                                  help="LabelPrepType provided by Amazon when we send shipment "
                                       "Plan to Amazon")
    odoo_shipment_line_ids = fields.One2many('inbound.shipment.plan.line', 'odoo_shipment_id',
                                             string='Shipment Items')
    picking_ids = fields.One2many('stock.picking', 'odoo_shipment_id', string="Pickings",
                                  readonly=True)
    shipping_type = fields.Selection([('sp', 'SP (Small Parcel)'),
                                      ('ltl', 'LTL (Less Than Truckload/FullTruckload (LTL/FTL))')
                                      ], default="sp")
    transport_type = fields.Selection([('partnered_small_parcel_data', 'PartneredSmallParcelData'),
                                       ('non_partnered_small_parcel_data',
                                        'NonPartneredSmallParcelData'),
                                       ('partnered_ltl_data', 'PartneredLtlData'),
                                       ('non_partnered_ltl_data', 'NonPartneredLtlData')
                                       ], compute="_compute_transport_type", store=True)
    is_partnered = fields.Boolean(default=False, copy=False)
    transport_state = fields.Selection(transport_status, default='draft', copy=False,
                                       string='Transport States')
    log_ids = fields.One2many('common.log.lines.ept', compute="_compute_error_logs")
    transport_content_exported = fields.Boolean('Transport Content Exported?', default=False,
                                                copy=False)
    fulfill_center_id = fields.Char(size=120, string='Fulfillment Center', readonly=True,
                                    help="DestinationFulfillmentCenterId provided by Amazon "
                                         "when we send shipment Plan to Amazon")
    is_manually_created = fields.Boolean(default=False, copy=False)
    is_picking = fields.Boolean(compute="_compute_error_logs")
    partnered_small_parcel_ids = fields.One2many('stock.quant.package',
                                                 'partnered_small_parcel_shipment_id',
                                                 string='Partnered Small Parcel')
    partnered_ltl_ids = fields.One2many('stock.quant.package', 'partnered_ltl_shipment_id',
                                        string='Partnered LTL')
    is_update_inbound_carton_contents = fields.Boolean("Is Update Inbound Carton Contents ?",
                                                       default=False, copy=False)

    is_carton_content_updated = fields.Boolean("Carton Content Updated ?", default=False,
                                               copy=False)
    void_deadline_date = fields.Datetime(help="The date after which a confirmed transportation "
                                              "request can no longer be voided. This date is 24 "
                                              "hours after you confirm a Small Parcel shipment "
                                              "transportation request or one hour after you confirm"
                                              "a Less Than Truckload/Full Truckload (LTL/FTL) "
                                              "shipment transportation request. After the void "
                                              "deadline passes your account will be charged for "
                                              "the shipping cost. In ISO 8601 format.")
    pro_number = fields.Char(size=10,
                             help="The PRO number assigned to your shipment by the carrier. "
                                  "A string of numbers, seven to 10 characters in length.")
    updated_in_amazon = fields.Boolean(compute="_compute_amazon_status", store=True)
    instance_id_ept = fields.Many2one("amazon.instance.ept", string="Instance")
    feed_id = fields.Many2one("feed.submission.history", string="Submit Feed Id")
    are_cases_required = fields.Boolean("AreCasesRequired", default=False,
                                        help="Indicates whether or not an Inbound shipment "
                                             "contains case-packed boxes. A shipment must either "
                                             "contain all case-packed boxes or all individually "
                                             "packed boxes")
    created_date = fields.Date('Create on', default=time.strftime('%Y-%m-%d'))
    carrier_id = fields.Many2one('delivery.carrier', string='Carrier')
    is_billof_lading_available = fields.Boolean(string='IsBillOfLadingAvailable', default=False,
                                                help="Indicates whether the bill of lading for the "
                                                     "shipment is available.")
    currency_id = fields.Many2one('res.currency', string='Currency')
    estimate_amount = fields.Float(help='The amount that the Amazon-partnered carrier will charge '
                                        'to ship the inbound shipment.')
    confirm_deadline_date = fields.Datetime(help="The date by which this estimate must be "
                                                 "confirmed. After this date the estimate is no "
                                                 "longer valid and cannot be confirmed. "
                                                 "In ISO 8601 format.")

    partnered_ltl_id = fields.Many2one('res.partner', string='Contact',
                                       help="Contact information for the person in your "
                                            "organization who is responsible for the shipment. "
                                            "Used by the carrier if they have questions "
                                            "about the shipment.")
    from_warehouse_id = fields.Many2one("stock.warehouse", string="Warehouse")
    preview_freight_class = fields.Selection(
        [('50', '50'), ('55', '55'), ('60', '60'), ('65', '65'), ('70', '70'), ('77.5', '77.5'),
         ('85', '85'), ('92.5', '92.5'), ('100', '100'), ('110', '110'), ('125', '125'),
         ('150', '150'), ('175', '175'), ('200', '200'), ('250', '250'), ('300', '300'),
         ('400', '400'), ('500', '500')],
        string='PreviewFreightClass',
        help="The freight class of the shipment as estimated by Amazon if you did not include a "
             "freight class when you called the PutTransportContent operation.")

    seller_declared_value = fields.Float(digits=(16, 2))
    seller_freight_class = fields.Selection(
        [('50', '50'), ('55', '55'), ('60', '60'), ('65', '65'), ('70', '70'), ('77.5', '77.5'),
         ('85', '85'), ('92.5', '92.5'), ('100', '100'), ('110', '110'), ('125', '125'),
         ('150', '150'), ('175', '175'), ('200', '200'), ('250', '250'), ('300', '300'),
         ('400', '400'), ('500', '500')])
    freight_ready_date = fields.Date()
    box_count = fields.Integer('Number of box')
    preview_pickup_date = fields.Datetime(string='PreviewPickupDate',
                                          help="The estimated date that the shipment will be "
                                               "picked up by the carrier. In ISO 8601 format.")
    preview_delivery_date = fields.Datetime(string='PreviewDeliveryDate',
                                            help="The estimated date that the shipment will be "
                                                 "delivered to an Amazon fulfillment center.")
    declared_value_currency_id = fields.Many2one('res.currency', string="Declare Value Currency")
    amazon_shipment_weight = fields.Float(compute='_compute_shipment_weight',
                                          string="Shipment Weight", store=True, readonly=True)
    amazon_shipment_weight_unit = fields.Selection(
        [('pounds', 'Pounds'), ('kilograms', 'Kilograms'), ],
        string='Weight Unit',
        compute="_compute_shipment_weight",
        store=True, readonly=True)
    suggest_seller_declared_value = fields.Float(digits=(16, 2))
    closed_date = fields.Date(readonly=True, copy=False)

    @api.depends('is_partnered', 'shipping_type')
    def _compute_transport_type(self):
        for shipment in self:
            if shipment.shipping_type == 'sp' and shipment.is_partnered:
                shipment.transport_type = 'partnered_small_parcel_data'
            elif shipment.shipping_type == 'ltl' and shipment.is_partnered:
                shipment.transport_type = 'partnered_ltl_data'
            elif shipment.shipping_type == 'sp':
                shipment.transport_type = 'non_partnered_small_parcel_data'
            elif shipment.shipping_type == 'ltl':
                shipment.transport_type = 'non_partnered_ltl_data'

    def unlink(self):
        """
        Inherited unlink method to do not allow to delete shipment of which shipment plan is
        approved and which shipment is not in cancelled and deleted.
        """
        for shipment in self:
            if shipment.shipment_plan_id and shipment.shipment_plan_id.state == 'plan_approved':
                raise UserError(_('You cannot delete Inbound Shipment.'))

            if shipment.instance_id_ept and shipment.state not in ['CANCELLED', 'DELETED']:
                raise UserError(_('You cannot delete Inbound Shipment.'))

        return super(InboundShipmentEpt, self).unlink()

    def _compute_error_logs(self):
        """
        Define method to get shipment error logs.
        """
        common_log_line_obj = self.env['common.log.lines.ept']
        model_id = common_log_line_obj.get_model_id('amazon.inbound.shipment.ept')
        logs = common_log_line_obj.search( \
            [('model_id', '=', model_id), ('res_id', '=', self.id)])
        self.log_ids = logs and logs.ids
        self.is_picking = True if self.picking_ids else False

    def create_or_update_address(self, address):
        """
        This method will prepare partner values based on the address details and
        return the created partner.
        """
        domain = []
        partner_obj = self.env['res.partner']
        country_obj = self.env['res.country']
        state_obj = self.env['res.country.state']
        state_id = False

        country = country_obj.search(
            [('code', '=', address.get('CountryCode', {}).get('value', ''))])
        state = address.get('StateOrProvinceCode', {}).get('value', '')
        name = address.get('Name', {}).get('value', '')
        street = address.get('AddressLine1', {}).get('value', '')
        street2 = address.get('AddressLine2', {}).get('value', '')
        postal_code = address.get('PostalCode', {}).get('value', '')
        city = address.get('City', {}).get('value', '')

        if state:
            result_state = state_obj.search( \
                [('code', '=ilike', state), ('country_id', '=', country.id)])
            if not result_state:
                state = partner_obj.create_or_update_state_ept( \
                    country.code, state, postal_code, country)
                state_id = state.id
            else:
                state_id = result_state[0].id
        name and domain.append(('name', '=', name))
        street and domain.append(('street', '=', street))
        street2 and domain.append(('street2', '=', street2))
        city and domain.append(('city', '=', city))
        postal_code and domain.append(('zip', '=', postal_code))
        state_id and domain.append(('state_id', '=', state_id))
        country and domain.append(('country_id', '=', country.id))

        partner = partner_obj.with_context(is_amazon_partner=True).search(domain)
        if not partner:
            partner_vals = {
                'name': name, 'is_company': False,
                'street': street, 'street2': street2,
                'city': city, 'country_id': country.id, 'zip': postal_code, 'state_id': state_id,
                'is_amz_customer': True
            }
            partner = partner_obj.create(partner_vals)
        return partner.id

    @api.model
    def create_or_update_inbound_shipment(self, ship_plan, shipment, job=False):
        """ Here We are not taking shipment id as domain because amazon create each time
         new shipment id & we merge with existing shipment_id in same plan """

        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']

        add_id = self.create_or_update_address(shipment.get('ShipToAddress', {}))
        fulfill_center_id = shipment.get('DestinationFulfillmentCenterId', {}).get('value', '')
        label_prep_type = shipment.get('LabelPrepType', {}).get('value', '')
        shipment_id = shipment.get('ShipmentId', {}).get('value', False)
        is_are_cases_required = ship_plan.is_are_cases_required if ship_plan else False
        instance = ship_plan.instance_id
        create_or_update = 'create'

        domain = [('shipment_id', '=', shipment_id), ('shipment_plan_id', '=', ship_plan.id)]
        odoo_shipment = self.search(domain)
        if odoo_shipment:
            create_or_update = 'update'
        else:
            try:
                sequence = self.env.ref('amazon_ept.seq_inbound_shipments')
                if sequence:
                    name = sequence.next_by_id()
                else:
                    name = '/'
            except:
                name = '/'

            shipment_vals = {
                'name': name,
                'shipment_plan_id': ship_plan.id,
                'fulfill_center_id': fulfill_center_id,
                'label_prep_type': label_prep_type,
                'address_id': add_id,
                'shipment_id': shipment_id,
                'state': 'WORKING',
                'intended_box_contents_source': ship_plan.intended_box_contents_source,
                'are_cases_required': is_are_cases_required,
                'instance_id_ept': instance.id
            }
            if ship_plan.shipping_type:
                shipment_vals.update({'is_partnered': ship_plan.is_partnered,
                                      'shipping_type': ship_plan.shipping_type})
            odoo_shipment = self.create(shipment_vals)

        items = []
        if not isinstance(shipment.get('Items', {}).get('member', []), list):
            items.append(shipment.get('Items', {}).get('member', []))
        else:
            items = shipment.get('Items', {}).get('member', [])

        sku_qty_dict = self.env['inbound.shipment.plan.line'].prepare_shipment_plan_line_dict( \
            odoo_shipment, items)

        address = ship_plan.ship_from_address_id
        address_dict = {'name': address.name, 'address_1': address.street or '',
                        'address_2': address.street2 or '', 'city': address.city or '',
                        'country': address.country_id and address.country_id.code or '',
                        'state_or_province': address.state_id and address.state_id.code or '',
                        'postal_code': address.zip or ''}
        result = {}
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo( \
            ).get_param('database.uuid')

        label_prep_type = odoo_shipment.label_prep_type
        if label_prep_type == 'NO_LABEL':
            label_prep_type = 'SELLER_LABEL'
        elif label_prep_type == 'AMAZON_LABEL':
            label_prep_type = ship_plan.label_preference

        if create_or_update == 'update':
            kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                      'auth_token': instance.auth_token and str(instance.auth_token) or False,
                      'app_name': 'amazon_ept',
                      'account_token': account.account_token,
                      'emipro_api': 'update_shipment_in_amazon_v13',
                      'dbuuid': dbuuid,
                      'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                                 instance.country_id.code,
                      'shipment_name': odoo_shipment.name,
                      'shipment_id': odoo_shipment.shipment_id,
                      'destination': fulfill_center_id,
                      'labelpreppreference': label_prep_type,
                      'inbound_box_content_status': odoo_shipment.intended_box_contents_source,
                      'cases_required': is_are_cases_required,
                      'shipment_status': 'WORKING',
                      'sku_qty_dict': sku_qty_dict,
                      'address_dict': address_dict
                      }
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                error_value = response.get('reason')
                if not job:
                    job = log_obj.create({'module': 'amazon_ept',
                                          'type': 'export',
                                          })
                log_line_obj.create({'message': error_value,
                                     'model_id': log_line_obj.get_model_id(
                                         'inbound.shipment.plan.ept'),
                                     'res_id': ship_plan.id,
                                     'log_book_id': job.id
                                     })

                return False, job
        elif create_or_update == 'create':
            kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                      'auth_token': instance.auth_token and str(instance.auth_token) or False,
                      'app_name': 'amazon_ept',
                      'account_token': account.account_token,
                      'emipro_api': 'create_shipment_in_amazon_v13',
                      'dbuuid': dbuuid,
                      'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                                 instance.country_id.code,
                      'shipment_name': odoo_shipment.name,
                      'shipment_id': odoo_shipment.shipment_id,
                      'destination': fulfill_center_id,
                      'sku_qty_dict': sku_qty_dict,
                      'address_dict': address_dict,
                      'labelpreppreference': label_prep_type,
                      'inbound_box_content_status': odoo_shipment.intended_box_contents_source,
                      'is_are_cases_required': is_are_cases_required,
                      'shipment_status': 'WORKING'
                      }
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                error_value = response.get('reason')
                if not job:
                    job = log_obj.create({'module': 'amazon_ept',
                                          'type': 'export',
                                          })
                log_line_obj.create({'message': error_value,
                                     'model_id': log_line_obj.get_model_id(
                                         'inbound.shipment.plan.ept'),
                                     'res_id': ship_plan.id,
                                     'log_book_id': job.id
                                     })

                return False, job

        shipment_id = result.get('ShipmentId', {}).get('value', '') if result else False
        if shipment_id:
            odoo_shipment.write({'shipment_id': shipment_id})
        return odoo_shipment, job

    def create_shipment_picking(self):
        """
        When Import Shipment from amazon to odoo with shipping ids this method will be used.
        :return: boolean
        @author: Keyur Kanani
        """
        self.ensure_one()
        if self.is_manually_created:
            self.create_procurements()
        else:
            inbound_shipment_plan_obj = self.env['inbound.shipment.plan.ept']
            inbound_shipment_plan_obj.create_procurements()
        return True

    @api.model
    def create_procurements(self):
        """
        This method will find warehouse and location according to routes,
        if found then Create and run Procurement, also it will assign pickings if found.
        :return: boolean
        @author: Keyur Kanani
        """
        proc_group_obj = self.env['procurement.group']
        picking_obj = self.env['stock.picking']
        group_wh_dict = {}
        proc_group = proc_group_obj.create({'odoo_shipment_id': self.id, 'name': self.name})
        instance = self.instance_id_ept
        warehouse = self.amz_inbound_get_warehouse_ept(instance, self.fulfill_center_id)
        if warehouse:
            location_routes = self.amz_find_location_routes_ept(warehouse)
            group_wh_dict.update({proc_group: warehouse})
            for line in self.odoo_shipment_line_ids:
                qty = line.quantity
                product_id = line.amazon_product_id.product_id
                datas = self.amz_inbound_prepare_procure_datas(location_routes, proc_group,
                                                               instance, warehouse)
                proc_group_obj.run([proc_group_obj.Procurement(product_id, qty, product_id.uom_id,
                                                               warehouse.lot_stock_id,
                                                               product_id.name, self.name,
                                                               instance.company_id, datas)])
        if group_wh_dict:
            for group, warehouse in group_wh_dict.items():
                picking = picking_obj.search([('group_id', '=', group.id),
                                              ('picking_type_id.warehouse_id', '=', warehouse.id)])
                if picking:
                    picking.write({'is_fba_wh_picking': True})

        pickings = self.mapped('picking_ids').filtered( \
            lambda pick: not pick.is_fba_wh_picking and pick.state not in ['done', 'cancel'])
        for picking in pickings:
            picking.action_assign()
        return True

    def amz_find_location_routes_ept(self, warehouse):
        """
        Find Location routes from warehouse.
        :param warehouse: stock.warehouse()
        :return: stock.location.route()
        @author: Keyur Kanani
        """
        location_route_obj = self.env['stock.location.route']
        location_routes = location_route_obj.search([('supplied_wh_id', '=', warehouse.id),
                                                     ('supplier_wh_id', '=',
                                                      self.from_warehouse_id.id)], limit=1)
        if not location_routes:
            error_value = 'Location routes are not found. Please configure routes in warehouse ' \
                          'properly || warehouse %s & shipment %s.' % (warehouse.name, self.name)
            self.search_or_create_inbound_common_log_ept('export', 'amazon.inbound.shipment.ept',
                                                         error_value)
        return location_routes

    @staticmethod
    def amz_inbound_prepare_procure_datas(location_routes, proc_group, instance, warehouse):
        """
        Prepare Procurement values dictionary.
        :param location_routes: stock.location.route()
        :param proc_group: procurement.group()
        :param instance: amazon.instance.ept()
        :param warehouse: stock.warehouse()
        :return: dict{}
        @author: Keyur Kanani
        """
        return {
            'route_ids': location_routes,
            'group_id': proc_group,
            'company_id': instance.company_id.id,
            'warehouse_id': warehouse,
            'priority': '1'
        }

    def amz_inbound_get_warehouse_ept(self, instance, fulfill_center):
        """
        Get warehouse from fulfillment center, if not found then from instance.
        :param instance: amazon.instance.ept()
        :param fulfill_center: Character
        :return: stock.warehouse()
        @author: Keyur Kanani
        """

        fulfillment_center_obj = self.env['amazon.fulfillment.center']
        fulfillment_center = fulfillment_center_obj.search(
            [('center_code', '=', fulfill_center), ('seller_id', '=', instance.seller_id.id)],
            limit=1)
        warehouse = fulfillment_center and fulfillment_center.warehouse_id or instance.fba_warehouse_id and instance.fba_warehouse_id or instance.warehouse_id or False
        if not warehouse:
            error_value = 'No any warehouse found related to fulfillment center {fulfill_center}.' \
                          'Please set fulfillment center {fulfill_center} in warehouse || ' \
                          'shipment {name}.'.format( \
                fulfill_center=fulfill_center, name=self.name)
            self.search_or_create_inbound_common_log_ept('export', 'amazon.inbound.shipment.ept',
                                                         error_value)
        return warehouse

    def search_or_create_inbound_common_log_ept(self, log_type, model_name, message):
        """
        Common log book creator, If log found then it will add log line only else create new log
        :param log_type: Char(import/export)
        :param model_name: table name
        :param message: string
        :return: common.log.book.ept()
        """
        log_book_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']
        job = log_book_obj.search([('module', '=', 'amazon_ept'),
                                   ('message', '=', 'Amazon Inbound Shipment Process'),
                                   ('model_id', '=', log_line_obj.get_model_id(model_name)),
                                   ('res_id', '=', self.id)])
        if not job:
            job = log_book_obj.create({'module': 'amazon_ept', 'type': log_type,
                                       'model_id': log_line_obj.get_model_id(model_name),
                                       'res_id': self.id})
        log_line_obj.create({'message': message,
                             'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                             'res_id': self.id,
                             'log_book_id': job.id})
        return job

    def create_pickings_ept(self):
        """
        Use: Create New Picking for Shipment
        """
        self.ensure_one()
        inbound_shipment_plan_obj = self.env['inbound.shipment.plan.ept']
        inbound_shipment_plan_obj.create_procurements(self)

    def update_inbound_shipment_qty(self):
        """Use: Update Shipment Qty in Amazon"""

        pickings = self.mapped('picking_ids'). \
            filtered(lambda picking: picking.state in ['done'])
        if pickings:
            raise UserError(_("You can not Update Shipment QTY whose Pickings are in Done State"))

        for shipment in self:
            ship_plan = shipment.shipment_plan_id
            if not ship_plan or not shipment.fulfill_center_id:
                raise UserError(_('You must have to first create Inbound Shipment Plan.'))

            instance = ship_plan.instance_id
            shipment_status = shipment.state
            destination = shipment.fulfill_center_id
            cases_required = ship_plan.is_are_cases_required

            label_prep_type = shipment.label_prep_type
            if label_prep_type == 'NO_LABEL':
                label_prep_type = 'SELLER_LABEL'
            elif label_prep_type == 'AMAZON_LABEL':
                label_prep_type = ship_plan.label_preference

            account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
            dbuuid = self.env['ir.config_parameter'].sudo( \
                ).get_param('database.uuid')
            address = ship_plan.ship_from_address_id
            address_dict = {'name': address.name, 'address_1': address.street or '',
                            'address_2': address.street2 or '', 'city': address.city or '',
                            'country': address.country_id and address.country_id.code or '',
                            'state_or_province': address.state_id and address.state_id.code or '',
                            'postal_code': address.zip or ''}
            for x in range(0, len(shipment.odoo_shipment_line_ids), 20):
                shipment_lines = shipment.odoo_shipment_line_ids[x:x + 20]
                sku_qty_dict = []

                for line in shipment_lines:
                    amazon_product = line.amazon_product_id
                    if not amazon_product:
                        raise UserError(_("Amazon Product is not available"))

                    sku_qty_dict.append({'sku':line.seller_sku,'quantity':int(line.quantity),
                                         'quantity_in_case':int(line.quantity_in_case) if
                                         cases_required else 0})

                kwargs = {
                    'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                    'auth_token': instance.auth_token and str(instance.auth_token) or False,
                    'app_name': 'amazon_ept',
                    'account_token': account.account_token,
                    'emipro_api': 'update_shipment_in_amazon_v13',
                    'dbuuid': dbuuid,
                    'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                               instance.country_id.code,

                    'shipment_name': shipment.name,
                    'shipment_id': shipment.shipment_id,
                    'labelpreppreference': label_prep_type,
                    'shipment_status': shipment_status,
                    'inbound_box_content_status': shipment.intended_box_contents_source,
                    'sku_qty_dict': sku_qty_dict,
                    'cases_required': cases_required,
                    'destination': destination,
                    'address_dict': address_dict
                }
                response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
                if response.get('reason'):
                    raise UserError(_(response.get('reason')))
            shipment.picking_ids.action_cancel()
            shipment.create_pickings_ept()
        return True

    def cancel_shipment_in_amazon_via_shipment_lines(self):
        """
        Added methods to prepare dict of sku, quantity and request to cancel shipment.
        """
        shipment = self
        instance = self.get_instance(shipment)
        destination = shipment.fulfill_center_id

        shipment_status = 'CANCELLED'
        if not shipment.shipment_id or not shipment.fulfill_center_id:
            raise UserError(_('You must have to first create Inbound Shipment Plan.'))

        address = shipment.shipment_plan_id.ship_from_address_id
        address_dict = {'name': address.name, 'address_1': address.street or '',
                        'address_2': address.street2 or '', 'city': address.city or '',
                        'country': address.country_id and address.country_id.code or '',
                        'state_or_province': address.state_id and address.state_id.code or '',
                        'postal_code': address.zip or ''}

        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        label_prep_type = shipment.label_prep_type
        if label_prep_type == 'NO_LABEL':
            label_prep_type = 'SELLER_LABEL'
        elif label_prep_type == 'AMAZON_LABEL':
            label_prep_type = shipment.shipment_plan_id.label_preference

        cases_required = shipment.shipment_plan_id.is_are_cases_required
        for x in range(0, len(shipment.odoo_shipment_line_ids), 20):
            ship_lines = shipment.odoo_shipment_line_ids[x:x + 20]
            sku_qty_dict = []
            for line in ship_lines:
                sku_qty_dict.append({'sku': line.seller_sku, 'quantity': int(line.quantity),
                                     'quantity_in_case': int(line.quantity_in_case) if
                                     cases_required else 0})
            kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                      'auth_token': instance.auth_token and str(instance.auth_token) or False,
                      'app_name': 'amazon_ept',
                      'account_token': account.account_token,
                      'emipro_api': 'update_shipment_in_amazon_v13',
                      'dbuuid': dbuuid,
                      'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                                 instance.country_id.code,

                      'shipment_name': shipment.name,
                      'shipment_id': shipment.shipment_id,
                      'destination': destination,
                      'labelpreppreference': label_prep_type,
                      'shipment_status': shipment_status,
                      'inbound_box_content_status': shipment.intended_box_contents_source,
                      'cases_required': shipment.shipment_plan_id.is_are_cases_required,
                      'sku_qty_dict': sku_qty_dict,
                      'address_dict': address_dict
                      }

            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                raise UserError(_(response.get('reason')))
            break
        shipment.write({'state': 'CANCELLED'})
        shipments = shipment.shipment_plan_id.odoo_shipment_ids.filtered( \
            lambda r: r.state != 'CANCELLED')
        not shipments and shipment.shipment_plan_id.write({'state': 'cancel'})
        return True

    def open_import_inbound_shipment_report_wizard(self):
        import_inbound_shipment_view = self.env.ref( \
            'amazon_ept.import_amazon_inbound_shipment_report_form_view')
        return {
            'name': 'Import Amazon Inbound Shipment Report',
            'view_type': 'form',
            "view_mode": 'form',
            'res_model': 'amazon.inbound.shipment.report.wizard',
            'type': 'ir.actions.act_window',
            'view_id': import_inbound_shipment_view.id,
            'target': 'new'
        }

    def get_instance(self, shipment):
        """
        will return the shipment instance.
        """
        if shipment.instance_id_ept:
            return shipment.instance_id_ept
        return shipment.shipment_plan_id.instance_id

    def get_header(self, instance):
        """
        will return the request header.
        """
        return """<?xml version="1.0"?>
            <AmazonEnvelope xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" 
            xsi:noNamespaceSchemaLocation="amzn-envelope.xsd">
            <Header>
                <DocumentVersion>1.01</DocumentVersion>
                <MerchantIdentifier>%s</MerchantIdentifier>
            </Header>
            <MessageType>CartonContentsRequest</MessageType>
            <Message>
         """ % instance.merchant_id

    def create_carton_contents_requests(self):
        """
        This method will prepare the data to create carton contents request and process response
        to create feed submission record.
        """
        amazon_product_obj = self.env['amazon.product.ept']
        feed_submit_obj = self.env['feed.submission.history']
        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']

        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        message = 1

        for shipment in self:
            instance = self.get_instance(shipment)
            job_log_vals = {
                'type': 'export',
                'module': 'amazon_ept'
            }
            job = log_obj.create(job_log_vals)

            box_no_product_dict = {}
            if shipment.partnered_small_parcel_ids:
                parcels = shipment.partnered_small_parcel_ids
            else:
                parcels = shipment.partnered_ltl_ids
            for content in parcels:
                box_no = content.box_no
                if box_no not in box_no_product_dict:
                    box_no_product_dict.update({box_no: {}})
                for carton_line in content.carton_info_ids:
                    line = shipment.odoo_shipment_line_ids. \
                        filtered( \
                        lambda
                            shipment_line: shipment_line.amazon_product_id.id == carton_line.amazon_product_id.id)

                    line = line and line[0]
                    seller_sku = line and line.seller_sku
                    quantity_in_case = line.quantity_in_case if line.quantity_in_case > 0.0 else 1
                    if not line:
                        amazon_product = amazon_product_obj.search(
                            [('id', '=', carton_line.amazon_product_id.id),
                             ('instance_id', '=', instance.id)], limit=1)
                        seller_sku = amazon_product.seller_sku if amazon_product else False
                    if not seller_sku:
                        continue

                    qty = box_no_product_dict.get(box_no, {}).get(seller_sku, 0.0) and \
                          int(box_no_product_dict.get(box_no, {}).get(seller_sku, 0.0)[0])
                    qty += carton_line.quantity

                    # Convert Expiration Date to ISO Format
                    expiry_date = content.box_expiration_date
                    expiry_date = expiry_date.isoformat() if expiry_date else ''
                    box_no_product_dict.get(box_no, {}).update(
                        {seller_sku: [str(int(qty)), str(int(quantity_in_case)), str(expiry_date)]})

            total_box_list = set(box_no_product_dict.keys())
            flag = False

            for box, qty_dict in box_no_product_dict.items():
                if len(qty_dict.keys()) > 200:
                    message = 'System did not update carton in amazon because amazon not allow to' \
                              'update more then 200 item in one box || Box no %s || Inbound' \
                              'shipment ref %s' % (box, shipment.name)

                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                        'res_id': shipment.id or 0,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    flag = True
                    break
            if flag:
                continue

            data = '<MessageID>%s</MessageID><CartonContentsRequest>' % message
            message = message + 1
            data = "%s<ShipmentId>%s</ShipmentId><NumCartons>%s</NumCartons>" % (
                data, shipment.shipment_id, len(total_box_list))
            for box, qty_dict in box_no_product_dict.items():
                box_info = '<Carton><CartonId>%s</CartonId>' % box
                item_dict = ''
                for sku, qty, in qty_dict.items():
                    if qty[2]:
                        item_dict = "%s<Item><SKU>%s</SKU><QuantityShipped>%s</QuantityShipped>" \
                                    "<QuantityInCase>%s</QuantityInCase>" \
                                    "<ExpirationDate>%s</ExpirationDate></Item>" % ( \
                                        item_dict, sku, int(qty[0]), int(qty[1]), qty[2])
                    else:
                        item_dict = "%s<Item><SKU>%s</SKU><QuantityShipped>%s</QuantityShipped>" \
                                    "<QuantityInCase>%s</QuantityInCase></Item>" % ( \
                                        item_dict, sku, int(qty[0]), int(qty[1]))
                box_info = "%s %s</Carton>" % (box_info, item_dict)
                data = "%s %s" % (data, box_info)
            data = "%s</CartonContentsRequest>" % data

            header = self.get_header(
                shipment.shipment_plan_id.instance_id or shipment.instance_id_ept)
            if data:
                data = "%s %s</Message></AmazonEnvelope>" % (header, data)

                marketplaceids = [instance.market_place_id]

                kwargs = {
                    'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                    'auth_token': instance.auth_token and str(instance.auth_token) or False,
                    'app_name': 'amazon_ept',
                    'account_token': account.account_token,
                    'emipro_api': 'create_carton_contents_requests_v13',
                    'dbuuid': dbuuid,
                    'marketplaceids': marketplaceids,
                    'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                               instance.country_id.code,
                    'data': data,
                }

                response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
                if response.get('reason'):
                    raise UserError(_(response.get('reason')))
                results = response.get('result')
                if results.get('FeedSubmissionInfo', {}).get('FeedSubmissionId', {}).get('value',
                                                                                         False):
                    last_feed_submission_id = results.get('FeedSubmissionInfo', {}).get(
                        'FeedSubmissionId', {}).get('value', False)

                    feed_vals = {'message': data, 'feed_result_id': last_feed_submission_id,
                                 'feed_submit_date': time.strftime("%Y-%m-%d %H:%M:%S"),
                                 'instance_id': instance.id, 'user_id': self._uid,
                                 'feed_type': 'update_carton_content',
                                 'seller_id': instance.seller_id.id}
                    feed = feed_submit_obj.create(feed_vals)

                    shipment.write({'is_update_inbound_carton_contents': True, 'feed_id': feed.id})
        return True

    def setup_partnered_ltl_data(self, parcel_data):
        """
        This method will get the parcel information and update the inbound shipment values.
        """
        self.ensure_one()
        box_count = parcel_data.get('BoxCount', {}).get('value')
        freight_class = parcel_data.get('SellerFreightClass', {}).get('value', False)
        freight_ready_date = parcel_data.get('FreightReadyDate', {}).get('value', False)
        prev_pickup_date = parcel_data.get('PreviewPickupDate', {}).get('value', False)
        prev_delivery_date = parcel_data.get('PreviewDeliveryDate', {}).get('value', False)
        prev_freight_class = parcel_data.get('PreviewFreightClass', {}).get('value', False)
        amazon_ref_id = parcel_data.get('AmazonReferenceId', {}).get('value', False)
        is_bol_available = True if parcel_data.get( \
            'IsBillOfLadingAvailable', {}).get('value', '') == 'true' else False
        currency_code = parcel_data.get('AmazonCalculatedValue', {}).get('CurrencyCode', {}).get( \
            'value')
        vals = {}
        if currency_code:
            currency = self.env['res.currency'].search([('name', '=', currency_code)], limit=1)
            currency and vals.update({'declared_value_currency_id': currency.id})
        currency_value = parcel_data.get('AmazonCalculatedValue', {}).get('Value', {}).get('value')
        if currency_value > 0.0:
            vals.update({'seller_declared_value': currency_value})
        if freight_class:
            vals.update({'seller_freight_class': freight_class})
        if freight_ready_date:
            vals.update({'freight_ready_date': freight_ready_date})
        if box_count:
            vals.update({'box_count': box_count})
        if prev_pickup_date:
            vals.update({'preview_pickup_date': prev_pickup_date})
        if prev_delivery_date:
            vals.update({'preview_delivery_date': prev_delivery_date})
        if prev_freight_class:
            vals.update({'preview_freight_class': prev_freight_class})
        if amazon_ref_id:
            vals.update({'amazon_reference_id': amazon_ref_id})
        if is_bol_available:
            vals.update({'is_billof_lading_available': is_bol_available})
        self.write(vals)
        return True

    def setup_partnered_small_parcel_data(self, parcel_data):
        """
        This method will prepare package information from the parcel data and
        create or update package.
        """
        package_obj = self.env['stock.quant.package']
        package_list = []
        packages = parcel_data.get('PackageList', {}).get('member', [])
        if not isinstance(packages, list):
            package_list.append(packages)
        else:
            package_list = packages
        for package in package_list:
            tracking_number = package.get('TrackingId', {}).get('value', '')
            if not tracking_number:
                continue

            package_status = package.get('PackageStatus', {}).get('value', '')
            weight_unit = package.get('Weight', {}).get('Unit', {}).get('value', '')

            weight_value = package.get('Weight', {}).get('Value', {}).get('value', 0.0) and \
                           float(package.get('Weight', {}).get('Value', {}).get('value', 0.0)) \
                           or 0.0

            package_vals = {'package_status': package_status, 'tracking_no': tracking_number}
            domain = [('partnered_small_parcel_shipment_id', '=', self.ids and self.ids[0])]

            if weight_unit:
                package_vals.update({'weight_unit': weight_unit}), domain.append( \
                    ('weight_unit', '=', weight_unit))

            if weight_value:
                package_vals.update({'weight_value': weight_value}), domain.append( \
                    ('weight_value', '=', weight_value))

            package_exist = package_obj.search( \
                [('partnered_small_parcel_shipment_id', '=', self.ids and self.ids[0]),
                 ('tracking_no', '=', tracking_number)])
            if not package_exist:
                domain.append(('tracking_no', '=', False))
                package_exist = package_obj.search(domain, order='id')
            if package_exist:
                package_exist = package_exist[0]
                package_exist.write(package_vals)
            else:
                package_vals.update( \
                    {'partnered_small_parcel_shipment_id': self.ids and self.ids[0]})
                package_obj.create(package_vals)

        return True

    def set_estimate_amount(self, parcel_data):
        """
        This method will set the currency, estimate amount, void deadline date and confirm
        deadline date.
        """
        amount = parcel_data.get('PartneredEstimate', {}).get('Amount', {})
        currency = amount.get('CurrencyCode', {}).get('value', '')
        amount_value = amount.get('Value', {}).get('value', 0.0)
        deadline_date = parcel_data.get('PartneredEstimate', {}).get('VoidDeadline', {}).get( \
            'value')
        confirm_deadline_date = parcel_data.get('PartneredEstimate', {}).get('ConfirmDeadline',
                                                                             {}).get('value')
        currency_id = self.env['res.currency'].search([('name', '=', currency)])
        deadline_date = deadline_date and dateutil.parser.parse(deadline_date)
        deadline_date = deadline_date and datetime.strftime(deadline_date, '%Y-%m-%d %H:%M:%S')
        vals = {'currency_id': currency_id and currency_id[0].id or False,
                'estimate_amount': amount_value, 'void_deadline_date': deadline_date}
        if confirm_deadline_date:
            confirm_deadline_date = dateutil.parser.parse(confirm_deadline_date)
            confirm_deadline_date = confirm_deadline_date and datetime.strftime( \
                confirm_deadline_date, '%Y-%m-%d %H:%M:%S')
            vals.update({'confirm_deadline_date': confirm_deadline_date})
        self.write(vals)
        return True

    def get_transport_content(self):
        """
        This method will request for transport content based on shipment id and process response.
        """
        instance = self.get_instance(self)
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'get_transport_content_v13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,
                  'shipment_id': self.shipment_id, }

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            raise UserError(_(response.get('reason')))

        result = response.get('result')
        transport_result = result.get('TransportContent', {}).get('TransportResult', {})
        transport_detail = result.get('TransportContent', {}).get('TransportDetails', {})
        transport_header = result.get('TransportContent', {}).get('TransportHeader', {})

        transport_status = transport_result.get('TransportStatus', {}).get('value', '')
        ship_type = transport_header.get('ShipmentType', {}).get('value', '')
        is_partnered = True if transport_header.get('IsPartnered', {}).get( \
            'value', '') == 'true' else False

        if is_partnered and ship_type == 'SP' and transport_status in ['ESTIMATED', 'CONFIRMING',
                                                                       'CONFIRMED']:
            small_parcel_data = transport_detail.get('PartneredSmallParcelData', {})
            self.set_estimate_amount(small_parcel_data)
            self.setup_partnered_small_parcel_data(small_parcel_data)
        elif is_partnered and ship_type == 'LTL' and transport_status in ['ESTIMATED',
                                                                          'CONFIRMING',
                                                                          'CONFIRMED']:
            parcel_data = transport_detail.get('PartneredLtlData', {})
            self.set_estimate_amount(parcel_data)
            self.setup_partnered_ltl_data(parcel_data)
        if transport_status in transport_status_list:
            self.write({'transport_state': transport_status})

        if transport_status == 'VOIDED':
            self.reset_inbound_shipment()
        return True

    def estimate_transport_request(self):
        """
        This method is used to send estimate transport request and process transport_status_list
        to get transport content.
        """
        instance = self.get_instance(self)
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo( \
            ).get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'estimate_transport_request_v13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,
                  'shipment_id': self.shipment_id, }

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            error_value = response.get('reason')
            raise UserError(_(error_value))

        result = response.get('result')
        transport_status = result and result.get('TransportResult', {}).get(
            'TransportStatus', {}).get('value', '')
        if transport_status in transport_status_list:
            self.write({'transport_state': transport_status})
            self.get_transport_content()
        return True

    def get_carton_content_result(self):
        """
        This method will request for get feed submission result based on feed_result_id and process
        response.
        """
        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']
        if not self.feed_id:
            return True

        instance = self.get_instance(self)
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'get_feed_submission_result_V13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,
                  'feed_submission_id': self.feed_id.feed_result_id, }

        try:
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                raise UserError(_(response.get('reason')))
            result = response.get('result')
            xml_to_dict_obj = xml2dict()
            result = xml_to_dict_obj.fromstring(result)
            summary = result.get('AmazonEnvelope', {}).get('Message', {}).get( \
                'ProcessingReport', {}).get('ProcessingSummary', {})
            error = summary.get('MessagesWithError', {}).get('value')
            if error != '0':
                job_log_vals = {
                    'module': 'amazon_ept',
                    'type': 'export',
                }
                job = log_obj.create(job_log_vals)
                summary = result.get('AmazonEnvelope', {}).get('Message', {}).get(
                    'ProcessingReport', {}).get('ProcessingSummary', {})
                description = "MessagesProcessed %s" % (
                    summary.get('MessagesProcessed', {}).get('value'))
                description = "%s || MessagesSuccessful %s" % (
                    description, summary.get('MessagesSuccessful', {}).get('value'))
                description = "%s || MessagesWithError %s" % (
                    description, summary.get('MessagesWithError', {}).get('value'))
                description = "%s || MessagesWithWarning %s" % (
                    description, summary.get('MessagesWithWarning', {}).get('value'))
                summary = result.get('AmazonEnvelope', {}).get('Message', {}).get(
                    'ProcessingReport', {}).get('Result', {})
                if not isinstance(summary, list):
                    summary = [summary]
                for line in summary:
                    description = "%s %s" % (description, line.get('ResultDescription'))

                log_line_vals = {
                    'model_id': log_line_obj.get_model_id(
                        'amazon.inbound.shipment.ept'),
                    'res_id': self.id or 0,
                    'message': description,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                self.write({'is_update_inbound_carton_contents': False})
            else:
                self.write({'is_carton_content_updated': True})

        except Exception as e:
            raise UserError(_(str(e)))

        return True

    def export_partnered_small_parcel(self):
        """
        This method is used to export small parcel.
        """
        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo(
        ).get_param('database.uuid')

        for shipment in self:
            instance = self.get_instance(shipment)
            job_log_vals = {
                'module': 'amazon_ept',
                'type': 'export',
            }
            job = log_obj.create(job_log_vals)

            data = {'ShipmentId': shipment.shipment_id,
                    'IsPartnered': 'true' if shipment.is_partnered else 'false',
                    'ShipmentType': 'SP' if shipment.shipping_type == 'sp' else 'LTL'}

            if not shipment.partnered_small_parcel_ids:
                message = 'Inbound Shipment %s is not update in amazon because Parcel not found ' \
                          'for update in amazon' % shipment.name
                log_line_vals = {
                    'model_id': log_line_obj.get_model_id( \
                        'amazon.inbound.shipment.ept'),
                    'res_id': shipment.id,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                continue

            count = 1
            flag = True
            for package in shipment.partnered_small_parcel_ids:
                if not package.ul_id:
                    message = 'Inbound Shipment %s is not update in amazon because dimension ' \
                              'package not found for update' % (shipment.name)
                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id( \
                            'amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    flag = False
                    break
                if package.ul_id.height <= 0.0 or \
                        package.ul_id.width <= 0.0 or package.ul_id.length <= 0.0:
                    message = 'Inbound Shipment %s is not update in amazon because Dimension ' \
                              'Length, Width and Height value must be greater than zero.' % (
                                  shipment.name)
                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id( \
                            'amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    flag = False
                    break
                dimension_unit = package.ul_id.dimension_unit or 'centimeters'
                if shipment.carrier_id:
                    data.update({
                        'TransportDetails.PartneredSmallParcelData.CarrierName':
                            shipment.carrier_id.amz_carrier_code or shipment.carrier_id.name})

                data.update({
                    'TransportDetails.PartneredSmallParcelData.PackageList.member.'
                    '%d.Dimensions.Unit' % (count): dimension_unit})
                data.update({
                    'TransportDetails.PartneredSmallParcelData.PackageList.member.'
                    '%d.Dimensions.Length' % (count): str(package.ul_id.length)})
                data.update({
                    'TransportDetails.PartneredSmallParcelData.PackageList.member.'
                    '%d.Dimensions.Width' % (count): str(package.ul_id.width)})
                data.update({
                    'TransportDetails.PartneredSmallParcelData.PackageList.member.'
                    '%d.Dimensions.Height' % (count): str(package.ul_id.height)})
                data.update({
                    'TransportDetails.PartneredSmallParcelData.PackageList.member.'
                    '%d.Weight.Unit' % (count): package.weight_unit})
                data.update({
                    'TransportDetails.PartneredSmallParcelData.PackageList.member.'
                    '%d.Weight.Value' % (count): str(int(package.weight_value))})
                count += 1
            if flag:
                kwargs = {
                    'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                    'auth_token': instance.auth_token and str(instance.auth_token) or False,
                    'app_name': 'amazon_ept',
                    'account_token': account.account_token,
                    'emipro_api': 'put_transport_content',
                    'dbuuid': dbuuid,
                    'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                               instance.country_id.code,
                    'data': data,
                }
                response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
                if response.get('reason'):
                    error_value = response.get('reason')
                    message = '%s %s' % (error_value, shipment.name)
                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id( \
                            'amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    shipment.write({'state': 'ERROR'})
                else:
                    result = response.get('result')
                    transport_status = result and result.get('TransportResult', {}).get( \
                        'TransportStatus', {}).get('value', '')
                    if transport_status in transport_status_list:
                        shipment.write( \
                            {'transport_state': transport_status,
                             'transport_content_exported': True,
                             'updated_in_amazon': True})

                    shipment.get_transport_content()
                    shipment.estimate_transport_request()

        return True

    def export_non_partnered_small_parcel_tracking(self):
        """
        This method used to export non partnered small parcel tracking
        """
        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']

        ctx = self._context.copy() or {}
        auto_called = ctx.get('auto_called', False)

        for shipment in self:
            instance = self.get_instance(shipment)
            job_log_vals = {
                'module': 'amazon_ept',
                'type': 'export',
            }
            job = log_obj.create(job_log_vals)

            pickings = shipment.picking_ids.filtered( \
                lambda
                    pick: pick.state == 'done' and not pick.is_fba_wh_picking and not pick.updated_in_amazon)

            if not pickings:
                message = 'Inbound Shipment %s is not update in amazon because of system is' \
                          'not found any transferred picking' % shipment.name
                log_line_vals = {
                    'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                    'res_id': shipment.id,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                continue

            pickings = shipment.picking_ids.filtered( \
                lambda pick: pick.state == 'done' and not pick.is_fba_wh_picking)

            data = {'ShipmentId': shipment.shipment_id,
                    'IsPartnered': 'true' if shipment.is_partnered else 'false',
                    'ShipmentType': 'SP' if shipment.shipping_type == 'sp' else 'LTL'
                    }

            if pickings[0].carrier_id:
                carrier_name = pickings[0].carrier_id.amz_carrier_code if pickings[0]. \
                    carrier_id else 'OTHER'

            else:
                carrier_name = 'OTHER'

            data.update( \
                {'TransportDetails.NonPartneredSmallParcelData.CarrierName': str(carrier_name)})
            traking_dict = {}
            count_box = 0
            tacking_no_list = []

            back_orders = shipment.picking_ids.filtered( \
                lambda pick: pick.state not in [ \
                    'done', 'cancel'] and not pick.is_fba_wh_picking and not pick.updated_in_amazon)
            if back_orders:
                back_orders.action_cancel()

            for picking in pickings:
                for op in picking.move_line_ids:
                    tracking_no = op.result_package_id and op.result_package_id.tracking_no
                    if tracking_no and tracking_no not in tacking_no_list:
                        count_box += 1
                        traking_dict.update({
                            'TransportDetails.NonPartneredSmallParcelData.PackageList.member.' + str(
                                count_box) + '.TrackingId': str(tracking_no),
                        })
                        tacking_no_list.append(tracking_no)

                if not traking_dict:
                    message = 'Inbound Shipment %s is not update in amazon because Tracking ' \
                              'number not found in the system' % shipment.name
                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    continue

            while True:
                if count_box >= shipment.box_count:
                    break
                count_box += 1
                traking_dict.update({
                    'TransportDetails.NonPartneredSmallParcelData.PackageList.member.' + str( \
                        count_box) + '.TrackingId': str(' '),
                })

            data.update(traking_dict)
            account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
            dbuuid = self.env['ir.config_parameter'].sudo( \
                ).get_param('database.uuid')

            kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                      'auth_token': instance.auth_token and str(instance.auth_token) or False,
                      'app_name': 'amazon_ept',
                      'account_token': account.account_token,
                      'emipro_api': 'export_non_partnered_small_parcel_tracking_v13',
                      'dbuuid': dbuuid,
                      'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                                 instance.country_id.code,

                      'data': data, }

            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('result'):
                result = response.get('result')
                pickings.write({'updated_in_amazon': True})
                transport_status = result and result.get('TransportResult', {}).get(
                    'TransportStatus', {}).get('value', '')
                if transport_status in transport_status_list:
                    shipment.write( \
                        {'transport_state': transport_status, 'transport_content_exported': True,
                         'state': 'SHIPPED', 'updated_in_amazon': True})

            elif response.get('reason'):
                error_value = response.get('reason')
                message = '%s %s' % (error_value, shipment.name)
                log_line_vals = {
                    'model_id': log_line_obj.get_model_id(
                        'amazon.inbound.shipment.ept'),
                    'res_id': shipment.id,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                shipment.write({'state': 'ERROR'})

            if shipment.state != 'ERROR':
                self.update_shipment_ept(shipment, pickings, back_orders, auto_called, instance,
                                         job)
        return True

    def update_shipment_ept(self, fba_shipment, pickings, back_orders, auto_called, instance,
                            job=False):
        """
        This method is used to update the shipment.
        :param fba_shipment : fba shipment.
        :param pickings : stock pickings
        :param back_orders : back orders
        :param auto_called : check is execution via cron
        :param instance : instance
        :param job : log record.
        """
        amazon_product_obj = self.env['amazon.product.ept']
        sku_list = []
        for picking in pickings:
            for x in range(0, len(picking.move_lines), 1):
                move_lines = picking.move_lines[x:x + 1]
                sku_qty_dict = {}
                list_of_dict = []
                for move in move_lines:
                    if move.state == 'done':
                        amazon_product = amazon_product_obj.search(
                            [('product_id', '=', move.product_id.id),
                             ('instance_id', '=', instance.id), ('fulfillment_by', '=', 'FBA')])
                        if not amazon_product:
                            raise UserError(_(
                                "Amazon Product is not available for this %s product code" % (
                                    move.product_id.default_code)))

                        line = fba_shipment.odoo_shipment_line_ids. \
                            filtered(lambda line: line.amazon_product_id.id == amazon_product.id)

                        qty = sku_qty_dict.get(
                            str(line and line.seller_sku or amazon_product[0].seller_sku), 0.0)
                        qty = move.product_qty + float(qty)
                        sku_qty_dict.update({str(
                            line and line.seller_sku or amazon_product[0].seller_sku): str( \
                            int(qty))})
                if sku_qty_dict:
                    for sku, qty in sku_qty_dict.items():
                        list_of_dict.append({'seller_sku': sku, 'quantity': int(qty)})
                self.update_shipment_in_amazon(picking, list_of_dict, instance, fba_shipment, job,
                                               auto_called)

                sku_list = sku_list + sku_qty_dict.keys()
        for picking in back_orders:
            for x in range(0, len(picking.move_lines), 20):
                move_lines = picking.move_lines[x:x + 20]
                sku_qty_dict = {}
                list_of_dict = []

                for move in move_lines:
                    amazon_product = amazon_product_obj.search(
                        [('product_id', '=', move.product_id.id), ('instance_id', '=', instance.id),
                         ('fulfillment_by', '=', 'FBA')])
                    if not amazon_product:
                        raise UserError(_(
                            "Amazon Product is not available for this %s product code" % (
                                move.product_id.default_code)))

                    line = fba_shipment.odoo_shipment_line_ids. \
                        filtered(lambda line: line.amazon_product_id.id == amazon_product.id)

                    if str(line and line.seller_sku or amazon_product[0].seller_sku) in sku_list:
                        continue
                    if str(line and line.seller_sku or amazon_product[ \
                            0].seller_sku) not in sku_qty_dict:
                        sku_qty_dict.update({str(
                            line and line.seller_sku or amazon_product[0].seller_sku): str( \
                            int(0.0))})
                if sku_qty_dict:
                    for sku, qty in sku_qty_dict.items():
                        list_of_dict.append({'seller_sku': sku, 'quantity': int(qty)})
                self.update_shipment_in_amazon(picking, list_of_dict, instance, fba_shipment,
                                               job, auto_called)
        pickings.write({'shipment_status': 'SHIPPED'})
        return True

    def update_shipment_in_amazon(self, picking, sku_qty_dict, instance, fba_shipment, job,
                                  auto_called):
        """
        # Added By: Dhaval Sanghani [11-Jun-2020]
        This method is used to update shipment in amazon
        """
        log_line_obj = self.env['common.log.lines.ept']
        address = picking.partner_id or fba_shipment.shipment_plan_id.ship_from_address_id

        label_prep_type = fba_shipment.label_prep_type
        if label_prep_type == 'NO_LABEL':
            label_prep_type = 'SELLER_LABEL'
        elif label_prep_type == 'AMAZON_LABEL':
            label_prep_type = fba_shipment.shipment_plan_id.label_preference

        destination = fba_shipment.fulfill_center_id
        shipment_status = 'SHIPPED'
        address_dict = {'name': address.name, 'address_1': address.street or '',
                        'address_2': address.street2 or '', 'city': address.city or '',
                        'country': address.country_id and address.country_id.code or '',
                        'state_or_province': address.state_id and address.state_id.code or '',
                        'postal_code': address.zip or ''}
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo(
        ).get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'update_shipment_in_amazon_v13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,

                  'shipment_name': fba_shipment.name,
                  'shipment_id': fba_shipment.shipment_id,

                  'labelpreppreference': label_prep_type,
                  'shipment_status': shipment_status,
                  'inbound_box_content_status': fba_shipment.intended_box_contents_source,
                  'sku_qty_dict': sku_qty_dict,
                  'address_dict': address_dict,
                  'destination': destination,
                  }

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            error_value = response.get('reason')
            if job:
                log_line_vals = {
                    'model_id': log_line_obj.get_model_id( \
                        'amazon.inbound.shipment.ept'),
                    'res_id': fba_shipment.id,
                    'message': error_value,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
            else:
                if not auto_called:
                    raise UserError(_(error_value))
            fba_shipment.write( \
                {'state': 'ERROR', 'updated_in_amazon': False,
                 'transport_content_exported': False})
            picking.write({'updated_in_amazon': False})
        return True

    def export_non_partnered_ltl_parcel_tracking(self):
        """Updated By: Dhaval Sanghani [29-May-2020]
           Purpose: If Data updated in Amazon then update picking record and set
           updated_in_amazon = True"""

        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']

        ctx = self._context
        auto_called = ctx.get('auto_called', False)
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo( \
            ).get_param('database.uuid')

        for shipment in self:
            instance = self.get_instance(shipment)
            job_log_vals = {
                'module': 'amazon_ept',
                'type': 'export',
            }
            job = log_obj.create(job_log_vals)
            pickings = shipment.picking_ids.filtered( \
                lambda
                    pick: pick.state == 'done' and not pick.is_fba_wh_picking and not pick.updated_in_amazon)

            if not pickings:
                message = 'Inbound Shipment %s is not update in amazon because of system is ' \
                          'not found any transfered picking' % (shipment.name)
                log_line_vals = {
                    'model_id': log_line_obj.get_model_id( \
                        'amazon.inbound.shipment.ept'),
                    'res_id': shipment.id,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                continue

            data = {'ShipmentId': shipment.shipment_id,
                    'IsPartnered': 'true' if shipment.is_partnered else 'false',
                    'ShipmentType': 'SP' if shipment.shipping_type == 'sp' else 'LTL'}

            if not shipment.carrier_id:
                fba_pickings = shipment.picking_ids.filtered('is_fba_wh_picking')
                if fba_pickings and fba_pickings[0].carrier_id:
                    carrier_name = fba_pickings[0].carrier_id.name
                else:
                    carrier_name = 'OTHER'
            else:
                carrier_name = shipment.carrier_id.name

            back_orders = shipment.picking_ids.filtered( \
                lambda pick: pick.state not in ['done',
                                                'cancel'] and not pick.is_fba_wh_picking and not pick.updated_in_amazon)
            if back_orders:
                back_orders.action_cancel()

            data.update({'TransportDetails.NonPartneredLtlData.CarrierName': str(carrier_name)})
            data.update(
                {'TransportDetails.NonPartneredLtlData.ProNumber': str(shipment.pro_number)})

            kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                      'auth_token': instance.auth_token and str(instance.auth_token) or False,
                      'app_name': 'amazon_ept',
                      'account_token': account.account_token,
                      'emipro_api': 'put_transport_content',
                      'dbuuid': dbuuid,
                      'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                                 instance.country_id.code,
                      'data': data, }

            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason'):
                error_value = response.get('reason')
                message = '%s %s' % (error_value, shipment.name)

                log_line_vals = {
                    'model_id': log_line_obj.get_model_id( \
                        'amazon.inbound.shipment.ept'),
                    'res_id': shipment.id,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                shipment.write({'state': 'ERROR'})
            if shipment.state != 'ERROR':
                pickings.write({'updated_in_amazon': True})
                if transport_status in transport_status_list:
                    shipment.write( \
                        {'transport_state': transport_status, 'transport_content_exported': True,
                         'state': 'SHIPPED', 'updated_in_amazon': True})
                self.update_shipment_ept(shipment, pickings, back_orders, auto_called, instance,
                                         job)

        return True

    def confirm_transport_request(self):
        """
        This method is used to confirm transport request.
        """
        instance = self.get_instance(self)
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'confirm_transport_request_v13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,
                  'shipment_id': self.shipment_id, }

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            error_value = response.get('reason')
            raise UserError(_(error_value))

        result = response.get('result')
        transport_status = result.get('TransportResult', {}).get( \
            'TransportStatus', {}).get('value', '')

        if transport_status in transport_status_list:
            self.write({'transport_state': transport_status})
        self.get_transport_content()
        return True

    def reset_inbound_shipment(self):
        """
        This method will set transport_content_exported to false and transport_state to draft.
        """
        self.ensure_one()
        self.transport_content_exported = False
        self.transport_state = 'draft'
        return True

    def void_transport_request(self):
        """Updated By Dhaval Sanghani [29-May-2020]
        # Purpose: We need to only reset Inbound Shipment if we get status = Voided,
        # because may be we can get status like voiding or error_in_voiding"""
        instance = self.get_instance(self)

        if not self.void_deadline_date:
            self.get_transport_content()

        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo( \
            ).get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'void_transport_request_v13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,
                  'shipment_id': self.shipment_id, }

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            error_value = response.get('reason')
            raise UserError(_(error_value))

        result = response.get('result')
        transport_status = result and result.get('TransportResult', {}).get( \
            'TransportStatus', {}).get('value', '')
        if transport_status in transport_status_list:
            self.write({'transport_state': transport_status})

        if transport_status == 'VOIDED':
            self.reset_inbound_shipment()
        return True

    def get_package_labels(self):
        """
        This method will return the amazon shipment label wizard to get package labels.
        """
        ctx = self._context.copy() or {}
        if ctx.get('label_type', '') == 'delivery':
            view = self.env.ref(
                'amazon_ept.amazon_inbound_shipment_print_delivery_label_wizard_form_view',
                False)
        else:
            view = self.env.ref(
                'amazon_ept.amazon_inbound_shipment_print_shipment_label_wizard_form_view',
                False)
            if self.shipping_type == 'sp' and self.is_partnered and not \
                    self.partnered_small_parcel_ids:
                raise UserError(_("Box dimension information's are missing!!! "))
            if self.is_partnered and self.shipping_type == 'ltl':
                ctx.update({'default_number_of_box': self.box_count})
            elif self.is_partnered and self.partnered_small_parcel_ids:
                ctx.update({'default_number_of_box': len(self.partnered_small_parcel_ids.ids),
                            'box_readonly': True})

        ctx.update({'shipping_type': self.shipping_type, })
        return {
            'name': _('Labels'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'amazon.shipment.label.wizard',
            'view_id': view.id,
            'nodestroy': True,
            'target': 'new',
            'context': ctx,
        }

    def get_unique_package_labels(self):
        """
        This method will return the wizard to get unique package labels.
        """
        view = self.env.ref(
            'amazon_ept.amazon_inbound_shipment_print_unique_label_wizard_form_view',
            False)
        if not self.is_partnered:
            return True
        return {
            'name': _('Labels'),
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'amazon.shipment.label.wizard',
            'view_id': view.id,
            'nodestroy': True,
            'target': 'new',
            'context': self._context,
        }

    def check_status(self):
        """
        Check status of Shipment from amazon and update in Odoo as per response of Amazon.
        :return:True
        """
        instance_shipment_ids = defaultdict(list)
        for shipment in self:
            if not shipment.shipment_id:
                continue
            instance = self.get_instance(shipment)
            instance_shipment_ids[instance].append(str(shipment.shipment_id))
        for instance, shipment_ids in instance_shipment_ids.items():
            kwargs = self.amz_prepare_inbound_shipment_kwargs_vals(instance)
            kwargs.update({'emipro_api': 'check_status_v13', 'shipment_ids': shipment_ids})
            response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
            if response.get('reason') and self._context.get('is_auto_process'):
                self.search_or_create_inbound_common_log_ept('import',
                                                             'amazon.inbound.shipment.ept',
                                                             response.get('reason'))
            elif response.get('reason'):
                raise UserError(_(response.get('reason')))
            amazon_shipments = response.get('amazon_shipments') or []
            self.amz_check_status_process_shipments(amazon_shipments, instance)
        return True

    def amz_check_status_process_shipments(self, amazon_shipments, instance):
        """
        :param amazon_shipments:
        :param instance:
        :return:
        """
        stock_picking_obj = self.env['stock.picking']
        for ship_member in amazon_shipments:
            flag = False
            cases_required = True if ship_member.get('AreCasesRequired', {}).get( \
                'value', '') == 'true' else False
            shipmentid = ship_member.get('ShipmentId', {}).get('value', '')
            shipment_status = ship_member.get('ShipmentStatus', {}).get('value', '')
            odoo_shipment_rec = self.search([('shipment_id', '=', shipmentid)])
            already_returned = False
            if shipment_status in ['RECEIVING', 'CLOSED']:
                kwargs = self.amz_prepare_inbound_shipment_kwargs_vals(instance)
                kwargs.update({'emipro_api': 'check_amazon_shipment_status_v13',
                               'amazon_shipment_id': shipmentid})
                response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
                if response.get('reason'):
                    raise UserError(_(response.get('reason')))

                pickings = odoo_shipment_rec.mapped('picking_ids').filtered( \
                    lambda r: r.state in ['assigned'] and r.is_fba_wh_picking)
                if pickings:
                    pickings.check_amazon_shipment_status(response)
                    odoo_shipment_rec.write( \
                        {'state': shipment_status, 'are_cases_required': cases_required})
                    stock_picking_obj.check_qty_difference_and_create_return_picking( \
                        response, shipmentid, odoo_shipment_rec.id, instance)
                    already_returned = True
                else:
                    if odoo_shipment_rec:
                        pickings = odoo_shipment_rec.mapped('picking_ids').filtered(
                            lambda r: r.state in ['draft', 'waiting',
                                                  'confirmed'] and r.is_fba_wh_picking)
                    if not pickings:
                        flag = False
                        self.get_remaining_qty(response, instance, shipmentid, odoo_shipment_rec)
                        odoo_shipment_rec.write( \
                            {'state': shipment_status, 'are_cases_required': cases_required})
                    else:
                        raise UserError(_("""Shipment Status is not update due to picking not found
                                             for processing  ||| Amazon status : %s ERP status : %s
                                             """ % (shipment_status, odoo_shipment_rec.state)))
                if shipment_status == 'CLOSED':
                    if not flag:
                        self.get_remaining_qty(response, instance, shipmentid, odoo_shipment_rec)
                    if not odoo_shipment_rec.closed_date:
                        odoo_shipment_rec.write({'closed_date': time.strftime("%Y-%m-%d")})
                    if odoo_shipment_rec:
                        pickings = odoo_shipment_rec.mapped('picking_ids').filtered(
                            lambda r: r.state in ['partially_available',
                                                  'assigned'] and r.is_fba_wh_picking)
                    if pickings:
                        pickings.action_cancel()
                    if not already_returned:
                        stock_picking_obj.check_qty_difference_and_create_return_picking( \
                            response, shipmentid, odoo_shipment_rec.id, instance)
            else:
                odoo_shipment_rec.write({'state': shipment_status})
        return True

    def amz_prepare_inbound_shipment_kwargs_vals(self, instance):
        """
        Prepare General Arguments for call Amazon MWS API
        :param instance:
        :return: kwargs {}
        @author: Keyur Kanani
        """
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code}
        return kwargs

    def get_remaining_qty(self, response, instance, amazon_shipment_id, odoo_shipment_rec):
        """
        Get remaining Quantity from done or cancelled pickings
        :param instance: amazon.instance.ept()
        :param amazon_shipment_id:
        :param odoo_shipment_rec:
        :return: Boolean
        """
        stock_immediate_transfer_obj = self.env['stock.immediate.transfer']
        pickings = odoo_shipment_rec.picking_ids.filtered(lambda picking:
                                                          picking.state == 'done' and
                                                          picking.is_fba_wh_picking).sorted( \
            key=lambda x: x.id)
        if not pickings:
            pickings = odoo_shipment_rec.picking_ids.filtered(lambda picking:
                                                              picking.state == 'cancel' and picking.is_fba_wh_picking)
        picking = pickings and pickings[0]
        new_picking = self.amz_inbound_copy_new_picking(response, instance, odoo_shipment_rec,
                                                        amazon_shipment_id, picking)
        if new_picking:
            new_picking.action_confirm()
            new_picking.action_assign()
            stock_immediate_transfer_obj.create({'pick_ids': [(4, new_picking.id)]}).process()
        return True

    def amz_inbound_copy_new_picking(self, response, instance, odoo_shipment_rec,
                                     amazon_shipment_id, picking):
        """
        create copy of picking and stock move if quantity mismatch found from done moves and amazon received quantity.
        :param response: list(dict{})
        :param instance: amazon.instance.ept()
        :param odoo_shipment_rec:
        :param amazon_shipment_id:
        :param picking:
        :return:
        """
        picking_obj = self.env['stock.picking']
        new_picking = False
        for item in response.get('items', {}):
            received_qty = float(item.get('QuantityReceived', {}).get('value', 0.0))
            if received_qty <= 0.0:
                continue
            amazon_product = picking_obj.amz_get_inbound_amazon_products_ept(instance, picking,
                                                                             item)
            if not amazon_product:
                continue
            picking_obj.amz_inbound_shipment_plan_line_ept(odoo_shipment_rec, amazon_product, item)
            odoo_product = amazon_product.product_id if amazon_product else False
            received_qty = picking_obj.amz_find_received_qty_from_done_moves(odoo_shipment_rec,
                                                                             odoo_product,
                                                                             received_qty,
                                                                             amazon_shipment_id)
            if received_qty <= 0.0:
                continue
            if not new_picking:
                picking_vals = self.amz_prepare_picking_vals_ept(picking)
                new_picking = picking.copy(picking_vals)
                picking_obj.amz_create_attachment_for_picking_datas(response.get('datas', {}),
                                                                    new_picking)
            move = picking.move_lines[0]
            move_vals = self.amz_prepare_inbound_move_vals_ept(new_picking, odoo_product,
                                                               received_qty)
            move.copy(move_vals)
        return new_picking

    @staticmethod
    def amz_prepare_inbound_move_vals_ept(new_picking, odoo_product, received_qty):
        """
        Prepare move vals for inbound shipment fba warehouse stock move.
        :param new_picking: stock.picking()
        :param odoo_product: produtc.product()
        :param received_qty: float
        :return: dict {}
        """
        return {
            'picking_id': new_picking.id,
            'product_id': odoo_product.id,
            'product_uom_qty': received_qty,
            'product_uom': odoo_product.uom_id.id,
            'procure_method': 'make_to_stock',
            'group_id': False
        }

    @staticmethod
    def amz_prepare_picking_vals_ept(picking):
        """
        Prepare vals for copy fba warehouse picking.
        :param picking: stock.picking()
        :return: dict {}
        """
        return {
            'is_fba_wh_picking': True,
            'move_lines': [],
            'group_id': False,
            'location_id': picking.location_id.id,
            'location_dest_id': picking.location_dest_id.id
        }

    def check_status_ept(self, amazon_shipments, seller, job_id=None):
        """
        method is used to check amazon shipment status.
        """
        stock_picking_obj = self.env['stock.picking']
        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']

        instance = seller.instance_ids
        if amazon_shipments:
            for key, amazon_shipment in amazon_shipments.items():
                shipmentid = key
                shipment = self.search( \
                    [('shipment_id', '=', shipmentid), ('instance_id_ept', 'in', instance.ids)])

                if shipment:
                    pickings = shipment.picking_ids.filtered(lambda picking: picking.state in ( \
                        'partially_available', 'assigned') and picking.is_fba_wh_picking)
                    if pickings:
                        pickings.check_amazon_shipment_status_ept(
                            amazon_shipment, job_id)

                        stock_picking_obj.check_qty_difference_and_create_return_picking_ept( \
                            shipmentid, shipment, shipment.instance_id_ept, amazon_shipment)
                    else:
                        pickings = shipment.picking_ids.filtered(lambda picking: picking.state in ( \
                            'draft', 'waiting', 'confirmed') and picking.is_fba_wh_picking)

                        if not pickings:
                            self.get_remaining_qty_ept(shipment.instance_id_ept, shipmentid,
                                                       shipment, amazon_shipment, job_id)
                        else:
                            if not job_id:
                                job_id = log_obj.create({'module': 'amazon_ept',
                                                         'type': 'import',
                                                         })
                            vals = {
                                'message': """Shipment Status %s is not update due to picking not
                                found for processing  ||| ERP status  : %s """ % ( \
                                    shipmentid, shipment.state),
                                'model_id': log_line_obj.get_model_id( \
                                    'amazon.inbound.shipment.ept'),
                                'res_id': shipment.id,
                                'log_book_id': job_id.id
                            }
                            log_line_obj.create(vals)
                else:
                    if not job_id:
                        job_id = log_obj.create({'module': 'amazon_ept',
                                                 'type': 'import',
                                                 })
                    vals = {
                        'message': """Shipment %s is not found in ERP""" % (shipmentid),
                        'res_id': '',
                        'log_book_id': job_id.id
                    }
                    log_line_obj.create(vals)
        return True

    def get_remaining_qty_ept(self, instance, amazon_shipment_id, odoo_shipment_rec, items, job_id):
        """
        This method is used to get remaining qty
        :param instance : instance record
        :param amazon_shipment_id: amazon shipment
        :param odoo_shipment_rec : odoo shipment
        :items :

        """
        amazon_product_obj = self.env['amazon.product.ept']
        inbound_shipment_plan_line_obj = self.env['inbound.shipment.plan.line']
        log_obj = self.env['common.log.book.ept']
        log_line_obj = self.env['common.log.lines.ept']
        stock_immediate_transfer_obj = self.env['stock.immediate.transfer']

        new_picking = False
        pickings = odoo_shipment_rec.picking_ids.filtered( \
            lambda picking: picking.state == 'done' and picking.is_fba_wh_picking).sorted( \
            key=lambda x: x.id)
        picking = pickings and pickings[0]

        if not picking:
            pickings = odoo_shipment_rec.picking_ids.filtered( \
                lambda picking: picking.state == 'cancel' and picking.is_fba_wh_picking)
            picking = pickings and pickings[0]

        for item in items:
            sku = item.get('SellerSKU', {}).get('value', '')
            asin = item.get('FulfillmentNetworkSKU', {}).get('value')
            shipped_qty = item.get('QuantityShipped', {}).get('value')
            received_qty = float(item.get('QuantityReceived', {}).get('value', 0.0))

            if received_qty <= 0.0:
                continue
            amazon_product = amazon_product_obj.search_amazon_product(instance.id, sku, 'FBA')
            if not amazon_product:
                amazon_product = amazon_product_obj.search( \
                    [('product_asin', '=', asin), ('instance_id', '=', instance.id),
                     ('fulfillment_by', '=', 'FBA')], limit=1)
            if not amazon_product:
                if not job_id:
                    job_id = log_obj.create({'module': 'amazon_ept',
                                             'type': 'import',
                                             })
                vals = {
                    'message': """Product not found in ERP ||| FulfillmentNetworkSKU : %s
                                SellerSKU : %s  
                                Shipped Qty : %s
                                Received Qty : %s                          
                             """ % (asin, sku, shipped_qty, received_qty),
                    'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                    'res_id': odoo_shipment_rec.name,
                    'log_book_id': job_id.id
                }
                log_line_obj.create(vals)
                continue

            inbound_shipment_plan_line = odoo_shipment_rec.odoo_shipment_line_ids. \
                filtered(lambda line: line.amazon_product_id.id == amazon_product.id)

            if inbound_shipment_plan_line:
                inbound_shipment_plan_line[0].received_qty = received_qty or 0.0

            else:
                vals = {
                    'amazon_product_id': amazon_product.id,
                    'quantity': shipped_qty or 0.0,
                    'odoo_shipment_id': odoo_shipment_rec and odoo_shipment_rec[0].id,
                    'fn_sku': asin,
                    'received_qty': received_qty,
                    'is_extra_line': True
                }
                inbound_shipment_plan_line_obj.create(vals)

            odoo_product = amazon_product.product_id if amazon_product else False

            done_moves = odoo_shipment_rec.picking_ids.filtered( \
                lambda
                    r: r.amazon_shipment_id == amazon_shipment_id and r.is_fba_wh_picking).mapped( \
                'move_lines').filtered( \
                lambda r: r.state == 'done' and r.product_id.id == odoo_product.id)

            source_location_id = done_moves and done_moves[0].location_id.id
            for done_move in done_moves:
                if done_move.location_dest_id.id != source_location_id:
                    received_qty = received_qty - done_move.product_qty
                else:
                    received_qty = received_qty + done_move.product_qty
            if received_qty <= 0.0:
                continue
            if not new_picking:
                new_picking = picking.copy( \
                    {'is_fba_wh_picking': True, 'move_lines': [], 'group_id': False,
                     'location_id': picking.location_id.id,
                     'location_dest_id': picking.location_dest_id.id,
                     })

            move = picking.move_lines[0]
            move.copy({'picking_id': new_picking.id,
                       'product_id': odoo_product.id,
                       'product_uom_qty': received_qty,
                       'product_uom': odoo_product.uom_id.id,
                       'procure_method': 'make_to_stock',
                       'group_id': False,
                       })
        if new_picking:
            new_picking.action_confirm()
            new_picking.action_assign()
            stock_immediate_transfer_obj.create({'pick_ids': [(4, new_picking.id)]}).process()
        return True

    def update_non_partnered_carrier(self):
        """
        This method is used to put_transport_content.
        """
        ctx = self._context.copy() or {}
        auto_called = ctx.get('auto_called', False)
        instance = self.get_instance(self)

        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')

        data = {'ShipmentId': self.shipment_id,
                'IsPartnered': 'true' if self.is_partnered else 'false',
                'ShipmentType': 'SP' if self.shipping_type == 'sp' else 'LTL'}
        if self.shipping_type == 'sp':
            data.update({
                'TransportDetails.NonPartneredSmallParcelData.CarrierName': 'OTHER',
                'TransportDetails.NonPartneredSmallParcelData.PackageList.member.' + str(
                    '1') + '.TrackingId': str(' '),
            })
        else:
            carrier_code = self.carrier_id.amz_carrier_code if self.carrier_id else 'OTHER'
            data.update({
                'TransportDetails.NonPartneredLtlData.ProNumber': '##########',
                'TransportDetails.NonPartneredLtlData.CarrierName': carrier_code,
            })

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'put_transport_content',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,

                  'data': data, }
        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            error_value = response.get('reason')
            if not auto_called:
                raise UserError(_(error_value))

        return True

    def export_partnered_ltl_parcel(self):
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo(
        ).get_param('database.uuid')

        for shipment in self:
            log_obj = self.env['common.log.book.ept']
            log_line_obj = self.env['common.log.lines.ept']
            job_log_vals = {
                'module': 'amazon_ept',
                'message': 'Amazon Inbound Shipment Update Parcel (Non partnered(SP))',
                'type': 'export',
            }
            job = log_obj.create(job_log_vals)
            name = shipment.partnered_ltl_id.name or ''
            phone = shipment.partnered_ltl_id.phone or ''
            email = shipment.partnered_ltl_id.email or ''

            if not name or not phone or not email:
                message = 'Invalid contact details found check name/phone/email for contact %s' % ( \
                    name)

                log_line_vals = {
                    'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                    'res_id': shipment.id or 0,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                continue

            if len(shipment.partnered_ltl_ids.ids) <= 0:
                message = 'Number of box must be greater than zero for shipment %s' % (
                    shipment.name)

                log_line_vals = {
                    'model_id': log_line_obj.get_model_id( \
                        'amazon.inbound.shipment.ept'),
                    'res_id': shipment.id or 0,
                    'message': message,
                    'log_book_id': job.id
                }
                log_line_obj.create(log_line_vals)
                continue

            data = {'ShipmentId': shipment.shipment_id,
                    'IsPartnered': 'true' if shipment.is_partnered else 'false',
                    'ShipmentType': 'SP' if shipment.shipping_type == 'sp' else 'LTL',
                    'TransportDetails.PartneredLtlData.Contact.Name': name,
                    'TransportDetails.PartneredLtlData.Contact.Phone': str(phone),
                    'TransportDetails.PartneredLtlData.Contact.Email': email,

                    'TransportDetails.PartneredLtlData.BoxCount': str(
                        len(shipment.partnered_ltl_ids.ids)),
                    'TransportDetails.PartneredLtlData.FreightReadyDate':
                        shipment.freight_ready_date.strftime( \
                            "%Y-%m-%d")
                    }
            instance = self.get_instance(shipment)
            if shipment.seller_freight_class:
                data.update({
                    'TransportDetails.PartneredLtlData.SellerFreightClass':
                        shipment.seller_freight_class})
            count = 1
            flag = True
            for pallet in shipment.partnered_ltl_ids:
                if not pallet.ul_id:
                    message = 'Inbound Shipment %s is not update in amazon because of dimension ' \
                              'for package not found' % shipment.name
                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id('amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    flag = False
                    break
                if pallet.ul_id.length <= 0.0 or pallet.ul_id.width <= 0.0 or \
                        pallet.ul_id.height <= 0.0:
                    message = 'Inbound Shipment %s is not update in amazon because of Dimension ' \
                              'Length, Width and Height value must be greater that zero' % (
                                  shipment.name)

                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id( \
                            'amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    flag = False
                    break

                dimension_unit = pallet.ul_id.dimension_unit or 'centimeters'
                data.update({
                    'TransportDetails.PartneredLtlData.PalletList.member.%d.Dimensions.Unit' % (
                        count): dimension_unit})
                data.update({
                    'TransportDetails.PartneredLtlData.PalletList.member.%d.Dimensions.Length' % (
                        count): str(pallet.ul_id.length)})
                data.update({
                    'TransportDetails.PartneredLtlData.PalletList.member.%d.Dimensions.Width' % (
                        count): str(pallet.ul_id.width)})
                data.update({
                    'TransportDetails.PartneredLtlData.PalletList.member.%d.Dimensions.Height' % (
                        count): str(pallet.ul_id.height)})

                # Not required parameter, so if given then we will set otherwise we skip it.
                if pallet.weight_unit and pallet.weight_value:
                    data.update({
                        'TransportDetails.PartneredLtlData.PalletList.member.%d.Weight.Unit' % ( \
                            count): pallet.weight_unit})
                    data.update({
                        'TransportDetails.PartneredLtlData.PalletList.member.%d.Weight.Value' % ( \
                            count): str(pallet.weight_value)})
                data.update({'TransportDetails.PartneredLtlData.PalletList.member.%d.IsStacked' % ( \
                    count): 'true' if pallet.is_stacked else 'false'})
                count += 1

            # Not required parameter, so if given then we will set otherwise we skip it.
            if shipment.amazon_shipment_weight_unit and shipment.amazon_shipment_weight:
                data.update({'TransportDetails.PartneredLtlData.TotalWeight.Unit': str(
                    shipment.amazon_shipment_weight_unit)})
                data.update({'TransportDetails.PartneredLtlData.TotalWeight.Value': str(
                    shipment.amazon_shipment_weight)})
            if shipment.seller_declared_value and shipment.declared_value_currency_id:
                data.update({
                    'TransportDetails.PartneredLtlData.SellerDeclaredValue.CurrencyCode': str(
                        shipment.declared_value_currency_id.name)})
                data.update({'TransportDetails.PartneredLtlData.SellerDeclaredValue.Value': str(
                    shipment.seller_declared_value)})

            if flag:
                kwargs = {
                    'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                    'auth_token': instance.auth_token and str(instance.auth_token) or False,
                    'app_name': 'amazon_ept',
                    'account_token': account.account_token,
                    'emipro_api': 'put_transport_content',
                    'dbuuid': dbuuid,
                    'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                               instance.country_id.code,
                    'data': data, }

                response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
                if response.get('reason'):
                    error_value = response.get('reason')
                    message = '%s %s' % (error_value, shipment.name)

                    log_line_vals = {
                        'model_id': log_line_obj.get_model_id( \
                            'amazon.inbound.shipment.ept'),
                        'res_id': shipment.id,
                        'message': message,
                        'log_book_id': job.id
                    }
                    log_line_obj.create(log_line_vals)
                    shipment.write({'state': 'ERROR'})
                else:
                    result = response.get('result')
                    transport_status = result and result.get('TransportResult', {}).get(
                        'TransportStatus', {}).get('value', '')
                    if transport_status in transport_status_list:
                        self.write(
                            {'transport_state': transport_status,
                             'transport_content_exported': True, 'updated_in_amazon': True})
                    shipment.get_transport_content()
                    shipment.estimate_transport_request()
        return True

    def get_bill_of_lading(self):
        """
        This method is used to get bill of lading and process to create attachment of response
        """
        self.ensure_one()
        instance = self.get_instance(self)

        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo(
        ).get_param('database.uuid')

        kwargs = {'merchant_id': instance.merchant_id and str(instance.merchant_id) or False,
                  'auth_token': instance.auth_token and str(instance.auth_token) or False,
                  'app_name': 'amazon_ept',
                  'account_token': account.account_token,
                  'emipro_api': 'get_bill_of_lading_v13',
                  'dbuuid': dbuuid,
                  'amazon_marketplace_code': instance.country_id.amazon_marketplace_code or
                                             instance.country_id.code,
                  'shipment_id': self.shipment_id}

        response = iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/iap_request', params=kwargs)
        if response.get('reason'):
            raise UserError(_(response.get('reason')))
        result = response.get('result')
        bol_doc = result.get('TransportDocument', {}).get('PdfDocument', {}).get('value', '')
        if bol_doc:
            bol_doc = base64.b64decode(bol_doc)
            bol_zip = open('/tmp/bill_of_landing.zip', 'wb')
            bol_zip.write(bol_doc)
            bol_zip.close()
            zip_file = open('/tmp/bill_of_landing.zip', 'rb')
            z = zipfile.ZipFile(zip_file)
            for name in z.namelist():
                path = z.extract(name, '/tmp/')
                fh = open(path, 'rb')
                datas = base64.b64encode(fh.read())
                fh.close()
                self.env['ir.attachment'].create({
                    'name': name,
                    'datas': datas,
                    'res_model': self._name,
                    'res_id': self.id,
                    'type': 'binary'
                })
                try:
                    os.remove(path)
                except Exception as e:
                    pass
            zip_file.close()
            try:
                os.remove('/tmp/bill_of_landing.zip')
            except Exception as e:
                pass
        return True
