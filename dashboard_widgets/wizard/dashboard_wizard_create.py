from odoo import api, fields, models


class DashboardWizardCreate(models.TransientModel):
    _name = 'is.dashboard.widget.wizard.create'
    _description = 'Dashboard Create Wizard'

    name = fields.Char(string="Name", required=True)
    menu_id = fields.Many2one(comodel_name='ir.ui.menu', string="Parent Menu")
    group_ids = fields.Many2many(comodel_name='res.groups', string="Allowed Groups")

    def action_create(self):
        self.env['is.dashboard'].create({'menu_id': self.menu_id.id, 'name': self.name, 'group_ids': self.group_ids.ids})
        return {
            'type': 'ir.actions.client',
            'tag': 'reload',
        }
