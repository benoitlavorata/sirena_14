# -*- coding: utf-8 -*-
{
    'name': 'Beautiful Powerful Dashboards',
    'category': 'Extra Tools',
    'website': 'https://www.odooinsights.com',
    'summary': "Beautiful powerful dashboards",
    'version': '14.0.14.3',
    'description': """
Beautiful powerful dashboards. Create a dashboard for KPI&apos;s, alerts, teams, TV displays. 
Works with all Odoo module such as inventory, sales, purchasing, crm, and accounting. 
Use line graphs, pie charts, bar charts, stacked charts, radar charts, tables, KPI kanban cards.
Track goals and measure progress with estimated, forecast and variation tracking.
Easily create multiple dashboard screens and tag your dashboard items to keep your dashboard displays organised.
Watch our training videos for clear easy to follow instructions on creating your own simple and advanced dashboards.
Updated every two weeks. Please let us know any feature requests you have.
        """,
    'author': 'Inspired Software Pty Ltd',
    'live_test_url': 'https://www.inspiredsoftware.com.au/r/YTb',
    'depends': [
        'base',
        'web',
        'mail',
        #'web_widget_color', # TODO: Add in dep
    ],
    'data': [
        'data/cron.xml',
        'data/email_template.xml',
        'data/dashboard_template.xml',
        'data/dashboard_widget_type.xml',

        'security/groups.xml',
        'security/ir.model.access.csv',

        'templates/dashboard_widget_table.xml',
        'templates/dashboard_email.xml',

        'views/assets.xml',
        'views/dashboard.xml',
        'views/dashboard_dashboard.xml',
        'views/dashboard_notes.xml',
        'views/dashboard_widget_config_date.xml',
        'views/dashboard_widget_card.xml',
        'views/dashboard_widget_datasource_python.xml',
        'views/dashboard_widget_graph.xml',
        'views/dashboard_widget_html.xml',
        'views/dashboard_widget__group_security.xml',
        'views/dashboard_widget_star.xml',
        'views/dashboard_widget_tag.xml',
        'views/dashboard_email.xml',
        'views/dashboard_sound.xml',
        'templates/dashboard_widget_table.xml',
        'templates/dashboard.xml',
        'templates/dashboard_email.xml',
        'templates/dashboard_card.xml',
        'templates/dashboard_notes.xml',
        'templates/dashboard_embedded_content.xml',
        'templates/dashboard_widget_cache.xml',
        'wizard/dashboard_wizard_create.xml',
    ],
    'qweb': [
        'static/src/xml/many2many_dashboards.xml',
    ],
    'images': [
        'static/description/main_image.gif',
    ],
    'installable': True,
    'application': True,

    'licence': 'OPL-1',
    'support': 'appsupport@inspiredsoftware.com.au',
    'price': '149',
    'currency': 'EUR',
}
