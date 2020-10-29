from odoo import api, fields, models
from odoo.tools.safe_eval import safe_eval as safe_eval
from odoo import tools


import datetime
import dateutil

from odoo.tools import DEFAULT_SERVER_DATE_FORMAT, DEFAULT_SERVER_DATETIME_FORMAT

IS_ODOO_VERSION_BEFORE_v12 = False


class DashboardWidget(models.Model):
    _inherit = 'is.dashboard.widget'

    datasource = fields.Selection(selection_add=[
        ('python', 'Python (Advanced)'),
    ], ondelete={'python': 'set default'})

    query_1_config_python_domain = fields.Text(compute="compute_python_dom")
    query_2_config_python_domain = fields.Text(compute="compute_python_dom")

    query_1_table = fields.Text(compute="compute_python_dom")

    query_1_config_python = fields.Text("Python Code")

    def get_run_python_count_eval_context(self):
        return {
            'dashboard': self,

            'model': self.query_1_config_model_id.model,
            'date_range_start': self.query_1_config_date_range_start or self.query_1_config_datetime_range_start,
            'date_range_end': self.query_1_config_date_range_end or self.query_1_config_datetime_range_end,

            'dom1': self.query_1_config_python_domain,
            'dom2': self.query_2_config_python_domain,

            'env': self.env,
            'datetime': tools.safe_eval.datetime,
            'dateutil': tools.safe_eval.dateutil,

            'get_date_range': self.python_get_date_range,

            'DEFAULT_SERVER_DATE_FORMAT': DEFAULT_SERVER_DATE_FORMAT,
            'DEFAULT_SERVER_DATETIME_FORMAT': DEFAULT_SERVER_DATETIME_FORMAT,
        }

    def compute_python_dom(self):
        for rec in self:
            rec.run_python_count()

    def run_python_count(self):
        code = self.query_1_config_python
        locals = {}
        eval_context = self.get_run_python_count_eval_context()
        if code:
            try:
                safe_eval(code, eval_context, locals, mode="exec", nocopy=True)
            except Exception as ex:
                self._add_render_dashboard_markup_error('run_python_count', ex)

            self.count = locals.get('count', 0)
            self.total = locals.get('total', 0)
            self.query_1_config_python_domain = locals.get('dom1', False)
            self.query_2_config_python_domain = locals.get('dom2', False)
            self.query_1_table = locals.get('table', False)
        else:
            self.count = 0
            self.total = 0

    def eval_data(self, code, mode='eval'):
        locals = {}
        eval_context = self.get_run_python_count_eval_context()
        if code:
            try:
                return safe_eval(code, eval_context, locals, mode=mode, nocopy=True)
            except Exception as ex:
                return False
