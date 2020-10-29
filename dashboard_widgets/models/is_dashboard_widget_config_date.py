from odoo import api, fields, models
from datetime import datetime, date


class DashboardWidget(models.Model):
    _inherit = 'is.dashboard.widget'

    widget_type = fields.Selection(selection_add=[("config_date_range", "Date Range")])

    config_date_start = fields.Date("Start")
    config_date_end = fields.Date("End")

    def action_config_update(self):
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }

    def action_edit(self):
        view = self.env.ref('dashboard_widgets.view_is_dashboard_config_date_range_form')
        return {
            'name': self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'is.dashboard.widget',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'view_id': view.id,
        }
