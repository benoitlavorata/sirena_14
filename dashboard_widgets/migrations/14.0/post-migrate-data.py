from odoo import api, SUPERUSER_ID, release
import re


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    env = api.Environment(cr, SUPERUSER_ID, {})

    env['is.dashboard.widget'].search([('template_category_id', '=', False)]).write({
        'template_category_id': env.ref('dashboard_widgets.dashboard_template_category_user').id,
    })
