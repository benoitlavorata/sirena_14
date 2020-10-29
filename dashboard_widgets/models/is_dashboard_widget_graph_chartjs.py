IS_ODOO_v12_OR_LATER = True
IS_ODOO_VERSION_BEFORE_v11 = False

from odoo import api, fields, models
from collections import OrderedDict, Counter
if IS_ODOO_v12_OR_LATER:
    from odoo.tools.func import lazy
from .lib.OrderedSet import OrderedSet
import logging
_logger = logging.getLogger(__name__)


class DashboardWidgetGraph(models.Model):
    _inherit = 'is.dashboard.widget'

    query_1_config_accumulative = fields.Boolean(string="Accumulative Data", help="Data accumulates over the horizontal Axis")
    query_2_config_accumulative = fields.Boolean(string="Accumulative Data", help="Data accumulates over the horizontal Axis")

    def update_dashboard_data_ds(self, data, ds, color, area, title):
        pass

    def get_average_dataset(self, data, ds, color, area, title):
        def _avg(i):
            return sum(i) / len(i) if len(i) > 0 else 0
        ds_avg = [{
            'label': 'Average',
            'data': [(_avg(list(map(lambda d: d['data'][i], ds)))) for i in range(len(ds[0]['data']))],
        }]
        avg_color = "#000000"
        self.update_dashboard_data_ds(data, ds_avg, avg_color, area, title + " Average")
        return ds_avg

    def get_dashboard_data(self):
        if self.display_mode != 'graph':
            return super(DashboardWidgetGraph, self).get_dashboard_data()

        data1, color1, area1, title1 = self.chart_get_data_query_1()

        if self.query_1_config_accumulative and data1 and data1['datasets']:
            for set in data1['datasets']:
                total = 0
                for i,x in enumerate(set['data']):
                    total += x
                    set['data'][i] = total

        # TODO: Allow data2 set to work
        data2, color2, area2, title2 = self.chart_get_data_query_2()

        if self.query_2_config_accumulative and data2 and data2['datasets']:
            for set in data2['datasets']:
                total = 0
                for i,x in enumerate(set['data']):
                    total += x
                    set['data'][i] = total

        if not data1:
            return False

        self.update_dashboard_data_ds(data1, data1['datasets'], False, area1, title1)  # TODO: Add colour option back in

        data = {
            'type': self.graph_type or 'bar',
            'show_values_on_graph': self.show_values_on_graph,
            'data': data1,
            'options': {
                'scales': {
                    'yAxes': [{
                        'ticks': {
                        },
                    }],
                },
            },
            'value_prefix_symbol': self.chart_display_value_prefix,
        }

        if self.display_mode == 'graph' and self.graph_type not in ['pie', 'radar']:
            if self.use_suggested_min_y_axis:
                data['options']['scales']['yAxes'][0]['ticks']['suggestedMin'] = self.suggested_min_y_axis
            if self.use_suggested_max_y_axis:
                data['options']['scales']['yAxes'][0]['ticks']['suggestedMax'] = self.suggested_max_y_axis
            if self.use_decimal_precision_y_axis:
                data['options']['scales']['yAxes'][0]['ticks']['precision'] = self.decimal_precision_y_axis

        if self.chart_1_config_show_average_dataset:
            data['data']['datasets'] += self.get_average_dataset(data1, data1['datasets'], color1, area1, title1)


        if data2:
            self.update_dashboard_data_ds(data2, data2['datasets'], color2, area2, title2)
            self._merge_datasets(data, data2)

            if self.chart_2_config_show_average_dataset:
                data['data']['datasets'] += self.get_average_dataset(data2, data2['datasets'], color2, area2, title2)

        if data1 and data2:
            # Label each dataset if a name is specified
            for ds in data['data']['datasets']:
                if ds.get('query_name') and ds.get('query_name').strip() and ds['label'] != ds['query_name']:
                    ds['label'] = "{} ({})".format(ds['label'], ds['query_name'])

        self.get_dashboard_data_add_ds(data['data'], data['data']['datasets'], data1, data2)

        if len(data['data']['datasets']) == 1 and self.graph_type != 'pie':
            data['options']['legend'] = {
                'display': False,
            }

        return data

    def get_dashboard_data_add_ds(self, data, chart_datasets, data1, data2):
        pass  # To be implemented with each chart type

    def chart_get_data(self, dom, model, measure_field, groupby, show_empty_groups, action, title=False, orderby=False, orderby_default_sort_label=True, limit=False, sudo=False, query_name=False):
        if not model or not groupby:
            return False  # Not enough data to make a chart/graph

        if groupby:
            groupby = list(filter(lambda g: g[0], groupby))  # Remove any empty groups

        data = self.get_query_result(model, dom, measure_field, groupby=groupby, orderby=orderby, limit=limit, sudo=sudo)

        def get_groupby_domain_value(item):
            item = get_first_item_if_list(item)
            # Return the first value of the groupby field in the domain
            if item:
                dom = list(filter(lambda dom: dom[0] == groupby[0][0], item['__domain']))
                if dom:
                    field = dom[0][0]
                    value = dom[0][2]

                    value = get_string_for_field_selection_value(field, value) or value
                    return value

                # return list(filter(lambda dom: dom[0] == groupby[0][0], item['__domain']))[0][2] if list(filter(lambda dom: dom[0] == groupby[0][0], item['__domain'])) else False
            return False

        def get_first_item_if_list(item):
            if not IS_ODOO_VERSION_BEFORE_v11 and isinstance(item, filter):
                item = list(item)
            if not item:
                return False
            if isinstance(item, list):
                return item[0]
            return item

        def get_second_item_if_tuple(item):
            if not IS_ODOO_VERSION_BEFORE_v11 and isinstance(item, filter):
                item = list(item)
            if not item:
                return False
            if isinstance(item, tuple) and len(item) > 1:
                return item[1]
            return item

        def _get_label(item):
            if group_field not in item:
                return "Unknown"

            if isinstance(item[group_field], tuple) and len(item[group_field]) == 2:
                return item[group_field][1]
            elif group_field in item:
                if group_field in self.env[model.model]._fields:
                    field = self.env[model.model]._fields[group_field]
                    if field.type == 'selection':
                        l = [l[1] for l in field.selection if l[0] == item[group_field]]
                        if l:
                            return l[0]
                return get_string_for_field_selection_value(group_field, item[group_field]) or item[group_field]

        def get_string_for_field_selection_value(field_name, value):
            if field_name not in self.env[model.model]._fields:
                return False

            field = self.env[model.model]._fields[field_name]
            if field.type == 'selection':
                selections = field.args['selection'] if 'selection' in field.args else field.selection  # Make compatible with Odoo versions/Studio related fields
                l = [l[1] for l in selections if l[0] == value]
                if l:
                    return l[0]
            return False

        def first(iterable, condition=lambda x: True):
            """
            https://stackoverflow.com/questions/2361426/get-the-first-item-from-an-iterable-that-matches-a-condition/2361899

            Returns the first item in the `iterable` that
            satisfies the `condition`.

            If the condition is not given, returns the first item of
            the iterable.

            Raises `StopIteration` if no item satysfing the condition is found.

            >> first( (1,2,3), condition=lambda x: x % 2 == 0)
            2
            >> first(range(3, 100))
            3
            >> first( () )
            Traceback (most recent call last):
            ...
            StopIteration
            """

            return next(x for x in iterable if condition(x))

        if not data:
            return data
        if not len(groupby):
            return False
        if len(groupby) > 2:
            raise UserWarning("More than 2 group by fields is not supported")
        elif len(groupby) == 1:
            group_field = groupby[0][2]

            def _key_if_data_has_key(key):
                return key if data and key in data[0] else False

            value_field = _key_if_data_has_key(measure_field[0]) or _key_if_data_has_key(groupby[0][0] + "_count") or "__count"

            labels = list(map(lambda line: _get_label(line), data))
            values = list(map(lambda line: line.get(value_field, 0), data))
            domains = list(map(lambda line: line.get('__domain'), data))


            if groupby and groupby[0] and groupby[0][3] and groupby[0][3].ttype in ['datetime', 'date']:
                date_start = list(map(lambda line: get_groupby_domain_value(line), data))
            else:
                date_start = False

            datasets = [{
                'label': title,
                'data': list(values),
                'domains': list(domains),
                'date_start': list(date_start) if date_start else [],
                'action_id': action.id,
                'model': model.model,
                'query_name': query_name,
            }]

            return {
                'labels': list(map(lambda label: get_second_item_if_tuple(label), labels)),
                'dates': list(date_start) if date_start else [],
                'datasets': datasets,
            }

        elif len(groupby) == 2:
            group_field = groupby[0][2]
            group_field_obj = groupby[0][3]
            value_field = measure_field[0] or "__count"

            # If measure field is not in the results than just show the count
            if data and data[0] and value_field not in data[0]:
                value_field = "__count"

            # Get group values and sort by total value in each group (Odoo does not sort this way in read_group)

            # Sort by value if the group by is not
            # TODO: Allow multiple order by fields
            _orderby = orderby.replace(' DESC', '').replace(' ASC', '') if orderby else orderby
            if groupby[0][0] != _orderby:
                # Sort by value
                reverse = ' DESC' in orderby if orderby else False  # TODO: Handle this better
                group_values = set([d[group_field] for d in data])  # Get list of all the options in the group
                group_values = {g: sum([d[value_field] for d in data if d[group_field] == g]) for g in group_values}  # Create a dict of each option with the total value
                group_values = sorted(group_values, key=group_values.get, reverse=reverse)  # Sort by the total value and just keep the keys
            else:
                # Sort by order listed in search result data
                group_values = list(OrderedSet([d[group_field] for d in data]))
            group2_field = groupby[1][2]
            group2_field_obj = groupby[1][3]

            if any(group2_field not in d for d in data):
                return False
                # raise UserError("{} not found in  {}".format(
                #    group2_field,
                #    data,
                # ))
            group2_values = set([d[group2_field] for d in data])

            label_data_old = set(map(lambda item: (item[group_field], get_groupby_domain_value(item) or _get_label(item)), data))

            def first_group_data(group_value):
                return first(data, lambda i: i[group_field] == group_value)

            # Convert group_values into a dict with the value as the label
            label_data = [(g, get_groupby_domain_value(first_group_data(g) or _get_label(first_group_data(g)))) for g in group_values]

            if not orderby:
                # Get all labels in order by getting label/date-pair and sorting. If there is no date than sort by label name
                default_orderby_index = 1 if orderby_default_sort_label else 0  # Sort by value or label (eg. selection value or selection label)
                try:
                    label_data = sorted(label_data, key=lambda item: item[default_orderby_index] or '')
                except Exception as ex:
                    _logger.error("Dashboard chart sort error: {}".format(repr(ex)))

            labels = list(map(lambda item: item, label_data))

            if groupby and groupby[0] and groupby[0][3] and groupby[0][3].ttype in ['datetime', 'date']:
                dates = list(map(lambda item: item[1], label_data))
            else:
                dates = False

            datasets = []

            # Get the first non-false group2 value default value to use for sorting any false values
            _g = list(filter(lambda item: item, group2_values))
            group2_values_item_default_type = type(_g[0])()
            if isinstance(group2_values_item_default_type, tuple) and len(_g[0]) > 1:
                group2_values_item_default_type = list(_g)[0][1]
                if IS_ODOO_v12_OR_LATER and isinstance(group2_values_item_default_type, lazy):
                    group2_values_item_default_type = group2_values_item_default_type._value
                try:
                    group2_values_item_default_type = type(group2_values_item_default_type)()
                except Exception as ex:
                    _logger.error("Unable to get default group value for {} / {} from {}".format(
                        type(group2_values_item_default_type), repr(group2_values_item_default_type),
                        group2_values,
                    ))
                    raise ex

            group2_values = sorted(group2_values, key=lambda k: get_second_item_if_tuple(k) or group2_values_item_default_type)
            for group in group2_values:

                group_data = list(filter(lambda item: item[group2_field] == group and (show_empty_groups or item[value_field]), data))

                def get_group_data_for_label(label):
                    return list(filter(lambda line: line[group_field] == label, group_data))

                def get_value_from_data(item, key, default=False):
                    item = get_first_item_if_list(item)
                    if item:
                        return item.get(key, default)
                    return default

                values = [get_value_from_data(get_group_data_for_label(label[0]), value_field, default=0) for label in labels]
                date_start = [get_groupby_domain_value(get_group_data_for_label(label[0])) for label in labels]
                domains = [get_value_from_data(get_group_data_for_label(label[0]), '__domain') for label in labels]

                datasets.append({
                    'label': get_second_item_if_tuple(group),
                    'data': values,
                    'domains': domains,
                    'date_start': date_start,
                    'action_id': action.id,
                    'model': model.model,
                    'query_name': query_name,
                })

            if group_field_obj.ttype == 'selection':
                labels = list(map(lambda label: get_second_item_if_tuple(label[1]), labels))
            else:
                labels = list(map(lambda label: get_second_item_if_tuple(label[0]), labels))

            return {
                'labels': labels,
                'dates': list(dates) if dates else [],
                'datasets': datasets,
            }
