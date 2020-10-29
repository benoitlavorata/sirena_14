from odoo import api, fields, models


class DashboardWidget(models.Model):
    _inherit = 'is.dashboard.widget'

    display_mode = fields.Selection(selection_add=[
        ("embed_html", "Embed HTML"),
        ("embed_iframe_html", "Embed HTML (iframe)"),
        ("embed_iframe_url", "Embed URL (iframe)"),
    ], ondelete={
        'embed_html': 'set default',
        'embed_iframe_html': 'set default',
        'embed_iframe_url': 'set default',
    })

    html = fields.Text(string="Embedded Content HTML")
    iframe_url = fields.Char(string="Embedded Content URL")

    def get_render_data(self):
        render_data = super(DashboardWidget, self).get_render_data()

        if self.display_mode == 'embed_html':
            render_data['html'] = self.html
        elif self.display_mode == 'embed_iframe_html':
            render_data['iframe_url'] = '/dashboard/html/{}'.format(self.id)
        elif self.display_mode == 'embed_iframe_url':
            render_data['iframe_url'] = self.iframe_url
        return render_data
