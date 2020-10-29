from odoo import api, fields, models, release


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    pass
