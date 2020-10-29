from odoo import models, fields, api
import json


class ResPartner(models.Model):
    _inherit = 'res.partner'

    dashboard_ids = fields.One2many('is.dashboard.widget', string="Dashboard", compute="_compute_dashboard_ids", readonly=True)

    def _compute_dashboard_ids(self):
        for rec in self:
            rec.dashboard_ids = self.env['is.dashboard.widget'].search([('show_on_partner_dashboard', '=', True)])
