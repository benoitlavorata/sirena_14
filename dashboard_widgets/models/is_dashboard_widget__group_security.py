from odoo import api, fields, models


class IsDashboardWidgetGroupSecurity(models.Model):
    _name = 'is.dashboard.widget.group_security'
    _description = 'Dashboard Widget Group Security Rule'

    name = fields.Char(string="Description")
    widget_id = fields.Many2one('is.dashboard.widget', string="Widget")
    group_ids = fields.Many2many('res.groups', relation="dashboard_widget_group_rel", string="Group")
    group_exclude_ids = fields.Many2many('res.groups', relation="dashboard_widget_group_exclude_rel", string="Exclude Group")
    note = fields.Text(string="Notes")

    domain = fields.Text(oldname='count_domain', default='[]')
    domain_widget = fields.Char(compute="compute_domain_widget", inverse="inverse_domain")
    domain_hide_widget = fields.Boolean(default=False)

    query_number = fields.Selection(selection=[
        ('query_1', 'Query 1'),
        ('query_2', 'Query 2'),
    ])

    model_id_name = fields.Char(compute="compute_model_id_name", store=True)
    locked = fields.Boolean(related='widget_id.locked')

    @api.depends(
        'query_number',
        'widget_id.query_1_config_model_id_name',
        'widget_id.query_2_config_model_id_name',
    )
    def compute_model_id_name(self):
        for rec in self:
            if rec.query_number == 'query_1':
                rec.model_id_name = rec.widget_id.query_1_config_model_id_name
            elif rec.query_number == 'query_2':
                rec.model_id_name = rec.widget_id.query_2_config_model_id_name
            else:
                rec.model_id_name = False

    @api.depends('domain', 'domain_hide_widget')
    def compute_domain_widget(self):
        for rec in self:
            rec.domain_widget = rec.domain if not rec.domain_hide_widget else False

    @api.onchange('domain_widget')
    def inverse_domain(self):
        for rec in self:
            if rec.domain_widget:
                rec.domain = rec.domain_widget
