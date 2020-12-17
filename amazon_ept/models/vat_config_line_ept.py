# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.


"""
Main Model for Vat Configuration.
"""
import logging
from odoo import api, fields, models

_logger = logging.getLogger("Amazon")


class VatConfigLineEpt(models.Model):
    """
    For Setting VAT number for Country.
    @author: Maulik Barad on Date 11-Jan-2020.
    """
    _name = "vat.config.line.ept"
    _description = "VAT Configuration Line EPT"

    def _get_country_domain(self):
        """
        Creates domain to only allow to select company from allowed companies in switchboard.
        @author: Maulik Barad on Date 11-Jan-2020.
        """
        europe_group = self.env.ref("base.europe")
        return [("id", "in", europe_group.country_ids.ids)]

    vat_config_id = fields.Many2one("vat.config.ept", ondelete="cascade")
    vat = fields.Char("VAT Number")
    country_id = fields.Many2one("res.country", domain=_get_country_domain)

    _sql_constraints = [
        ("unique_country_vat_config", "UNIQUE(vat_config_id,country_id)",
         "VAT configuration is already added for the country.")]

    @api.model
    def create(self, values):
        """
        Inherited the create method for updating the VAT number and creating Fiscal positions.
        @author: Maulik Barad on Date 13-Jan-2020.
        """
        result = super(VatConfigLineEpt, self).create(values)

        fiscal_position_obj = self.env["account.fiscal.position"]
        tax_configuration_obj = self.env['amazon.tax.configuration.ept']
        amz_seller_obj = self.env['amazon.seller.ept']
        data = {"company_id": result.vat_config_id.company_id.id,
                "country_id": values["country_id"],
                "auto_apply": True, "vat_config_id": values["vat_config_id"],
                "is_amazon_fpos": True}
        country_name = result.country_id.name
        excluded_vat_registered_europe_group = self.env.ref(
            "amazon_ept.excluded_vat_registered_europe")
        if data["country_id"] in excluded_vat_registered_europe_group.country_ids.ids:
            excluded_vat_registered_europe_group.country_ids = [(3, data["country_id"], 0)]
            _logger.info("Country removed from Europe group....")

        # Updating the VAT number into warehouse's partner of the same country.
        warehouses = self.env["stock.warehouse"].search([("company_id", "=", data["company_id"])])
        if warehouses:
            warehouse_partners = warehouses.partner_id.filtered(
                lambda x: x.country_id.id == data["country_id"])
            warehouse_partners.write({"vat": values["vat"]})
            _logger.info("VAT number updated of Warehouse's partner.")

        # Creating Fiscal position.
        existing_fiscal_position = fiscal_position_obj.search_read(
            [("company_id", "=", data["company_id"]), ("country_id", "=", data["country_id"]),
             ("auto_apply", "=", True)], ["id"])
        if not existing_fiscal_position:
            data["name"] = "Deliver to %s" % country_name
            fiscal_position_obj.create(data)
            _logger.info("Fiscal position created for country %s." % country_name)
        existing_excluded_fiscal_position = fiscal_position_obj.search_read(
            [("company_id", "=", data["company_id"]),
             ("origin_country_ept", "=", data["country_id"]),
             ("country_group_id", "=", excluded_vat_registered_europe_group.id),
             ("auto_apply", "=", True)],
            ["id"])
        if not existing_excluded_fiscal_position:
            data.update(
                {"name": "Deliver from %s to Europe(Exclude VAT registered country)" % country_name,
                 "origin_country_ept": data["country_id"],
                 "country_group_id": excluded_vat_registered_europe_group.id})
            del data["country_id"]
            fiscal_position_obj.create(data)
            _logger.info(
                "Fiscal position created from %s to Excluded country group." % country_name)

        sellers = amz_seller_obj.search([('company_id', '=', result.vat_config_id.company_id.id),
                                         ('country_id', 'in',
                                          self.env.ref("base.europe").country_ids.ids)])
        existing_tax_config = tax_configuration_obj.search(
            [('jurisdiction_country_id', '=', result.country_id.id),
             ('seller_id', 'in', sellers.ids)])
        if not existing_tax_config:
            for seller in sellers:
                tax_config = tax_configuration_obj.create({
                    'seller_id': seller.id,
                    'jurisdiction_country_id': result.country_id.id,
                    'is_outside_eu': True
                })
                tax_config.copy({'is_outside_eu': False})
        else:
            for tax_conf in existing_tax_config:
                if tax_conf.is_outside_eu:
                    tax_conf.copy({'is_outside_eu': False})
                else:
                    tax_conf.copy({'is_outside_eu': True})
        return result
