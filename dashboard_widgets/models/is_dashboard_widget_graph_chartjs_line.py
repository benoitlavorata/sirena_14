from odoo import api, fields, models

from collections import OrderedDict
from odoo.exceptions import UserError
from datetime import datetime, date
from dateutil.relativedelta import relativedelta
import pytz


class DashboardWidgetGraph(models.Model):
    _inherit = 'is.dashboard.widget'

    def get_dataset_for_goal_1(self, dates, labels=None):
        if dates:
            return {
                'label': self.chart_1_goal_config_title,
                'data': [self.get_1_goal_for_date(date, False, current_goal_value_only=True) if date else 0 for date in dates],
                'domains': False,
                'date_start': False,
                'action_id': False,
            }
        elif labels:
            return {
                'label': self.chart_1_goal_config_title,
                'data': [self.goal_count for label in labels],
                'domains': False,
                'date_start': False,
                'action_id': False,
            }

    def _merge_datasets(self, data, ds):
        labels = data['data']['labels']
        new_labels = ds['labels']
        if labels != new_labels:
            self._add_render_dashboard_markup_error('_merge_datasets', "Data series labels must match to allow combining into a single chart")
        data['data']['datasets'] += ds['datasets']

    def update_dashboard_data_ds(self, data, datasets, color, area, title):
        super(DashboardWidgetGraph, self).update_dashboard_data_ds(data, datasets, color, area, title)
        if datasets and self.graph_type == 'line':
            for ds in datasets:
                if 'fill' not in ds:
                    ds['fill'] = area
                if color:
                    ds['pointColor'] = color
                    ds['pointBorderColor'] = color
                    ds['pointBackgroundColor'] = color
                    ds['borderColor'] = color
                    ds['backgroundColor'] = color

    def _update_list_of_date_datetime_objects_to_string_if_not_already(self, values):
        for i, value in enumerate(values):
            if isinstance(value, datetime):
                values[i] = fields.Datetime.to_string(value)
            elif isinstance(value, date):
                values[i] = fields.Date.to_string(value)

    def _update_list_of_string_date_or_datetime_to_object_if_not_already(self, values):
        type = False
        for i, value in enumerate(values):
            if not isinstance(value, date) and not isinstance(value, datetime):
                if value and '' in value:
                    values[i] = fields.Datetime.context_timestamp(self, fields.Datetime.from_string(value))
                    type = fields.Datetime
                else:
                    values[i] = fields.Date.from_string(value)
                    type = fields.Date
        return type

    def _get_string_date_type(self, values):
        if values and len(values) > 0:
            value = values[0]
            if not isinstance(value, date) and not isinstance(value, datetime):
                if value and '' in value:
                    return fields.Datetime
                else:
                    return fields.Date
        return False

    def convert_datetime_to_user_tz(self, d):
        if not d:
            return False
        tz_name = self._context.get('tz') or self.env.user.tz
        context_tz = pytz.timezone(tz_name)
        return context_tz.localize(d).astimezone(pytz.utc)


    def get_dashboard_data_add_ds(self, data, chart_datasets, data1, data2):
        # TODO: Very bad and ugly code that only works for very limited use-cases. Not ready for normal use
        if self.goal_1_show_future_goals:

            chart_dates = data['dates']
            type = self._get_string_date_type(chart_dates)
            chart_dates_obj = [fields.Datetime.from_string(d) if type == fields.Datetime else fields.Date.from_string(d) for d in chart_dates]
            max_chart_date = max(chart_dates_obj) if chart_dates_obj else (datetime.now() - relativedelta(months=1))
            if isinstance(max_chart_date, datetime):
                max_chart_date = fields.Date.from_string(fields.Date.context_today(self, max_chart_date.date()))

            goal_dates = self.goal_1_line_ids.filtered(lambda k: k.date and fields.Date.from_string(k.date) > max_chart_date).mapped(lambda l: l.date if type == fields.Date else fields.Datetime.to_string(self.convert_datetime_to_user_tz(fields.Datetime.from_string(l.date))))
            goal_dates = [d for d in goal_dates if d not in chart_dates]

            new_dates = sorted(set(goal_dates))
            obj_new_dates = [fields.Datetime.context_timestamp(self, fields.Datetime.from_string(d)) if type == fields.Datetime else fields.Date.from_string(d) for d in new_dates]

            data['dates'] += new_dates
            data['labels'] += [d.strftime("%B %Y") for d in obj_new_dates]

        if self.graph_type == 'line' and data1:
            if self.query_1_config_enable_goal and (data1['dates'] or self.goal_count):
                ds = self.get_dataset_for_goal_1(data1['dates'], data1['labels'])

                ds['fill'] = self.chart_1_goal_config_area

                if self.chart_1_goal_config_color:
                    ds['pointColor'] = self.chart_1_goal_config_color
                    ds['pointBorderColor'] = self.chart_1_goal_config_color
                    ds['pointBackgroundColor'] = self.chart_1_goal_config_color
                    ds['borderColor'] = self.chart_1_goal_config_color
                    ds['backgroundColor'] = self.chart_1_goal_config_color

                chart_datasets.append(ds)

        return super(DashboardWidgetGraph, self).get_dashboard_data_add_ds(data, chart_datasets, data1, data2)
