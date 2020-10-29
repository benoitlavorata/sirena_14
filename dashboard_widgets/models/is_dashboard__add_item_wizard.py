from odoo import api, fields, models


class Dashboard(models.Model):
    _inherit = 'is.dashboard'

    add_widget_id = fields.Many2one(comodel_name='is.dashboard.widget', string="Add Existing Item")
    add_widget_link_id = fields.Many2one(comodel_name='is.dashboard.widget', string="Link Existing Item")
    add_widget_type_id = fields.Many2one(comodel_name='is.dashboard.widget.type', string="Add New Dashboard Item")

    available_widget_filter_keywords = fields.Char()
    available_widget_filter_template_category_id = fields.Many2one('is.dashboard.template.category', string="Template Category")
    available_widget_ids = fields.Many2many(comodel_name='is.dashboard.widget', string="Available Items To Add", compute="compute_available_widget_ids")

    @api.depends(
        'available_widget_filter_template_category_id',
        'available_widget_filter_keywords',
        'widget_ids',
    )
    def compute_available_widget_ids(self):
        for rec in self:
            dom = [
                ('dashboard_ids', '!=', False),
                ('template_category_id', '=', rec.available_widget_filter_template_category_id.id),
            ]
            if rec.available_widget_filter_keywords:
                dom += [('name', 'ilike', rec.available_widget_filter_keywords)]
            template_items = self.env['is.dashboard.widget'].search(dom)
            rec.available_widget_ids = [(6, 0, template_items.ids)]

    def action_add_all_widget_templates(self):
        for rec in self:
            for template_widget in rec.available_widget_ids:
                widget = template_widget.copy(default={'copied_from_template_id': template_widget.id}).id
                rec.add_widget(rec.id, widget, default_size_auto=True)

    @api.onchange('add_widget_id')
    def _onchange_add_widget_id(self):
        if self.add_widget_id:
            widget = self.add_widget_id.copy(default={'copied_from_template_id': self.add_widget_id.id}).id

            self.add_widget(
                self._origin.id,
                widget,
                default_size_auto=True,
            )
            self.add_widget_id = False

    @api.onchange('add_widget_link_id')
    def _onchange_add_widget_link_id(self):
        if self.add_widget_link_id:
            self.add_widget(
                self._origin.id,
                self.add_widget_link_id.id,
                default_size_auto=True,
            )
            self.add_widget_link_id = False

    @api.onchange('add_widget_type_id')
    def onchange_add_widget_type_id(self):
        if self.add_widget_type_id:
            widget = self.env['is.dashboard.widget'].create({
                'name': self.add_widget_type_id.name,
                'display_mode': self.add_widget_type_id.type,
            }).id
            self.add_widget(
                self._origin.id,
                widget,
                default_size_x=self.add_widget_type_id.default_size_x,
                default_size_y=self.add_widget_type_id.default_size_y,
            )
