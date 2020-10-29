odoo.define('is_dashboard_widgets.dashboards', function (require) {
'use strict';

var IS_ODOO_VERSION_AFTER_v10 = true;
var IS_ODOO_VERSION_BEFORE_v12 = false;

var AbstractField = require('web.AbstractField');
var core = require('web.core');
var registry = require('web.field_registry');
var Dialog = require('web.Dialog');

var _t = core._t;
var qweb = core.qweb;
var pyUtils = require('web.py_utils');

var FieldMany2ManyDashboards = AbstractField.extend({
    tag_template: "FieldMany2ManyDashboard",
    className: "o_field_many2many_dashboards",
    supportedFieldTypes: ['many2many'],
    fieldsToFetch: {
        display_name: {type: 'char'},
        id: {type: 'integer'},
        size_x: {type: 'integer'},
        size_y: {type: 'integer'},
        pos_x: {type: 'integer'},
        pos_y: {type: 'integer'},
        background_color: {type: 'char'},
        display_allow_scrolling: {type: 'boolean'},
        play_sound_on_change_down: {type: 'boolean'},
        play_sound_on_change_down_url: {type: 'char'},
        play_sound_on_change_up: {type: 'boolean'},
        play_sound_on_change_up_url: {type: 'char'},
        is_template: {type: 'boolean'},
    },
    events: {
        'click .click-select-template-copy': '_selectRecord_copy',
        'click .click-select-template-link': '_selectRecord_link',
        'click .click-open-record': '_openRecord',
        'click .click-copy-record': '_copyRecord',
        'click .click-remove-record': '_removeRecord',
        'click .oe_kanban_action': '_onDashboardActionClicked',
        'change .date_range_type_selection': '_onchange_date_range_type_selection',
    },
    limit: 1000,

    init: function () {
        this._super.apply(this, arguments);

        // avoid quick multiple clicks
        this._onDashboardActionClicked = _.debounce(this._onDashboardActionClicked, 300, true);

        // FIX for odoo commit which effects '{ viewType: view.type }' in case 'UPDATE' of  _applyX2ManyChange
        // since it now breaks if there is now view set
        //    https://github.com/odoo/odoo/commit/f894b6a1d88f8ac946bc3481668e6556f72e83c0
        this.attrs.mode = 'kanban_dashboards';
        this.attrs.views = {
            kanban_dashboards: {
                'type': 'list',
                'fieldsInfo': {
                    'list': this.fieldsToFetch,
                },
                'fields': this.fieldsToFetch,
            },
        };

    },

    isSet: function () {
        if(this.getParent().state.data.preview_data){
            var preview_data = JSON.parse(this.getParent().state.data.preview_data);
            this.render_tiles(false, preview_data);
        }
        else if (this.attrs && this.attrs.context && this.attrs.context.indexOf('template_mode')) {
            this.grid.destroy();
            this.start_gridstack();
            this.render_tiles(false);
        }
        return true; // it should always be displayed, whatever its value
    },

    _onchange_date_range_type_selection: function(ev){
        var self = this;
        this._rpc({
            model: 'is.dashboard',
            method: "update_date_range",
            args: [[this.record.data.id], ev.target.value],
        }).then(function(result){
            // self.render_tiles(true);
            self.trigger_up('reload');
        });
    },

    gridstack_onchange: function(field, event, items){
        _.each(items, function (item) {
            var rowID = item.el.data('id');
            var data = {
                'pos_x': item.x,
                'pos_y': item.y,
                'size_x': item.width,
                'size_y': item.height,
            };
            var context = _.find(field.value.data, function(el){return el.id === rowID});
            if (context.data.pos_x !== data.pos_x ||
                context.data.pos_y !== data.pos_y ||
                context.data.size_x !== data.size_x ||
                context.data.size_y !== data.size_y
            ) {
                field._setValue({
                    operation: 'UPDATE',
                    id: rowID,
                    data: data
                });
                // _.assign(context.data, data);
            }
        });
    },

    start_gridstack: function(){
        var self = this;

        this.$el.html(qweb.render(this.tag_template, {'self': this}));

        var options = {
            cellHeight: 120,
            verticalMargin: 10,
        };

        if (this.mode === "readonly") {
            options.disableResize = true;
            options.disableDrag = true;
        }
        self.$grid = this.$el.find('.grid-stack');
        self.grid = self.$grid.gridstack(options).data('gridstack');

        self.$grid.on('change', function(event, items) {
            self.gridstack_onchange(self, event, items);
        });
    },

    _render_tile_preview_on_save: function(record, tile){
        var preview_data = JSON.parse(tile.data.preview_data);
        var $tile = record.$grid.find('div[data-dashboard-content-id="' + tile.data.id + '"]');
        record._render_gridstack_item($tile, tile, false, preview_data);
    },

    _render_gridstack_item: function($tile, tile, update_only, preview_data){
        if (preview_data){
            this._render_gridstack_item_internal(this, $tile, tile, preview_data, update_only);
            return;
        }
        // TODO: Debounce/throttle?
        var self = this;
        $.ajax({
            dataType: "json",
            data: JSON.stringify({widget_id: tile.data.id, dashboard_id: self.record.res_id}),
            contentType: "application/json; charset=utf-8",
            url: '/dashboard/render_data/',
            type: 'post',
            context: {field: this, $tile: $tile, tile: tile},
            success: function (data) {
                self._render_gridstack_item_internal(this.field, $tile, tile, data['result'], update_only)
                this.field.play_sound_if_changed(this.field, $tile, tile, data);
            }
        });
    },
    _render_gridstack_item_internal: function(field, $tile, tile, data, update_only){
        if (data['render_type'] === 'chart') {
            field._render_chart(field, $tile, tile.data.id, data['data'], tile, update_only);
        } else if (data['render_type'] === 'html') {
            $($tile).html(data['data']);
        }
    },

    _render: function () {
        var res =  this._super.apply(this, arguments);
        var self = this;
        if (this.$grid === undefined) {
            this.start_gridstack();
        }
        window.auto_refresh_render_id = Math.random(); // Track this render so that if render is called again all previous auto-refreshes will stop automatically
        this.render_tiles(false);

        // Setup auto refresh
        if (self.recordData.auto_refresh && self.mode !== 'edit') {
            setTimeout(function(){self.auto_refresh(self, window.auto_refresh_render_id);}, self.recordData.auto_refresh * 1000);
        }

        return res;
    },

    render_tiles: function(update_only, preview_data){
        var self = this;
        var itile;
        for (itile = 0; itile < self.value.data.length; itile++){
            var tile = self.value.data[itile];
            var $tile = this.$grid.find('div[data-dashboard-content-id="' + tile.data.id + '"]');
            if ($tile.length && (update_only || preview_data || $tile.data('rendered') === undefined)) {
                $tile.data('rendered', true);
                self._render_gridstack_item($tile, tile, update_only, preview_data);
            }
        }
    },

    auto_refresh: function(field, auto_refresh_render_id){
        var self = this;
        if (self.mode !== 'edit') {
            if (field.recordData.auto_refresh_type === 'dashboard') {
                field.trigger_up('reload');
            }
            else if (window.auto_refresh_render_id === auto_refresh_render_id && field.recordData.auto_refresh_type === 'data')  {
                field.render_tiles(true);
                setTimeout(function(){self.auto_refresh(field, auto_refresh_render_id);}, self.recordData.auto_refresh * 1000);
            }
        }
    },

    _open_chart_action: function (data, ds, action, activePoint) {
        if (action !== undefined){
            // need to add views if not defined
            if (!('views' in action)) {
                action['views'] = [[false, 'list'], [false, 'form']];
            }

            var label = data.data['labels'][activePoint._index];
            if (data.data.datasets.length > 1){
                var ds_label = ds['label'];
                action['name'] = ds_label + ": " + label;
            } else {
                action['name'] = label;
            }

            // open the action
            this.do_action(action, {'segment_selected': 1});
        }
    },
    _render_chart: function(field, self, dashboard_id, data, tile, update_only){
        data = JSON.parse(data);
        if (update_only && tile.chart){
            $.extend(true, tile.chart.data, data.data);
            tile.chart.update();
            return;
        }
        var ctx = $(self).html('<canvas/>').find('canvas')[0].getContext('2d');

        var datalabels_display = !!(data && data['show_values_on_graph'] === true);
        var hide_gridlines = !!(data && ['radar', 'pie'].includes(data['type']));
        var value_prefix_symbol = (this.data && this.data['value_prefix_symbol']);
        // bar graphs handled the default anchor point poorly so move it to the top.
        var datalabels_anchor = (data && data['type'] === 'bar') ? 'end' : 'center';

        var chart_data = $.extend(true, {}, data, {
            options: {
                maintainAspectRatio: false,
                onClick: function(ev, el) {
                    ev.stopPropagation();

                    if (field.mode === 'edit'){
                        return;
                    }

                    var activePoint = tile.chart.getElementAtEvent(ev)[0];
                    if (! activePoint || !activePoint._chart){
                        return;
                    }
                    var _data = activePoint._chart.data;
                    var datasetIndex = activePoint._datasetIndex;
                    var ds = _data.datasets[datasetIndex];
                    if (!ds['model']){
                        return;
                    }
                    var open_data = {
                        data_model: ds['model'],
                        data_action: ds['action_id'],
                        data_domain: ds['domains'][activePoint._index]
                    };

                    var call;
                    if (IS_ODOO_VERSION_AFTER_v10){
                        call = field._rpc({
                            model: 'is.dashboard.widget',
                            method: 'action_open_data_segment',
                            args: [[dashboard_id], open_data]
                        });
                    } else {
                        console.log('MIG: charts not back-ported to v10 with many2many_dashboard widget');
                        debugger; //TODO: Migrate to v10
                        //call = new Model('is.dashboard.widget').call('action_open_data_segment', [[dashboard_id], open_data]);
                    }

                    call.then(function(action){
                        field._open_chart_action(data, ds, action, activePoint);
                    })
                },
                scales: {
                    xAxes: [{
                        display: !hide_gridlines,
                        gridLines: {
                            color: (hide_gridlines) ? "transparent" : Chart.defaults.scale.gridLines.color,
                            zeroLineColor: (hide_gridlines) ? "transparent" : Chart.defaults.scale.gridLines.zeroLineColor,
                        }
                    }],
                    yAxes: [
                        {
                            display: !hide_gridlines,
                            gridLines: {
                                color: (hide_gridlines) ? "transparent" : Chart.defaults.scale.gridLines.color,
                                zeroLineColor: (hide_gridlines) ? "transparent" : Chart.defaults.scale.gridLines.zeroLineColor,
                            },
                            ticks: {
                                callback: function(label, index, labels) {
                                    var _label = label;
                                    if (Math.abs(label) >= 1000000) {
                                        _label = label/1000000+'m';
                                    }
                                    else if (Math.abs(label) >= 1000) {
                                        _label = label/1000+'k';
                                    }
                                    else {
                                        _label = label;
                                    }

                                    if (value_prefix_symbol){
                                        _label = value_prefix_symbol + _label;
                                        _label = _label.replace(value_prefix_symbol + "-", "-" + value_prefix_symbol)
                                    }

                                    return _label;
                                }
                            }
                        }
                    ]
                },
                plugins: {
                    colorschemes: {
                        scheme: 'brewer.Paired12'
                    },
                    datalabels: {
                        color: 'black',
                        display: function(context){
                            return datalabels_display && context.dataset.data[context.dataIndex];
                        },
                        anchor: datalabels_anchor,
                        formatter: function(value, context) {
                            var label = '';

                            if (isNaN(value)) {
                                label += value;
                            } else {
                                label += value.toLocaleString('en');
                            }

                            if (value_prefix_symbol) {
                                label = value_prefix_symbol + label
                            }
                            return label;
                        }
                    },
                },
                emptyOverlay:{
                    fillStyle: 'rgba(255,255,255,0.5)',
                },
                tooltips: {
                    callbacks: {
                        label: function (tooltipItem, _data) {
                            //use default tooltip on pie chart
                            if (this._chart.config.type === 'pie') {
                                return Chart.defaults.pie.tooltips.callbacks.label(tooltipItem, _data);
                            }
                            var ds = _data.datasets[tooltipItem.datasetIndex];
                            var label = ds.label || '';
                            if (label) {
                                label += ': ';
                            }
                            if (value_prefix_symbol){
                                label += value_prefix_symbol;
                            }
                            if (isNaN(tooltipItem.yLabel)) {
                                label += tooltipItem.yLabel;
                            } else {
                                label += tooltipItem.yLabel.toLocaleString('en');
                            }

                            if (value_prefix_symbol) {
                                label = label.replace(value_prefix_symbol + "-", "-" + value_prefix_symbol)
                            }
                            return label;
                        }
                    },
                },
            },
        });

        tile.chart = new Chart(ctx, chart_data);
    },
    _openRecord: function (event) {
        event.preventDefault();
        event.stopPropagation();
        var self = this;
        this.trigger_up('open_record', {
            id: event.target.getAttribute('data-id'),
            mode: 'edit',
            string: 'Dashboard Tile',
            on_saved: function (tile) {
                self._render_tile_preview_on_save(self, tile);
            },
        });
    },

    _removeRecord: function (event) {
        event.preventDefault();
        event.stopPropagation();
        var self = this;

        Dialog.confirm(this, _t("Do you really want to delete this dashboard item?"), {
            confirm_callback: function () {
                var id = event.target.getAttribute('data-id');
                var $grid_item = self.$grid.find('div[data-id="' + id + '"]');
                self._setValue({operation: 'FORGET', ids: [id]});
                self.grid.removeWidget($grid_item);
            },
        });
    },

    _selectRecord_copy: function(event){
        event.preventDefault();
        var self = this;
        var $action = $(event.currentTarget);
        var data = $action.data();
        var available_widget_filter_template_category_id = _.filter(this.getParent().getChildren(), function(f) { return f.name === 'add_widget_id'; });
        if (available_widget_filter_template_category_id) {
            available_widget_filter_template_category_id[0]._setValue(data.recordId).then(function(){
                self.trigger_up('do_action', {'action': {'type': 'ir.actions.act_window_close'}})
            });
        }
    },

    _selectRecord_link: function(event){
        event.preventDefault();
        var self = this;
        var $action = $(event.currentTarget);
        var data = $action.data();
        var available_widget_filter_template_category_id = _.filter(this.getParent().getChildren(), function(f) { return f.name === 'add_widget_link_id'; });
        if (available_widget_filter_template_category_id) {
            available_widget_filter_template_category_id[0]._setValue(data.recordId).then(function(){
                self.trigger_up('do_action', {'action': {'type': 'ir.actions.act_window_close'}})
            });
        }
    },

    _onDashboardActionClicked: function (event) {
        event.preventDefault();
        var self = this;

        if (this.mode === 'edit'){
            return;
        }

        var $action = $(event.currentTarget);
        var data = $action.data();
        var context = pyUtils.eval('context', data.context, {});

        var action_name = 'action_open_data';
        if (data.action_name) {
            action_name = data.action_name;
        }

        this._rpc({
            model: 'is.dashboard',
            method: action_name,
            args: [[this.record.data.id]],
            context: context,
        }).then(function(action){
            self.do_action(action);
        });

    },

    // Play sounds on change
    play_sound_if_changed: function(self, $tile, tile, data){
        if (tile.data.play_sound_on_change_down || tile.data.play_sound_on_change_up){
            var current_value = data.result.additional_data.current_value;
            var last_value = self.get_last_value(tile);
            if (last_value === undefined || last_value === null){
                self.set_last_value(tile, current_value);
            } else {
                self.set_last_value(tile, current_value);
                if (tile.data.play_sound_on_change_down && current_value < last_value){
                    self.play_sound(tile.data.play_sound_on_change_down_url);
                } else if (tile.data.play_sound_on_change_up && current_value > last_value){
                    self.play_sound(tile.data.play_sound_on_change_up_url);
                }
            }
        }
    },
    get_last_value: function(tile){
        return localStorage.getItem('widget-' + tile.data.id);
    },
    set_last_value: function(tile, value){
        localStorage.setItem('widget-' + tile.data.id, value);

    },
    play_sound: function(file_url){
        var x = document.createElement("AUDIO");
        x.setAttribute('autoplay', 'autoplay')
        x.setAttribute('src', file_url);
        x.play();
    },
});

registry.add('many2many_dashboards', FieldMany2ManyDashboards);
});
