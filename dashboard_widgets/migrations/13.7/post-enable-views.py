from odoo import api, SUPERUSER_ID, release
import re


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    env = api.Environment(cr, SUPERUSER_ID, {})

    views = env['ir.ui.view']
    env.cr.execute("select name from ir_model_fields where name='mig_flag_dashboard' and model='ir.ui.view';")
    feature_installed_mig_flag_dashboard = True if env.cr.fetchall() else False

    if feature_installed_mig_flag_dashboard:
        views = env['ir.ui.view'].with_context(active_test=False).search([
            ('model', 'ilike', 'is.dashboard.widget'),
            ('mig_flag_dashboard', '=', True)
        ])

    if not views:
        # mig_flag_dashboard not available during install (or all views are disable)
        views = env['ir.ui.view'].with_context(active_test=False).search([
            ('model', 'ilike', 'is.dashboard.widget'),
            ('active', '=', False),
        ])
    views.write({'active': True})
