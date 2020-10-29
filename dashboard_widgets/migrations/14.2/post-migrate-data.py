from odoo import api, SUPERUSER_ID, release
import re


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    env = api.Environment(cr, SUPERUSER_ID, {})

    env['is.dashboard.widget'].search([('open_action_1_auto_generate_view', '=', True)]).write({
        'drilldown_type': 'custom_action',
    })
