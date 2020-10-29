ODOO_VERSION_IS_v11 = False
from odoo import api, fields, models
from .date_ranges import DATE_RANGE_TYPES, SINGLE_DATE_RANGE_OPERATORS


class Dashboard(models.Model):
    _name = 'is.dashboard'
    _description = "Dashboard"

    name = fields.Char(string="Name", required=True)
    widget_ids = fields.Many2many(comodel_name='is.dashboard.widget', relation='is_dashboard_widget_position', column1='dashboard_id', column2='widget_id', string="Widgets")
    menu_id = fields.Many2one(comodel_name='ir.ui.menu', string="Menu")
    auto_refresh = fields.Integer(string="Auto Refresh", default=0, help="Auto-refresh in seconds. Set to 0 to disable")
    auto_refresh_type = fields.Selection(selection=[
        # ('data', "Data Only"),
        ('dashboard', "Entire Dashboard"),
    ], default='dashboard')  # TODO: Change default to data

    # TODO: Imp groups
    group_ids = fields.Many2many(comodel_name='res.groups', string="Allowed Groups")

    show_date_range = fields.Boolean(compute="compute_show_date_range")
    date_range_type = fields.Selection(selection=[
        a for a in DATE_RANGE_TYPES if
        a[0] != 'dashboard' and '_x_' not in a[0] and 'goal' not in a[0] and 'custom' not in a[0]
    ], compute="_compute_date_range_type")
    date_single_range_operator = fields.Selection(selection=SINGLE_DATE_RANGE_OPERATORS, default='=')
    date_range_x = fields.Integer(default=0)


    def compute_show_date_range(self):
        for rec in self:
            rec.show_date_range = any(rec.widget_ids.filtered(lambda a: a.query_1_config_date_range_type == 'dashboard' or a.query_2_config_date_range_type == 'dashboard'))

    def _compute_date_range_type(self):
        for rec in self:
            data = self.env['is.dashboard.user_data'].sudo().search([
                ('dashboard_id', '=', self.id),
                ('user_id', '=', self.env.user.id),
            ], limit=1)
            rec.date_range_type = data.date_range_type

    def update_date_range(self, date_range_type):
        Data = self.env['is.dashboard.user_data'].sudo()
        data = Data.search([
            ('dashboard_id', '=', self.id),
            ('user_id', '=', self.env.user.id),
        ], limit=1)
        if not data:
            Data.create({
                'dashboard_id': self.id,
                'user_id': self.env.user.id,
                'date_range_type': date_range_type,
            })
        else:
            data.update({
                'date_range_type': date_range_type,
            })

    @api.model
    def create(self, vals):
        res = super(Dashboard, self).create(vals)

        # Create a unique action to allow refreshing without losing any context
        action = self.env.ref('dashboard_widgets.is_dashboard_form_action').copy({'name': res.name, 'res_id': res.id, 'context': {'dashboard_id': res.id}})

        res.menu_id = self.env['ir.ui.menu'].create({
            'name': res.name,
            'parent_id': res.menu_id.id,
            'action': 'ir.actions.act_window,{}'.format(action.id),
            'groups_id': [(6, 0, vals.get('group_ids'))] if vals.get('group_ids') else False
        })
        return res

    def write(self, vals):
        # Keep menu item name in sync with dashboard name.
        name = vals.get('name')
        if name:
            self.mapped('menu_id').write({'name': name})
            self.env['ir.ui.menu'].invalidate_cache()

        # If updating widget_ids, strip out all of the updates, run them in one write and do all other changes during super.
        if 'widget_ids' in vals and any(val[0] == 1 for val in vals['widget_ids']):
            update_data = {}
            for val in vals['widget_ids']:
                if val[0] == 1:
                    id = val[1]
                    if id not in update_data:
                        update_data[id] = {}
                    update_data[id].update(val[2])
            for id in update_data:
                    self.env['is.dashboard.widget.position'].search([('widget_id', '=', id), ('dashboard_id', '=', self.id)]).write(update_data[id])

            if ODOO_VERSION_IS_v11:
                # V11 does a 6 command to set the list of widgets to the current screen.
                #  This deletes the db rows and recreates them all which removes all the saved pos/size data.
                #  Instead, just delete any lines that are actually deleted
                del_cmd = [val for val in vals['widget_ids'] if val[0] == 6]
                extra_vals = []
                if len(del_cmd) == 1:
                    for rec in self:
                        to_del = set(self.widget_ids.ids) - set(del_cmd[0][2])
                        if to_del:
                            # Replace 6 command with our own
                            extra_vals = [(3, to_del_id, False) for to_del_id in to_del]
                vals['widget_ids'] = extra_vals + [val for val in vals['widget_ids'] if val[0] != 6]
            else:
                vals['widget_ids'] = [val for val in vals['widget_ids'] if val[0] != 1]
        return super(Dashboard, self).write(vals)

    def unlink(self):
        # Cleanup created records
        for rec in self:
            if rec.menu_id.action:
                rec.menu_id.action.unlink()
            rec.menu_id.unlink()
        return super(Dashboard, self).unlink()


    @api.model
    def add_widget(self, dashboard_id,  widget_id, default_size_x=3, default_size_y=2, default_size_auto=False):
        Position = self.env['is.dashboard.widget.position']

        if default_size_auto:
            widget = self.env['is.dashboard.widget'].browse(widget_id)
            widget_type = self.env['is.dashboard.widget.type'].search([('type', '=', widget.display_mode)], limit=1)
            if widget_type:
                default_size_x = widget_type.default_size_x
                default_size_y = widget_type.default_size_y

        # Find a blank space for a new 3x3 tile to go.
        pos_x = 0
        pos_y = 0

        # Get a list of all currently occupied spaces
        grid = []
        positions = Position.search([('dashboard_id', '=', dashboard_id)])
        for position in positions:
            x = position.pos_x
            y = position.pos_y
            for dx in range(position.size_x):
                for dy in range(position.size_y):
                    grid.append((x + dx, y + dy),)

        def test_pos(x, y):
            for dy in range(3):
                for dx in range(3):
                    if (x + dx, y + dy) in grid:
                        return False
            return True

        while True:
            if test_pos(pos_x, pos_y):
                break
            pos_x += 1
            if pos_x == 10:
                pos_x = 0
                pos_y += 1

        # Create new position
        Position.create({
            'dashboard_id': dashboard_id,
            'widget_id': widget_id,
            'pos_x': pos_x,
            'pos_y': pos_y,
            'size_x': default_size_x,
            'size_y': default_size_y,
        })

    def action_refresh(self):
        pass  # Do nothing for a refresh

    def action_open_settings(self):
        view = self.env.ref('dashboard_widgets.is_dashboard_form_settings_view')
        return {
            'name': 'Dashboard Settings',
            'type': 'ir.actions.act_window',
            'view_type': 'form',
            'view_mode': 'form',
            'res_model': 'is.dashboard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': self.id,
        }

    def action_add_item(self):
        view = self.env.ref('dashboard_widgets.is_dashboard_form_add_item_view')
        return {
            'name': 'Add to dashboard',
            'type': 'ir.actions.act_window',
            'view_mode': 'form',
            'res_model': 'is.dashboard',
            'views': [(view.id, 'form')],
            'view_id': view.id,
            'target': 'new',
            'res_id': self.id,
            'context': {
                'template_mode': True,
            }
        }
