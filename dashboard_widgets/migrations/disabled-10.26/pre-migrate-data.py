from odoo import api, fields, models, release


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    pass
    # try:
    #     sql = "DELETE FROM ir_ui_view where name in ('view_dashboard_widget_kanban_count', 'view_is_dashboard_form_graph', 'view_is_dashboard_form_count', 'view_is_dashboard_form_count_inherit_dashboard_widgets_pwa', 'view_is_dashboard_form_count_inherit_dashboard_widgets_html')"
    #     cr.execute(sql)
    #     cr.commit()
    # except:
    #     pass
