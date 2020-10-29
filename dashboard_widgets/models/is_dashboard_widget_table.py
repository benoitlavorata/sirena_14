from odoo import api, fields, models
import json


class IsDashboardWidgetTable(models.Model):
    _inherit = 'is.dashboard.widget'

    display_mode = fields.Selection(selection_add=[
        ('table', 'Query Table'),
    ], ondelete={'table': 'set default'})

    table_display_value_prefix = fields.Char()

    def action_table_action(self, **data):

        if 'action_model' in data:
            domain = data.get('action_domain', [])
            return self._action_open_data(model=data['action_model'], action=self.action_id, domain=domain)

        return {
            'name': self.env.context.get('action_name') or self.env.context['action_model'].name,
            'view_mode': 'form' if self.env.context.get('open_form_view_res_id') else 'list,form',
            'res_model': self.env.context['action_model'],
            'type': 'ir.actions.act_window',
            'res_id':  self.env.context.get('open_form_view_res_id', None),
            'domain': self.env.context['action_domain'],
        }

    def get_render_data(self):
        render_data = super(IsDashboardWidgetTable, self).get_render_data()

        if self.display_mode != 'table':
            return render_data

        if self.datasource == 'python':
            table_data = self.eval_data(self.query_1_table)
            if not table_data:
                return render_data

            headers = table_data.get('headers', [])
            render_data['table'] = {
                'record': self,
                'headers': headers,
                'rows': [[{
                    'value': cell.get('value') or cell.get('display_value') or '',
                    'display_value': self.human_format_value(cell.get('display_value') or cell.get('value') or ''),
                    'class': cell.get('class') or headers[icell].get('column_class') if len(headers) > icell else '',
                    'action': {
                        'type': 'object',
                        'name': 'action_table_action',
                        'class': 'oe_kanban_action',
                        'context': {
                            'action_model': cell['action'].get('model') or self.query_1_config_model_id.model,
                            'action_domain': cell['action'].get('domain') or [],
                            'action_name': cell['action'].get('name'),
                            'dashboard_widget_id': self.id,
                        }
                    } if cell.get('action') else False,
                } for icell, cell in enumerate(row['cells'])] for irow, row in enumerate(table_data.get('rows', []))],
            }
        else:
            if not self.query_1_config_model_id:
                render_data['error'] = "Please set a record type by editing this dashboard item"
            data = self.chart_get_data_query_1()
            if not data[0]:
                render_data['table'] = {
                    'record': self,
                    'headers': [{'name': ''}],
                    'rows': [[{'value': 'No results', 'display_value': 'No Results', 'class': ''}]],
                }
                return render_data

            total_row = [sum(map(lambda ds: ds['data'][col], data[0]['datasets'])) for col in range(len(data[0]['datasets'][0]['data']))]
            total = sum([sum(ds['data']) for ds in data[0]['datasets']])

            def _get_action(row, row_index, d, d_index):
                domain = row['domains'][d_index]
                if domain:
                    domain = json.dumps(domain, default=self._dashboard_json_converter)
                label = data[0]['labels'][d_index]
                return {
                      'type': 'object',
                      'name': 'action_table_action',
                      'class': 'oe_kanban_action',
                      'context': {
                          'action_model': self.query_1_config_model_id.model,
                          'action_domain': domain or [],
                          'action_name': label,
                          'dashboard_widget_id': self.id,
                      }
                  }

            render_data['table'] = {
                'record': self,
                'headers':
                    [{'name': ''}] +
                    [{'name': label} for label in data[0]['labels']] +
                    [{'name': 'Total'}],
                'rows':
                    # Data Row
                    [
                        # Header Column
                        [{'value': row['label'], 'display_value': self.human_format_value(row['label'], heading=True), 'class': 'active bold'}] +
                        # Data Column
                        [{'value': d, 'display_value': self.human_format_value(d), 'action': _get_action(row, row_index, d, d_index)} for d_index, d in enumerate(row['data'])] +
                        # Total Column
                        [{'value': sum(row['data']), 'display_value': self.human_format_value(sum(row['data'])), 'type': 'header', 'class': 'active bold'}]
                            for row_index, row in enumerate(data[0]['datasets'])
                    ] +
                    # Total Row
                    [
                        # Header Column
                        [{'value': 'Total', 'display_value': self.human_format_value("Total", heading=True), 'class': 'active bold'}] +
                        # Data Column
                        [{'value': total_row, 'display_value': self.human_format_value(v), 'class': 'active bold'} for v in total_row] +
                        # Total Column
                        [{'value': total, 'display_value': self.human_format_value(total), 'class': 'active bold'}]
                    ],
            }

        return render_data

    def human_format_value(self, value, heading=False):
        table_display_value_prefix = '' if heading else (self.table_display_value_prefix or '')
        if isinstance(value, int) or isinstance(value, float):
            dp = 1
            hide_zeros = True

            if abs(value) >= 1000000:
                res = "{}{:,}m".format(table_display_value_prefix, round(value / 1000000.0, dp))
            elif abs(value) >= 1000:
                res = "{}{:,}k".format(table_display_value_prefix, round(value / 1000.0, dp))
            elif abs(value) > 0 or not hide_zeros:
                res = "{}{:,}".format(table_display_value_prefix, round(value, dp))
            else:
                res = ""
        else:
            res = u"{}{}".format(table_display_value_prefix, value)

        if not heading and table_display_value_prefix:
            res = res.replace(
                '{}-'.format(table_display_value_prefix),
                '-{}'.format(table_display_value_prefix),
            )
        return res
