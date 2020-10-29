from odoo import api, SUPERUSER_ID, release
import re


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    env = api.Environment(cr, SUPERUSER_ID, {})
    pattern = re.compile("'tag_ids'.*?(\[[0-9, ]*?\])")  # List of tag ids
    pattern2 = re.compile("'tag_ids'.*?, ([0-9])")  # Single tag id
    actions = env['ir.actions.act_window'].search([
        ('res_model', '=', 'is.dashboard.widget'),
        ('domain', 'like', 'tag_ids'),
    ])

    for action in actions:
        name = action.name
        menu = env['ir.ui.menu'].search([('action', '=', 'ir.actions.act_window,{}'.format(action.id))], limit=1)
        parent = menu.parent_id

        if not parent:
            parent = menu  # RHP?
        elif not menu:
            parent = env.ref('dashboard_widgets.menu_dashboard')

        dashboard = env['is.dashboard'].create({'menu_id': parent.id, 'name': name, 'group_ids': False})

        match = pattern.search(action.domain)
        if not match:
            match = pattern2.search(action.domain)
        tags = False
        try:
            tags = eval(match.group(1))
            if isinstance(tags, int):
                tags = [tags]
        except:
            pass
        if not tags:
            continue
        items = env['is.dashboard.widget'].search([('tag_ids', 'in', tags)])

        line_items = []
        line_count = 1
        Position = env['is.dashboard.widget.position']
        for i, item in enumerate(items):
            # There are items and it is time for a new line, a line break, or we have run out or more items
            if len(line_items) and (len(line_items) >= 6 or item.display_mode == 'line_break' or i + 1 == len(items)):
                # add the items we have so for for this line
                size_x = int(12 / len(line_items))
                for line_item_i, line_item in enumerate(line_items):
                    line_item.background_color = get_color(line_item)
                    Position.create({
                        'dashboard_id': dashboard.id,
                        'widget_id': line_item.id,
                        'pos_x': size_x * line_item_i,
                        'pos_y': 2 * line_count,
                        'size_x': size_x,
                        'size_y': 2,
                    })
                line_items = []
                line_count += 1

            if item.display_mode != 'line_break':
                line_items += item

        # Delete menu/action if there is no external id for them
        if menu and not menu.get_external_id()[menu.id]:
            menu.unlink()
        if action and not action.get_external_id()[action.id]:
            action.unlink()

    # Delete line breaks as they are no longer an option
    env['is.dashboard.widget'].search([('display_mode', '=', 'line_break')]).unlink()


def get_color(item):
    if not item.color:
        return False
    elif item.color == 1:
        return "#fce0dd"
    elif item.color == 2:
        return "#fef6ef"
    elif item.color == 3:
        return "#fceeb3"
    elif item.color == 4:
        return "#f4fafe"
    elif item.color == 5:
        return "#c79cb4"
    elif item.color == 6:
        return "#ffffff"
    elif item.color == 7:
        return "#82cada"
    elif item.color == 8:
        return "#96a3c1"
    elif item.color == 9:
        return "#f48fb6"
    elif item.color == 10:
        return "#a4e8ca"
    elif item.color == 11:
        return "#dccee8"
    else:
        return False
