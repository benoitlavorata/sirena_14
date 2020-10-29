odoo.define('dashboard_widgets.field_widgets', function (require) {
    var relational_fields = require('web.relational_fields');
    var registry = require('web.field_registry');
    var dashboard_widgets_type_widget = relational_fields.FieldMany2One.extend({
        supportedFieldTypes: ['many2one'],
        events: _.extend({}, relational_fields.FieldMany2One.prototype.events, {
            'click img': '_onClicked',
        }),
        willStart: function () {
            var self = this;
            this.widget_types = {};
            return this._super()
                .then(function () {
                    return self._rpc({
                        model: 'is.dashboard.widget.type',
                        method: "search_read"
                    }).then(function (values) {
                        self.widget_types = values;
                    });
                });
        },
        _render: function () {
            var self = this;
            this.$el.empty();
            var value = _.isObject(this.value) ? this.value.data.id : this.value;
            _.each(this.widget_types, function (val) {
                var $container = $('<div>').addClass('text-center');
                var $img = $('<img>')
                    .addClass('img img-fluid img-thumbnail ml16')
                    .attr('src', val.preview_image_url)
                    .data('type_id', val.id);
                $container.append($img);
                self.$el.append($container);
            });
        },
        _onClicked: function (event) {
            var self = this;
            var type_id = $(event.currentTarget).data('type_id')
            this._setValue(type_id).then(function(){
                self.trigger_up('do_action', {'action': {'type': 'ir.actions.act_window_close'}})
            });
        },
    });

    registry.add('dashboard_widgets_type_widget', dashboard_widgets_type_widget);
    return dashboard_widgets_type_widget;
});
