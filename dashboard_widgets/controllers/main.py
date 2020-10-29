import odoo.http as http
from odoo.http import request


class DashboadWidgetsHelper(http.Controller):

    @http.route('/dashboard/html/<int:widget_id>', type='http', auth='user', website=True)
    def dashboard_widget_html(self, widget_id, **kwargs):
        widget = request.env['is.dashboard.widget'].browse(widget_id).exists()
        if not widget:
            widget = request.env['is.dashboard.widget.preview'].browse(widget_id).exists()
        if widget and widget.html:
            return widget.html
        else:
            return 'Please save record first to preview'

    @http.route('/dashboard/render_data', type='json', auth='user', methods=['POST'], website=False)
    def dashboard_render_data(self, **kwargs):
        widget_id = request.jsonrequest.get('widget_id')
        dashboard_id = request.jsonrequest.get('dashboard_id')
        widget = request.env['is.dashboard.widget'].browse(widget_id).exists().with_context(dashboard_id=dashboard_id)
        return self._dashboard_render_data(widget)

    def _dashboard_render_data(self, widget):
        additional_data = {}

        if widget.display_mode == 'graph':
            render_type = 'chart'
            data = widget.dashboard_data
        else:
            render_type = 'html'
            data = widget.render_dashboard_markup

        if widget.display_mode == 'card' and (widget.play_sound_on_change_up or widget.play_sound_on_change_down):
            additional_data['current_value'] = widget.count

        return {
            'render_type': render_type,
            'data': data,
            'additional_data': additional_data,
        }
