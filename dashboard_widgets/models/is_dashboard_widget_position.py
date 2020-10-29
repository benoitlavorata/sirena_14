from odoo import api, fields, models


class IsDashboardWidgetPosition(models.Model):
    _name = 'is.dashboard.widget.position'
    _description = "Dashboard Position"

    dashboard_id = fields.Many2one(comodel_name='is.dashboard', string="Dashboard", required=True, ondelete='cascade')
    widget_id = fields.Many2one(comodel_name='is.dashboard.widget', string="Tile", required=True, ondelete='cascade')

    pos_x = fields.Integer(string="Position X")
    pos_y = fields.Integer(string="Position Y")

    size_x = fields.Integer(string="Size X", default=3)
    size_y = fields.Integer(string="Size Y", default=3)

    def init(self):
        super(IsDashboardWidgetPosition, self).init()
        self._cr.execute("ALTER TABLE is_dashboard_widget_position ADD COLUMN IF NOT EXISTS id SERIAL")

    @api.constrains('size_x', 'size_y')
    def _check_sizes(self):
        for rec in self:
            # Size Y must be at least 1
            if rec.size_y < 1:
                rec.size_y = 1

            # Size X is constrained by the 12 columns of the grid
            if rec.size_x < 1:
                rec.size_x = 1
            if rec.size_x > 12:
                rec.size_x = 12
