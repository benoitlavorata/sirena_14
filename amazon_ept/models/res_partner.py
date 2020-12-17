# -*- coding: utf-8 -*-pack
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import api, models, fields
from odoo.addons.iap.tools import iap_tools
from ..endpoint import DEFAULT_ENDPOINT


class ResPartner(models.Model):
    """
    Inherited for VAT configuration in partner of Warehouse.
    """
    _inherit = "res.partner"

    is_amz_customer = fields.Boolean("Is Amazon Customer?")

    @api.model
    def _search(self, args, offset=0, limit=None, order=None, count=False, access_rights_uid=None):
        if not self.env.context.get('is_amazon_partner', False):
            args = [('is_amz_customer', '=', False)] + list(args)
        return super(ResPartner, self)._search(args, offset, limit, order, count, access_rights_uid)

    @api.onchange("country_id")
    def _onchange_country_id(self):
        """
        Inherited for updating the VAT number of the partner as per the VAT configuration.
        @author: Maulik Barad on Date 13-Jan-2020.
        """
        if self.country_id:
            warehouse_ids = self.env["stock.warehouse"].search_read(\
                [("partner_id", "=", self._origin.id)],
                ["id", "company_id"])
            if warehouse_ids:
                vat_config = self.env["vat.config.ept"].search(\
                    [("company_id", "=", warehouse_ids[0].get("company_id")[0])])
                vat_config_line = vat_config.vat_config_line_ids.filtered(\
                    lambda x: x.country_id == self.country_id)
                if vat_config_line:
                    self.write({"vat": vat_config_line.vat})
        return super(ResPartner, self)._onchange_country_id()

    @api.model
    def create(self, vals):
        if vals.get('is_amz_customer'):
            vals.update({'allow_search_fiscal_based_on_origin_warehouse': True})
        return super(ResPartner, self).create(vals)

    def auto_delete_customer_pii_details(self):
        """
        Auto Archive Customer's PII Details after 30 days of Import as per Amazon MWS Policies.
        :return:
        """
        if not self.env['amazon.seller.ept'].search([]):
            return True
        account = self.env['iap.account'].search([('service_name', '=', 'amazon_ept')])
        dbuuid = self.env['ir.config_parameter'].sudo().get_param('database.uuid')
        kwargs = {
            'app_name': 'amazon_ept',
            'account_token': account.account_token,
            'dbuuid': dbuuid,
            'updated_records': 'Scheduler for delete PII data has been started.'
        }
        iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/delete_pii', params=kwargs, timeout=1000)
        query = """update res_partner set name='Amazon',commercial_company_name='Amazon', 
                    display_name='Amazon', 
                    street=NULL,street2=NULL,email=NULL,city=NULL,state_id=NULL,country_id=NULL,
                    zip=Null,phone=NULL,mobile=NULL
                    from
                    (select r1.id as partner_id,r2.id as partner_invoice_id,r3.id as 
                    partner_shipping_id from sale_order
                    inner join res_partner r1 on r1.id=sale_order.partner_id
                    inner join res_partner r2 on r2.id=sale_order.partner_invoice_id
                    inner join res_partner r3 on r3.id=sale_order.partner_shipping_id
                    where amz_instance_id is not null and sale_order.create_date<=current_date-30)T
                    where res_partner.id in 
                    (T.partner_id,T.partner_invoice_id,T.partner_shipping_id)
                    """
        self.env.cr.execute(query)

        if self.env.cr.rowcount:
            kwargs.update({'updated_records': 'Archived %d customers' % self.env.cr.rowcount})
            iap_tools.iap_jsonrpc(DEFAULT_ENDPOINT + '/delete_pii', params=kwargs, timeout=1000)
        return True
