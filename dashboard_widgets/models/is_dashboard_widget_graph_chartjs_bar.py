from odoo import api, fields, models

from collections import OrderedDict


class DashboardWidgetGraph(models.Model):
    _inherit = 'is.dashboard.widget'

    graph_1_bar_stacked = fields.Boolean("Stack Bar Chart (1)")

    def update_dashboard_data_ds(self, data, datasets, color, area, title):
        super(DashboardWidgetGraph, self).update_dashboard_data_ds(data, datasets, color, area, title)
        if datasets and self.graph_type == 'bar':
            for ds in datasets:
                if 'fill' not in ds:
                    ds['fill'] = area
                if color:
                    ds['borderColor'] = color
                    ds['backgroundColor'] = color
                if 'stack' not in ds and self.graph_1_bar_stacked:
                    ds['stack'] = title

    def get_dashboard_data_add_ds(self, data, chart_datasets, data1, data2):
        if self.graph_type == 'bar' and data1:
            if self.query_1_config_enable_goal and data1['dates']:
                ds = self.get_dataset_for_goal_1(data1['dates'], data1['labels'])

                if self.graph_1_bar_stacked:
                    ds['stack'] = 'Stack 1'

                if self.chart_1_goal_config_color:
                    ds['borderColor'] = self.chart_1_goal_config_color
                    ds['backgroundColor'] = self.chart_1_goal_config_color

                chart_datasets.append(ds)

        return super(DashboardWidgetGraph, self).get_dashboard_data_add_ds(data, chart_datasets, data1, data2)

    def get_dashboard_data(self):
        data = super(DashboardWidgetGraph, self).get_dashboard_data()

        if data and self.display_mode == 'graph' and self.graph_type == 'bar':
            if self.graph_1_bar_stacked:
                data['options']['scales'] = {
                    'xAxes': [{
                        'stacked': True,
                    }],
                    'yAxes': [{
                        'stacked': True
                    }]
                }
                for ds in data['data']['datasets']:
                    if 'stack' not in ds:
                        ds['stack'] = 'Stack 0'
        return data
