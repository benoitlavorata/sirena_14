from odoo import api, SUPERUSER_ID, release


def migrate(cr, version):
    if not version.startswith(release.major_version):
        return  # skip previously run migration scripts during a major upgrade

    env = api.Environment(cr, SUPERUSER_ID, {})
    # Copy company properties to field
    for rec in env['is.dashboard.widget'].with_context(active_test=False).search([]):
        copy_prop_to_model(env, rec, 'goal_count', 'goal_count')  # TODO: card_1_goal_standard?
        copy_prop_to_model(env, rec, 'goal_total', 'goal_total')  # card_2_goal_standard?

        widget_type = get_sql_value(cr, rec, 'widget_type')
        if not rec.display_mode and widget_type in (
                "count",
                "count_over_total",
                "count_over_total_ratio",
                "count_over_total_ratio_percentage",
        ):
            rec.display_mode = 'card'

        res_model = get_sql_value(cr, rec, 'res_model')
        if res_model and not rec.query_1_config_model_id:
            rec.query_1_config_model_id = env['ir.model'].search([('model', '=', res_model)], limit=1)

        # Copy query #1 settings to query #2 now that they are separate
        copy_field_if_not_set(rec, 'query_2_config_model_id', 'query_1_config_model_id')
        copy_field_if_not_set(rec, 'query_2_config_domain_use_widget', 'query_1_config_domain_use_widget')
        copy_field_if_not_set(rec, 'query_2_config_measure_field_id', 'query_1_config_measure_field_id')
        copy_field_if_not_set(rec, 'query_2_config_date_range_type', 'query_1_config_date_range_type')
        copy_field_if_not_set(rec, 'query_2_config_date_range_custom_start', 'query_1_config_date_range_custom_start')
        copy_field_if_not_set(rec, 'query_2_config_date_range_custom_end', 'query_1_config_date_range_custom_end')
        copy_field_if_not_set(rec, 'query_2_config_date_range_field_id', 'query_1_config_date_range_field_id')
        copy_field_if_not_set(rec, 'query_2_config_date_range_x', 'query_1_config_date_range_x')


        # TODO: Set fields like card_1_show_query_value, card_2_show_query_value if count_over_total.*, etc

def copy_field_if_not_set(record, dest_field, src_field):
    if not record[dest_field] and record[src_field]:
        record[dest_field] = record[src_field]

def get_sql_value(cr, record, column_name):
    sql = """
        SELECT "%s"
        FROM "%s"
        WHERE id=%s
    """
    cr.execute(sql % (column_name, record._table, record.id))
    fetched = cr.fetchone()
    if fetched:
        return fetched[0]
    return False


def copy_prop_to_model(env, record, prop_name, field_name):
    print('%s,%s'.format(record._name, record.id))
    prop = env['ir.property'].get(prop_name, record._name, res_id='{},{}'.format(record._name, record.id))
    if prop:
        print(prop)
        record[field_name] = prop
