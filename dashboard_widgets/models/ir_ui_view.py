from odoo import api, fields, models


class IrUiView(models.Model):
    _inherit = 'ir.ui.view'

    mig_flag_dashboard = fields.Boolean(default=False)
