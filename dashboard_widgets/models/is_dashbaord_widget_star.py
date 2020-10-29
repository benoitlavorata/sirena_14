from odoo import api, fields, models


class IsDashbaordWidgetStar(models.Model):
    _name = 'is.dashboard.widget'

    display_mode = fields.Selection(selection_add=[
        ('star', 'Star Rating'),
    ], ondelete={'star': 'set default'})
