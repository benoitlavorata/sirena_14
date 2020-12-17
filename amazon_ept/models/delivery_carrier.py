# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Inherited delivery carrier class
"""

from odoo import models, fields


class DeliveryCarrier(models.Model):
    """
        Amazon Delivery Code will set at time Update Order Status
        Based on matching shipping service level category Carrier will set in Sales Order
    """
    _inherit = "delivery.carrier"

    amz_carrier_code = fields.Selection([('Blue Package', 'Blue Package'),
                                         ('USPS', 'USPS'),
                                         ('UPS', 'UPS'),
                                         ('UPSMI', 'UPSMI'),
                                         ('FedEx', 'FedEx'),
                                         ('DHL', 'DHL'),
                                         ('DHL Global Mail', 'DHL Global Mail'),
                                         ('Fastway', 'Fastway'),
                                         ('UPS Mail Innovations', 'UPS Mail Innovations'),
                                         ('Lasership', 'Lasership'),
                                         ('Royal Mail', 'Royal Mail'),
                                         ('FedEx SmartPost', 'FedEx SmartPost'),
                                         ('OSM', 'OSM'),
                                         ('OnTrac', 'OnTrac'),
                                         ('Streamlite', 'Streamlite'),
                                         ('Newgistics', 'Newgistics'),
                                         ('Canada Post', 'Canada Post'),
                                         ('City Link', 'City Link'),
                                         ('GLS', 'GLS'),
                                         ('GO!', 'GO!'),
                                         ('Hermes Logistik Gruppe', 'Hermes Logistik Gruppe'),
                                         ('Parcelforce', 'Parcelforce'),
                                         ('TNT', 'TNT'),
                                         ('Target', 'Target'),
                                         ('SagawaExpress', 'SagawaExpress'),
                                         ('NipponExpress', 'NipponExpress'),
                                         ('YamatoTransport', 'YamatoTransport'),
                                         ('Other', 'Other')], "Carrier Code")

    amz_shipping_service_level_category = fields.Selection(
        [('Expedited', 'Expedited'), ('NextDay', 'NextDay'), ('SecondDay', 'SecondDay'),
         ('Standard', 'Standard'), ('FreeEconomy', 'FreeEconomy')],
        "Shipping Service Level Category", default='Standard',
        help="Amazon Shipping Categories")
