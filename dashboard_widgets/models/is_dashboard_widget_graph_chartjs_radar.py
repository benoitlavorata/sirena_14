from odoo import api, fields, models

from collections import OrderedDict


class DashboardWidgetGraph(models.Model):
    _inherit = 'is.dashboard.widget'
