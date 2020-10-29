from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval as safe_eval
from datetime import datetime, date


class DashboardWidgetNotes(models.Model):
    _inherit = 'is.dashboard.widget'

    note = fields.Text(string="Internal Notes")
    note_kanban = fields.Html(string="Notes On Dashboard")
