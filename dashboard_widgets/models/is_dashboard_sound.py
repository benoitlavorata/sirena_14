from odoo import api, fields, models


class DashboardSound(models.Model):
    _inherit = 'is.dashboard.widget'

    SOUND_SELECTION = [
        ('buzzer', 'Buzzer'),
        ('cheer', 'Cheer'),
        ('custom', 'Custom'),
    ]

    play_sound_on_change_up = fields.Boolean(string="Play Sound on change (Increase)")
    play_sound_on_change_up_url = fields.Char(string="Technical Field: Play Sound on change (Sound File Url)", compute="compute_play_sound_on_change_up_url")
    play_sound_on_change_up_sound_custom = fields.Char(string="Custom Sound File Url")
    play_sound_on_change_up_sound = fields.Selection(string="Sound", selection=SOUND_SELECTION, default='cheer')

    play_sound_on_change_down = fields.Boolean(string="Play Sound on change (Decrease)")
    play_sound_on_change_down_url = fields.Char(string="Technical Field: Play Sound on change (Sound File Url)", compute="compute_play_sound_on_change_down_url")
    play_sound_on_change_down_sound_custom = fields.Char(string="Custom Sound File Url")
    play_sound_on_change_down_sound = fields.Selection(string="Sound", selection=SOUND_SELECTION, default='buzzer')

    @api.depends('play_sound_on_change_up_sound', 'play_sound_on_change_up_sound_custom')
    def compute_play_sound_on_change_up_url(self):
        for rec in self:
            rec.play_sound_on_change_up_url = rec._get_sound_file(
                rec.play_sound_on_change_up_sound,
                rec.play_sound_on_change_up_sound_custom,
            )

    @api.depends('play_sound_on_change_down_sound', 'play_sound_on_change_down_sound_custom')
    def compute_play_sound_on_change_down_url(self):
        for rec in self:
            rec.play_sound_on_change_down_url = rec._get_sound_file(
                rec.play_sound_on_change_down_sound,
                rec.play_sound_on_change_down_sound_custom,
            )

    def _get_sound_file(self, type, custom):
        if type == 'buzzer':
            return '/dashboard_widgets/static/src/sound/buzzer.mp3'
        elif type == 'cheer':
            return '/dashboard_widgets/static/src/sound/cheer.mp3'
        elif type == 'custom':
            return custom
        else:
            return False
