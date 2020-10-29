from odoo import models, fields, api


class DashboardWidgetTag(models.Model):
    _name = 'is.dashboard.widget.tag'
    _description = "Dashboard Record Tag"

    name = fields.Char(string="Name", required=True)
