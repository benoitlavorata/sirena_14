from odoo import api, fields, models


class IsDashboardWidget(models.Model):
    _inherit = 'is.dashboard.widget'

    query_1_config_domain_additional_ids = fields.One2many('is.dashboard.widget.group_security', 'widget_id', domain=[('query_number', '=', 'query_1')])
    query_2_config_domain_additional_ids = fields.One2many('is.dashboard.widget.group_security', 'widget_id', domain=[('query_number', '=', 'query_2')])
