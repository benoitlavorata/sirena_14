# -*- coding: utf-8 -*-
# See LICENSE file for full copyright and licensing details.

"""
Vat Configuration Class.
"""
from odoo import fields, models


class VatConfigEpt(models.Model):
    """
    For Setting VAT number in warehouse partner.
    @author: Maulik Barad on Date 11-Jan-2020.
    """
    _name = "vat.config.ept"
    _description = "VAT Configuration EPT"
    _rec_name = "company_id"

    def _get_company_domain(self):
        """
        Creates domain to only allow to select company from allowed companies in switchboard.
        @author: Maulik Barad on Date 11-Jan-2020.
        """
        return [("id", "in", self.env.context.get('allowed_company_ids'))]

    company_id = fields.Many2one("res.company", domain=_get_company_domain)
    vat_config_line_ids = fields.One2many("vat.config.line.ept", "vat_config_id")

    _sql_constraints = [
        ("unique_company_vat_config", "UNIQUE(company_id)",
         "VAT configuration is already added for the company.")]
