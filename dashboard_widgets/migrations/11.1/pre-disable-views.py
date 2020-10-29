from odoo import api, SUPERUSER_ID, release
import re


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    env = api.Environment(cr, SUPERUSER_ID, {})

    env.cr.execute("select name from ir_model_fields where name='mig_flag_dashboard' and model='ir.ui.view';")
    feature_installed_mig_flag_dashboard = True if env.cr.fetchall() else False

    if feature_installed_mig_flag_dashboard:
        env.cr.execute("update ir_ui_view set mig_flag_dashboard=TRUE where model ILIKE 'is.dashboard.widget%' and active=TRUE")
    else:
        env.cr.execute("update ir_ui_view set active=FALSE where model ILIKE 'is.dashboard.widget%'")
