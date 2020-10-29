from odoo import api, fields, models

from odoo import api, fields, models


class DashboardWidget(models.Model):
    _inherit = 'is.dashboard.widget'

    template_category_id = fields.Many2one('is.dashboard.template.category', string="Template Category", default=lambda self: self.env.ref('dashboard_widgets.dashboard_template_category_user', raise_if_not_found=False), copy=False)
    copied_from_template_id = fields.Many2one("is.dashboard.widget", string="Copied from template")
    is_template = fields.Boolean(compute="_compute_is_template")

    def _compute_is_template(self):
        for rec in self:
            rec.is_template = not rec.template_category_id.is_existing_item_category


class IsDashboardTemplateCategory(models.Model):
    _name = 'is.dashboard.template.category'
    _description = "Dashboard Template Category"
    _order = "sequence"

    name = fields.Char()
    sequence = fields.Integer()
    is_existing_item_category = fields.Boolean()
