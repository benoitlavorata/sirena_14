# -*- coding: utf-8 -*-
"""
inherited sale report class and inherited method to update the query.
"""

from odoo import fields, models


class SaleReport(models.Model):
    """
    Added class to add fields to relate wth the instance, seller and selling on and
    updated query to get sale report with group by those fields.
    """
    _inherit = "sale.report"

    amz_instance_id = fields.Many2one('amazon.instance.ept', 'Amazon Instances', readonly=True)
    amz_seller_id = fields.Many2one('amazon.seller.ept', 'Amazon Sellers', readonly=True)
    amz_fulfillment_by = fields.Selection([('FBA', 'Fulfilled By Amazon'),
                                           ('FBM', 'Fulfilled By Merchant')],
                                          string='Fulfillment By', readonly=True)

    def _query(self, with_clause='', fields={}, groupby='', from_clause=''):
        """
        inherited method to group by with the added custom fields.
        """
        fields[
            'amazon_report_fields'] = ", s.amz_instance_id as amz_instance_id , s.amz_seller_id " \
                                      "as amz_seller_id , s.amz_fulfillment_by as amz_fulfillment_by"
        groupby += ', s.amz_instance_id, s.amz_seller_id, s.amz_fulfillment_by'
        return super(SaleReport, self)._query(with_clause, fields, groupby, from_clause)
