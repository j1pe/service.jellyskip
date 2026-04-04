import xbmcgui, xbmc, xbmcaddon
import time
from xbmcgui import ACTION_NAV_BACK, ACTION_PREVIOUS_MENU, ACTION_STOP

import helper.utils as utils
from helper import LazyLogger

OK_BUTTON = 2101
QUIT_BUTTON = 2102

MIN_REMAINING_SECONDS = 5
BINGE_PROPERTY_KEY = "jellyskip_binge_count"

LOG = LazyLogger(__name__)

class SkipSegmentDialogue(xbmcgui.WindowXMLDialog):

    def __init__(self, xmlFile, resourcePath, seek_time_seconds, segment_type, is_initial_play=False, play_start_time=0):
        self.seek_time_seconds = seek_time_seconds
        self.segment_type = segment_type
        self.player = xbmc.Player()
        self.is_initial_play = is_initial_play
        self.play_start_time = play_start_time

        self.is_closed = False
        self.action_taken = False 

        addon = xbmcaddon.Addon('service.jellyskip')
        try:
            self.max_display_seconds = int(addon.getSetting('intro_display_time'))
        except:
            self.max_display_seconds = 10

        try:
            self.outro_timeout = int(addon.getSetting('outro_timeout'))
        except:
            self.outro_timeout = 10

        try:
            self.max_binge_episodes = int(addon.getSetting('max_binge_episodes'))
        except:
            self.max_binge_episodes = 3

    def onInit(self):
        autoskip = xbmcaddon.Addon('service.jellyskip').getSettingBool('autoskip')
        if autoskip:
            self.close()
            if self.is_initial_play and (time.time() - self.play_start_time) < 15:
                xbmc.sleep(5000)
            xbmc.executebuiltin('Notification(Jellyskip, Skipped %s, 3000)' % self.segment_type)
            if self.player.isPlaying():
                current_time = self.player.getTime()
                total_time = self.player.getTotalTime()
                skip_distance = self.seek_time_seconds - current_time
                if total_time > 0 and skip_distance > 5:
                    from dialogue_handler import dialogue_handler
                    dialogue_handler.autoskip_time = time.time()
                    remaining_seconds = total_time - self.seek_time_seconds
                    if remaining_seconds < MIN_REMAINING_SECONDS:
                        self.player.seekTime(total_time - MIN_REMAINING_SECONDS)
                    else:
                        self.player.seekTime(self.seek_time_seconds)
            return

        quit_button = self.getControl(QUIT_BUTTON)
        if self.segment_type in ["Outro", "Credits"]:
            quit_button.setVisible(True)
        else:
            quit_button.setVisible(False)

        self.schedule_close_action()

    def get_seconds_till_segment_end(self):
        return self.seek_time_seconds - self.player.getTime()

    def schedule_close_action(self):
        segment_time_remaining = self.get_seconds_till_segment_end()

        if self.segment_type in ["Outro", "Credits"]:
            display_time = self.outro_timeout
        else:
            display_time = min(segment_time_remaining, self.max_display_seconds)

        if display_time > 0:
            utils.run_threaded(self.countdown_loop, delay=0, kwargs={'start_time': int(display_time)})
        else:
            utils.run_threaded(self.on_automatic_close, delay=15, kwargs={})

    def countdown_loop(self, start_time):
        current_time = start_time

        window = xbmcgui.Window(10000)
        current_count_str = window.getProperty(BINGE_PROPERTY_KEY)
        current_count = int(current_count_str) if current_count_str else 0
        is_limit_reached = current_count >= self.max_binge_episodes

        while current_time > 0 and not self.is_closed:
            try:
                skip_button = self.getControl(OK_BUTTON)
                if self.segment_type in ["Outro", "Credits"]:
                    if is_limit_reached:
                        skip_button.setLabel(f"Veille. Arrêt dans {current_time}s")
                    else:
                        skip_button.setLabel(f"Épisode suivant ({current_time}s)")
                else:
                    skip_button.setLabel(f"Skip {self.segment_type} ({current_time}s)")
            except:
                break

            for _ in range(10):
                if self.is_closed:
                    break
                xbmc.sleep(100)

            current_time -= 1

        if not self.is_closed and not self.action_taken:
            self.on_automatic_close()

    def reset_binge_counter(self):
        xbmcgui.Window(10000).clearProperty(BINGE_PROPERTY_KEY)

    def trigger_native_next(self):
        """ 
        Utilise l'API Python native de Kodi pour sauter à 2 secondes de la fin.
        C'est 100% fiable sur Android et Windows. 
        Jellyfin intercepte la fin naturelle de la vidéo et enchaîne l'épisode.
        """
        try:
            total_time = self.player.getTotalTime()
            if total_time > 3:
                self.player.seekTime(total_time - 2)
            else:
                xbmc.executebuiltin('PlayerControl(Next)')
        except Exception as e:
            LOG.error(f"Erreur lors du saut: {e}")

    def on_automatic_close(self):
        if self.action_taken or self.is_closed:
            return

        self.action_taken = True
        self.is_closed = True

        if self.segment_type in ["Outro", "Credits"] and self.player.isPlaying():
            window = xbmcgui.Window(10000)
            current_count_str = window.getProperty(BINGE_PROPERTY_KEY)
            current_count = int(current_count_str) if current_count_str else 0

            if current_count < self.max_binge_episodes:
                current_count += 1
                window.setProperty(BINGE_PROPERTY_KEY, str(current_count))
                self.close()
                xbmc.sleep(100)
                self.trigger_native_next()
                return
            else:
                self.reset_binge_counter()
                self.player.stop()
                xbmc.executebuiltin(f'Notification(Jellyskip, Lecture suspendue (Limite de {self.max_binge_episodes} épisodes), 5000)')

        self.close()
        xbmc.executebuiltin("NotifyAll(%s, %s, %s)" % ("service.jellyskip", "Jellyskip.DialogueClosed", {}))

    def onAction(self, action):
        if action in (ACTION_NAV_BACK, ACTION_PREVIOUS_MENU, ACTION_STOP):
            self.is_closed = True
            self.action_taken = True
            self.reset_binge_counter()
            self.close()

    def onControl(self, control):
        pass

    def onFocus(self, control):
        pass

    def onClick(self, control):
        if self.action_taken or self.is_closed:
            return

        self.action_taken = True
        self.is_closed = True

        if not self.player.isPlaying():
            self.close()
            return

        self.reset_binge_counter()

        if control == OK_BUTTON:
            if self.segment_type in ["Outro", "Credits"]:
                self.close()
                xbmc.sleep(100)
                self.trigger_native_next()
                return
            else:
                remaining_seconds = self.player.getTotalTime() - self.seek_time_seconds
                if remaining_seconds < MIN_REMAINING_SECONDS:
                    self.player.seekTime(self.player.getTotalTime() - MIN_REMAINING_SECONDS)
                else:
                    self.player.seekTime(self.seek_time_seconds)

        elif control == QUIT_BUTTON:
            self.player.stop()

        self.close()
