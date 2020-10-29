from odoo import api, fields, models
from odoo.addons.web.controllers.main import clean_action


class IsDashboard(models.Model):
    _inherit = 'is.dashboard'

    def action_open_data(self):
        widget_id = self.env.context.get('dashboard_widget_id')
        widget = self.env['is.dashboard.widget'].browse(widget_id)

        if widget.drilldown_type == 'sub_dashboard' and widget.drilldown_dashboard_id:
            return widget.drilldown_dashboard_id.action_open_dashboard()

        if widget.datasource not in ['query', 'python']:
            return {}

        return widget._action_open_data(
            widget.query_1_config_model_id.model,
            action=widget.action_id,
            domain=widget.get_query_1_domain()
        )

    def action_open_dashboard(self):
        return {
            'name': self.name,
            'type': 'ir.actions.act_window',
            'res_model': 'is.dashboard',
            'view_type': 'form',
            'view_mode': 'form',
            'views': [(False, 'form')],
            'res_id': self.id,
            'context': {
                'dashboard_id': self.id,
            }
        }

    def action_open_data_query_2(self):
        widget_id = self.env.context.get('dashboard_widget_id')
        widget = self.env['is.dashboard.widget'].browse(widget_id)
        return widget._action_open_data(
            widget.query_2_config_model_id.model,
            action=widget.query_2_config_action_id,
            domain=widget.get_query_2_domain()
        ) if widget else {}

    def action_table_action(self, **data):
        widget_id = data.get('dashboard_widget_id') or self.env.context.get('dashboard_widget_id')
        widget = self.env['is.dashboard.widget']
        if widget_id:
            widget = self.env['is.dashboard.widget'].browse(widget_id).exists()
        if widget.drilldown_type == 'sub_dashboard' and widget.drilldown_dashboard_id:
            return widget.drilldown_dashboard_id.action_open_dashboard()
        if widget_id and widget and 'action_model' in data:
            domain = data.get('action_domain', [])
            return widget._action_open_data(model=data['action_model'], action=widget.action_id, domain=domain)
        elif widget_id and widget and 'action_model' in self.env.context:
            domain = self.env.context.get('action_domain', [])
            return widget._action_open_data(model=self.env.context.get('action_model'), action=widget.action_id, domain=domain)

        res = {
            'name': self.env.context.get('action_name') or data.get('action_name') or (self.env.context.get('action_model') and self.env.context['action_model'].name),
            'view_mode': 'form' if self.env.context.get('open_form_view_res_id') or data.get('open_form_view_res_id') else 'list,form',
            'res_model': self.env.context.get('action_model') or data.get('action_model'),
            'views': [(False, 'form')],
            'type': 'ir.actions.act_window',
            'res_id':  self.env.context.get('open_form_view_res_id', None) or data.get('open_form_view_res_id', None),
            'domain': self.env.context.get('action_domain') or data.get('action_domain')
        }
        if 'open_form_view_res_id' in data:
            res['open_form_view_res_id'] = data['open_form_view_res_id']

        return res


class IsDashboardWidgetTableColumn(models.Model):
    _name = 'is.dashboard.widget.auto_view.column'
    _description = 'Dashboard record list field'
    _order = 'sequence'

    sequence = fields.Integer()
    field_id = fields.Many2one('ir.model.fields', string="Column")
    dashboard_id = fields.Many2one('is.dashboard.widget')
    show_sum = fields.Boolean()
    invisible = fields.Boolean(string="Hide Column")


class IsDashboardWidgetTable(models.Model):
    _inherit = 'is.dashboard.widget'

    open_action_1_auto_generate_view = fields.Boolean()
    open_action_1_auto_generate_action_id = fields.Many2one('ir.actions.act_window', readonly=True, string="Auto-Generated Action")
    open_action_1_auto_generate_tree_view_id = fields.Many2one('ir.ui.view', readonly=True, string="List View")
    open_action_1_auto_generate_form_view_id = fields.Many2one('ir.ui.view', string="Form View")
    open_action_1_auto_generate_view_column_ids = fields.One2many(string="Columns", comodel_name='is.dashboard.widget.auto_view.column', inverse_name='dashboard_id')

    def get_auto_view_action_vals(self):
        return {
            'name': self.name,
            'res_model': self.query_1_config_model_id.model,
            'type': 'ir.actions.act_window',
            'view_mode': 'tree,form',
            'view_ids': [(5, 0, 0),
                 (0, 0, {'view_mode': 'tree', 'view_id': self.open_action_1_auto_generate_tree_view_id.id}),
                 (0, 0, {'view_mode': 'form', 'view_id': self.open_action_1_auto_generate_form_view_id.id})
             ]
        }

    def get_auto_view_tree_view_vals(self):
        arch = "<tree>\r\n"
        for col in self.open_action_1_auto_generate_view_column_ids:
            arch += "\t<field name=\"{}\" {} {}/>\r\n".format(
                col.field_id.name,
                "sum=\"{}\"".format(col.field_id.field_description) if col.show_sum else "",
                "invisible=\"1\"" if col.invisible else "",
            )
        arch += "</tree>"
        return {
            'name': "{} (List View)".format(self.name),
            'model': self.query_1_config_model_id.model,
            'priority': 99,
            'arch_base': arch,
        }

    def action_update_auto_view(self):
        for rec in self:
            if not rec.drilldown_type == 'custom_action':
                continue

            if not rec.open_action_1_auto_generate_tree_view_id:
                rec.open_action_1_auto_generate_tree_view_id = self.env['ir.ui.view'].sudo().create(rec.get_auto_view_tree_view_vals())
            else:
                rec.sudo().open_action_1_auto_generate_tree_view_id.write(rec.get_auto_view_tree_view_vals())

            if not rec.open_action_1_auto_generate_action_id:
                rec.open_action_1_auto_generate_action_id = self.env['ir.actions.act_window'].sudo().create(rec.get_auto_view_action_vals())
            else:
                rec.sudo().open_action_1_auto_generate_action_id.write(rec.get_auto_view_action_vals())
            rec.action_id = rec.open_action_1_auto_generate_action_id

    def _action_open_data(self, model, action=False, domain=False, **kwargs):
        self.ensure_one()

        if action:
            action = action.read([])[0]
            action['name'] = self.name,
        else:
            action = {
                'name': self.name,
                'type': 'ir.actions.act_window',
                'res_model': model,
                'view_mode': 'tree,form',
            }

        if domain:
            action['domain'] = domain

        return clean_action(action, self.env)
