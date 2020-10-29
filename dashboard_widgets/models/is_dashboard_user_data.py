from odoo import api, fields, models


class IsDashboardUserData(models.Model):
    _name = 'is.dashboard.user_data'
    _description = "Dashboard User Data"

    dashboard_id = fields.Many2one('is.dashboard')
    user_id = fields.Many2one('res.users')

    date_range_type = fields.Char()
