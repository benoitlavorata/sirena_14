from odoo import api, fields, models


class IsDashboardTemplateType(models.Model):
    _name = 'is.dashboard.widget.type'
    _description = "Dashboard Type"
    _order = "sequence,id"

    name = fields.Char()
    sequence = fields.Integer()
    type = fields.Char()
    preview_image_url = fields.Char()

    default_size_x = fields.Integer(default=3)
    default_size_y = fields.Integer(default=2)
