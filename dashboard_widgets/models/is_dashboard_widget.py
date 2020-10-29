from odoo import models, fields, api
from datetime import date, datetime

import json
from odoo.tools import frozendict
from odoo.addons.web.controllers.main import clean_action


class DashboardWidget(models.Model):
    _name = 'is.dashboard.widget'
    _description = "Dashboard Record"
    _order = 'sequence,id'

    # TODO Delete
    preview_id = fields.Char()
    # /TODO Delete

    name = fields.Char(string="Name", required=True)
    sequence = fields.Integer()
    display_mode = fields.Selection(string="Dashboard Type", selection=[('line_break', 'Start New Line')], required=True)
    datasource = fields.Selection(string="Data Source", required=True, selection=[])

    use_cache = fields.Boolean(string="Use Cached results", help="Store a cached copy of the results for faster rendering for slow running queries")
    last_cache_updated_datetime = fields.Datetime(string="Cache Last Updated", readonly=True)

    show_on_global_dashboard = fields.Boolean(string="Show on dashboard", default=False)

    config_id = fields.Many2one(comodel_name="is.dashboard.widget", string="Config")

    group_by_label = fields.Char(string="Group By Label")
    dashboard_ids = fields.Many2many(comodel_name='is.dashboard', relation='is_dashboard_widget_position', column1='widget_id', column2='dashboard_id', string="Tags", copy=False)
    tag_ids = fields.Many2many('is.dashboard.widget.tag', string="Dashboard Tags")

    show_on_partner_dashboard = fields.Boolean(string="Show on partner dashboard")

    drilldown_type = fields.Selection(string="Drill-down Type", selection=[
        ('standard', 'Standard'),
        ('sub_dashboard', 'Sub-Dashboard'),
        ('custom_action', 'Custom Action/View'),
    ], default='standard', required=True)
    action_id = fields.Many2one(string="Action", comodel_name='ir.actions.act_window')
    drilldown_dashboard_id = fields.Many2one('is.dashboard', string="Drill-down Dashboard")

    kanban_class_main = fields.Char(string="Kanban Class Main", compute='_compute_kanban_class_main')

    color = fields.Integer(string='Color Index')
    background_color = fields.Char()

    date_end = fields.Datetime(compute="compute_date_range")
    date_start = fields.Datetime(compute="compute_date_range")

    dashboard_data = fields.Text(compute='compute_dashboard_data')

    hide_dashboard_item = fields.Boolean(string="Hide dashboard Item")
    widget_hidden = fields.Boolean(compute="compute_widget_hidden")

    render_dashboard_markup = fields.Html(compute="compute_render_dashboard_markup", sanitize=False)

    pos_x = fields.Integer(string="Position X", compute='_compute_position', inverse='_set_positions')
    pos_y = fields.Integer(string="Position Y", compute='_compute_position', inverse='_set_positions')

    size_x = fields.Integer(string="Size X", compute='_compute_position', inverse='_set_positions')
    size_y = fields.Integer(string="Size Y", compute='_compute_position', inverse='_set_positions')

    display_allow_scrolling = fields.Boolean(string="Allow scrolling")

    def get_render_data(self):
        return {
            'name': self.name,
            'widget_id': self.id,
            'display_mode': self.display_mode,
            'widget_type': self.widget_type,
            'display_allow_scrolling': self.display_allow_scrolling,
        }

    def compute_render_dashboard_markup(self):
        for rec in self:
            try:
                rec._setup_render_dashboard_markup_error()
                rec._compute_kanban_class_count()  # TODO: Done to fix Odoo cache miss error. Can we fix and remove the underlying issue here?

                markup = self.env['ir.qweb']._render('dashboard_widgets.render_dashboard_widget', values={'record': rec, 'data': rec.get_render_data()})
                errors = rec._get_render_dashboard_markup_errors()
                if errors:
                    rec.render_dashboard_markup = "ERROR: {0}".format(repr(errors))
                else:
                    rec.render_dashboard_markup = markup
            except Exception as ex:
                errors = rec._get_render_dashboard_markup_errors()
                if errors:
                    pass
                rec.render_dashboard_markup = "ERROR: {0}".format(repr(ex))

    def _setup_render_dashboard_markup_error(self):
        if isinstance(self.env.context, frozendict):
            self.env.context.render_dashboard_markup_errors = []
        else:
            self.env.context['render_dashboard_markup_errors'] = []

    def _get_render_dashboard_markup_errors(self):
        if isinstance(self.env.context, frozendict) and hasattr(self.env.context, 'render_dashboard_markup_errors'):
            return self.env.context.render_dashboard_markup_errors
        else:
            return self.env.context.get('render_dashboard_markup_errors')

    def _add_render_dashboard_markup_error(self, title, error):
        if isinstance(self.env.context, frozendict):
            if not hasattr(self.env.context, 'render_dashboard_markup_errors'):
                self.env.context.render_dashboard_markup_errors = []
            self.env.context.render_dashboard_markup_errors += (title, error)
        else:
            if 'render_dashboard_markup_errors' not in self.env.context:
                self.env.context['render_dashboard_markup_errors'] = []
            self.env.context['render_dashboard_markup_errors'] += (title, error)

    def get_widget_hidden(self):
        return self.hide_dashboard_item  # Allow override in other functions

    def compute_widget_hidden(self):
        for rec in self:
            rec.widget_hidden = rec.get_widget_hidden()

    @staticmethod
    def _dashboard_json_converter(o):
        if isinstance(o, datetime):
            return fields.Datetime.to_string(o)
        elif isinstance(o, date):
            return fields.Date.to_string(o)
        elif o.__class__.__name__ == 'lazy':
            return o.__str__()
        raise TypeError("Unable to parse type {}".format(o.__class__.__name__))

    def compute_dashboard_data(self):
        for rec in self:
            rec.dashboard_data = json.dumps(rec.get_dashboard_data(), default=self._dashboard_json_converter)

    def get_dashboard_data(self):
        pass  # Functionality defined in extension modules

    def compute_date_range(self):
        pass  # Hook in each implementation

    def action_open_data_segment(self, data):
        if self.drilldown_type == 'sub_dashboard' and self.drilldown_dashboard_id:
            return self.drilldown_dashboard_id.action_open_dashboard()
        if all(x in data for x in ['data_model', 'data_action']):
            model = data['data_model']
            action = data['data_action']
            if action:
                action = self.env['ir.actions.act_window'].browse(action).exists()
            domain = data.get('data_domain', [])
            return self._action_open_data(model=model, action=action, domain=domain)

    @api.depends()
    def _compute_kanban_class_main(self):
        for rec in self:
            rec.kanban_class_main = ''

    def _action_open_data(self, model, action=False, domain=False, **kwargs):
        self.ensure_one()

        if action:
            action = action.read([])[0]
        else:
            action = {
                'name': self.name,
                'type': 'ir.actions.act_window',
                'res_model': model,
                'view_mode': 'tree,form',
            }

        if domain:
            action['domain'] = domain

        return clean_action(action)

    def _compute_position(self):
        if self.env.context.get('preview_mode'):
            for rec in self:
                rec.pos_x = 1
                rec.pos_y = 1
                rec.size_x = 10
                rec.size_y = 3
            return
        if self.env.context.get('template_mode'):
            for i, rec in enumerate(self):
                rec.pos_x = 6 if i % 2 else 0
                rec.pos_y = 4 * i
                rec.size_x = 6
                rec.size_y = 2 if rec.display_mode == 'card' else 3
            return
        dashboard_id = self.env.context.get('dashboard_id', 0)
        positions = self.env['is.dashboard.widget.position'].search_read([('dashboard_id', '=', dashboard_id)], ['pos_x', 'pos_y', 'size_x', 'size_y', 'widget_id'])
        positions = {position['widget_id'][0]: position for position in positions}

        for rec in self:
            if rec.id in positions:
                rec.pos_x = positions[rec.id]['pos_x']
                rec.pos_y = positions[rec.id]['pos_y']
                rec.size_x = positions[rec.id]['size_x']
                rec.size_y = positions[rec.id]['size_y']
            else:
                rec.pos_x = 0
                rec.pos_y = 0
                rec.size_x = 0
                rec.size_y = 0

    def _set_positions(self):
        for rec in self:
            dashboard_id = self.env.context.get('params', {}).get('id', 0)
            if not dashboard_id or self.env.context.get('preview_mode') or self.env.context.get('template_mode'):
                return
            self.env['is.dashboard.widget.position'].search([('widget_id', '=', rec.id), ('dashboard_id', '=', dashboard_id)]).write({
                'pos_x': rec.pos_x,
                'pos_y': rec.pos_y,
                'size_x': rec.size_x,
                'size_y': rec.size_y
            })

from odoo.addons.dashboard_widgets.controllers.main import DashboadWidgetsHelper
class DashboardWidget2(models.Model):
    _inherit = 'is.dashboard.widget'

    preview_ids = fields.Many2many(comodel_name='is.dashboard.widget', compute='compute_preview_ids', string="Preview")
    preview_data = fields.Text(compute="compute_preview_data")

    @api.onchange(
        'preview_data',
    )
    def compute_preview_ids(self):
        for rec in self:
            rec.preview_ids = rec.ids

    #TODO: Dynamic of all relevent fields
    @api.onchange(
        'name',
        'display_mode',
        'widget_type',
        'card_primary_display',
        'card_hide_when_no_data',
        'card_1_goal_standard',
        'card_1_config_enable_forecast',
        'widget_type_is_a_count',
        'widget_type_is_a_count_over_total',
        'count',
        'total',
        'goal_count_variance',
        'goal_total_variance',
        'goal_forecast_count_variance',
        'goal_forecast_total_variance',
        'current_goal_count',
        'current_goal_total',
        'forecast_count',
        'expected_count',
        'expected_total',
        'forecast_total',
        'forecast_count_meets_goal',
        'forecast_total_meets_goal',
        'has_forecast_1',
        'has_forecast_2',
        'show_expected_1',
        'show_goal_1',
        'show_expected_1_label',
        'show_goal_1_label',
        'show_expected_2',
        'show_goal_2',
        'show_expected_2_label',
        'show_goal_2_label',
        'show_forecast_1',
        'show_forecast_1_label',
        'show_forecast_2',
        'show_forecast_2_label',
        'show_variation_1',
        'show_variation_1_label',
        'show_variation_2',
        'show_variation_2_label',
        'show_forecasted_variation_1',
        'show_forecasted_variation_1_label',
        'show_forecasted_variation_2',
        'show_forecasted_variation_2_label',
        'kanban_class_count',
        'kanban_class_name',
        'kanban_class_expected',
        'kanban_class_goal',
        'kanban_class_variation',
        'kanban_class_forecast',
        'kanban_class_forecasted_variation',
        'background_color',
        'goal_count',
        'goal_total',
        'goal_1_show_future_goals',
        'goal_1_is_greater_than',
        'goal_1_line_ids',
        'goal_2_is_greater_than',
        'goal_2_line_ids',
        'current_goal_date_start',
        'current_goal_date_end',

        'graph_type',
        'show_values_on_graph',
        'use_suggested_min_y_axis',
        'use_suggested_max_y_axis',
        'suggested_min_y_axis',
        'suggested_max_y_axis',
        'use_decimal_precision_y_axis',
        'decimal_precision_y_axis',
        'chart_display_value_prefix',
        'chart_1_config_show_average_dataset',
        'chart_1_config_aggregate_field_id',
        'chart_1_config_aggregate_operator',
        'chart_1_config_aggregate_operator_supported',
        'chart_1_config_aggregate2_field_id',
        'chart_1_config_aggregate2_operator',
        'chart_1_config_aggregate2_operator_supported',
        'chart_1_config_show_empty_groups',
        'chart_1_config_color',
        'chart_1_config_area',
        'chart_1_config_title',
        'chart_1_config_sort_field_id',
        'chart_1_config_sort_default_by_label',
        'chart_1_config_sort_descending',
        'chart_1_goal_config_color',
        'chart_1_goal_config_area',
        'chart_1_goal_config_title',
        'chart_2_config_show_average_dataset',
        'chart_2_config_aggregate_field_id',
        'chart_2_config_aggregate_operator',
        'chart_2_config_aggregate_operator_supported',
        'chart_2_config_aggregate2_field_id',
        'chart_2_config_aggregate2_operator',
        'chart_2_config_aggregate2_operator_supported',
        'chart_2_config_show_empty_groups',
        'chart_2_config_color',
        'chart_2_config_area',
        'chart_2_config_title',
        'chart_2_config_sort_field_id',
        'chart_2_config_sort_default_by_label',
        'chart_2_config_sort_descending',
        'chart_2_goal_config_color',
        'chart_2_goal_config_area',
        'chart_2_goal_config_title',

        'query_1_config_accumulative',
        'query_2_config_accumulative',
        'graph_1_bar_stacked',
        'html',
        'iframe_url',
        'note_kanban',
        'record_list_column_ids',
        'record_list_column_ids.sequence',
        'record_list_column_ids.field_id',
        'record_list_column_ids.name',
        'record_list_column_ids.format_string',
        'table_display_value_prefix',

        'datasource',
        'query_1_config_domain',
        'query_1_config_domain_widget',
        'query_1_config_domain_use_widget',
        'query_1_config_model_id',
        'query_1_config_model_id_name',
        'query_1_config_measure_field_id',
        'query_1_config_measure_operator',
        'query_1_config_measure_operator_supported',
        'query_1_config_result_limit',
        'query_1_config_date_range_type',
        'query_1_config_date_single_range_operator',
        'query_1_config_date_range_custom_start',
        'query_1_config_date_range_custom_end',
        'query_1_config_datetime_range_custom_start',
        'query_1_config_datetime_range_custom_end',
        'query_1_config_date_range_field_id',
        'query_1_config_date_range_x',
        'query_1_config_date_range_x_label',
        'query_1_config_date_is_datetime',
        'query_1_config_date_range_start',
        'query_1_config_date_range_end',
        'query_1_config_datetime_range_start',
        'query_1_config_datetime_range_end',
        'query_1_config_enable_goal',
        'query_1_sudo',
        'help_date_range_types_display',
        'query_2_config_domain',
        'query_2_config_domain_widget',
        'query_2_config_domain_use_widget',
        'query_2_config_model_id',
        'query_2_config_model_id_name',
        'query_2_config_measure_field_id',
        'query_2_config_measure_operator',
        'query_2_config_measure_operator_supported',
        'query_2_config_result_limit',
        'query_2_config_date_range_type',
        'query_2_config_date_single_range_operator',
        'query_2_config_date_range_custom_start',
        'query_2_config_date_range_custom_end',
        'query_2_config_datetime_range_custom_start',
        'query_2_config_datetime_range_custom_end',
        'query_2_config_date_range_field_id',
        'query_2_config_date_range_x',
        'query_2_config_date_range_x_label',
        'query_2_config_date_is_datetime',
        'query_2_config_date_range_start',
        'query_2_config_date_range_end',
        'query_2_config_datetime_range_start',
        'query_2_config_datetime_range_end',
        'query_2_config_enable_goal',
        'query_2_config_action_id',
        'query_2_sudo',
        'query_2_config_context',
    )
    def compute_preview_data(self):
        for rec in self:
            rec.compute_render_dashboard_markup()
            rec.compute_dashboard_data()
            data = DashboadWidgetsHelper._dashboard_render_data(self, rec)
            if isinstance(data['data'], bytes):
                data['data'] = data['data'].decode("utf-8")
            rec.preview_data = json.dumps(data)
