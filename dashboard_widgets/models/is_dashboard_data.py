from odoo import api, fields, models


class IsDashboardData(models.Model):
    _name = 'is.dashboard.data'
    _description = "Dashboard Data"

    date = fields.Datetime(string="Date", readonly=True)
    type = fields.Char(string="Type", readonly=True)
    value_float = fields.Float(string="Value", readonly=True)
    value_string = fields.Char(string="String Value", readonly=True)

    def cron_update_dashboard_data(self):
        # hook for modules to update data types
        return
