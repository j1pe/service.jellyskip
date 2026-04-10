import xbmcgui, xbmc, xbmcaddon
import time
import threading
from xbmcgui import ACTION_NAV_BACK, ACTION_PREVIOUS_MENU, ACTION_STOP

import helper.utils as utils
from helper import LazyLogger

OK_BUTTON = 2101
QUIT_BUTTON = 2102

MIN_REMAINING_SECONDS = 5
BINGE_PROPERTY_KEY = "jellyskip_binge_count"

# Durée de l'animation WindowClose dans le XML (slide 450ms + fade 350ms)
# On attend la plus longue + marge de sécurité
DIALOG_CLOSE_ANIMATION_MS = 500

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

    def _wait_for_dialog_close(self):
        """
        Attend que l'animation de fermeture du dialogue soit terminée.

        ROOT CAUSE du bug : PlayerControl(Next) appelé pendant l'animation
        de fermeture déclenche "ignoring action 14, topmost modal dialog
        closing animation is running" — la commande est silencieusement ignorée.

        Solution : attente active via xbmcgui.getCurrentWindowDialogId() jusqu'à
        ce que notre fenêtre (id=9999) ne soit plus la fenêtre active, puis
        délai supplémentaire pour l'animation résiduelle.
        """
        # Attente active : jusqu'à ce que le dialogue ne soit plus au premier plan
        timeout = 30  # 3 secondes max
        while timeout > 0:
            try:
                current_dialog_id = xbmcgui.getCurrentWindowDialogId()
                if current_dialog_id != 9999:
                    break
            except Exception:
                break
            xbmc.sleep(100)
            timeout -= 1

        # Délai supplémentaire pour l'animation résiduelle (slide: 450ms, fade: 350ms)
        xbmc.sleep(DIALOG_CLOSE_ANIMATION_MS)

    def _get_next_episode_url(self):
        """
        Récupère l'URL plugin:// de l'épisode suivant via l'API Jellyfin.
        Retourne None si introuvable.
        """
        try:
            import json
            import urllib.request
            import xbmcvfs

            # Lire la config jellyfin-kodi
            data_path = xbmcvfs.translatePath(
                "special://profile/addon_data/plugin.video.jellyfin/data.json"
            )
            with open(data_path, "rb") as f:
                jf_config = json.load(f)

            server  = jf_config["Servers"][0]["address"]
            token   = jf_config["Servers"][0]["AccessToken"]
            user_id = jf_config["Servers"][0].get("UserId", "")

            headers = {
                "Accept": "application/json",
                "Authorization": f"MediaBrowser Token={token}",
            }

            # L'ID Jellyfin est stocké dans la window property par jellyfin-kodi
            win = xbmcgui.Window(10000)
            item_id = (win.getProperty("jellyfin_id")
                       or win.getProperty("emby_id")
                       or win.getProperty("jellyfinid"))

            # Fallback : extraire l'ID depuis l'URL du fichier en lecture
            if not item_id:
                import re
                try:
                    playing_file = self.player.getPlayingFile()
                    m = re.search(r'[?&]id=([a-f0-9]{32})', playing_file, re.I)
                    if m:
                        item_id = m.group(1)
                except Exception:
                    pass

            if not item_id:
                LOG.warning("[jellyskip] Could not find Jellyfin ItemId for next episode lookup")
                return None

            LOG.info(f"[jellyskip] Looking up next episode for item_id={item_id}")

            # Récupérer SeriesId et IndexNumber de l'épisode en cours
            req = urllib.request.Request(
                f"{server}/Users/{user_id}/Items/{item_id}?Fields=SeriesId,SeasonId,IndexNumber,ParentIndexNumber",
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                item_info = json.load(resp)

            series_id = item_info.get("SeriesId")
            season_id = item_info.get("SeasonId")
            index     = item_info.get("IndexNumber", 0)

            if not series_id:
                LOG.warning("[jellyskip] No SeriesId — not a TV episode?")
                return None

            # Stratégie A : NextUp (épisode suivant non vu)
            req = urllib.request.Request(
                f"{server}/Shows/NextUp?UserId={user_id}&SeriesId={series_id}&Limit=1&Fields=MediaSources",
                headers=headers
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                next_up = json.load(resp)

            next_items = next_up.get("Items", [])
            if next_items:
                next_id = next_items[0]["Id"]
                LOG.info(f"[jellyskip] Next episode via NextUp API: {next_id}")
                return f"plugin://plugin.video.jellyfin/?mode=play&id={next_id}"

            # Stratégie B : épisode IndexNumber+1 dans la même saison
            if season_id and index:
                req = urllib.request.Request(
                    f"{server}/Users/{user_id}/Items?ParentId={season_id}&SortBy=IndexNumber&SortOrder=Ascending&Fields=MediaSources",
                    headers=headers
                )
                with urllib.request.urlopen(req, timeout=5) as resp:
                    season_items = json.load(resp)

                for ep in season_items.get("Items", []):
                    if ep.get("IndexNumber") == index + 1:
                        next_id = ep["Id"]
                        LOG.info(f"[jellyskip] Next episode via season index: {next_id}")
                        return f"plugin://plugin.video.jellyfin/?mode=play&id={next_id}"

            LOG.info("[jellyskip] No next episode found in Jellyfin")
            return None

        except Exception as e:
            LOG.error(f"[jellyskip] Error getting next episode URL: {e}")
            return None

    def trigger_next_episode(self):
        """
        Passe à l'épisode suivant.

        CRITIQUE : toujours appelé dans un thread séparé APRÈS _wait_for_dialog_close(),
        pour éviter "ignoring action 14, topmost modal dialog closing animation is running".

        Stratégies en cascade :
          1. PlayerControl(Next) si la playlist Kodi a un item suivant
          2. Lecture directe via URL plugin://plugin.video.jellyfin (API Jellyfin)
          3. Fallback : seek à total_time - 2s
        """
        # Attendre que l'animation de fermeture soit terminée — FIX PRINCIPAL
        self._wait_for_dialog_close()

        # --- Stratégie 1 : item suivant déjà dans la playlist Kodi ---
        try:
            playlist = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            pos  = playlist.getposition()
            size = playlist.size()
            if size > 1 and pos < size - 1:
                LOG.info("[jellyskip] Next ep via PlayerControl(Next) — playlist has next item")
                xbmc.executebuiltin("PlayerControl(Next)")
                return
        except Exception as e:
            LOG.error(f"[jellyskip] Playlist check failed: {e}")

        # --- Stratégie 2 : URL directe via API Jellyfin ---
        next_url = self._get_next_episode_url()
        if next_url:
            LOG.info(f"[jellyskip] Next ep via direct URL: {next_url}")
            self._deferred_play(next_url)
            return

        # --- Stratégie 3 : fallback original (seek fin de vidéo) ---
        LOG.warning("[jellyskip] Fallback: seeking to end of video to trigger natural next")
        try:
            total_time = self.player.getTotalTime()
            if total_time > 3:
                self.player.seekTime(total_time - 2)
            else:
                xbmc.executebuiltin('PlayerControl(Next)')
        except Exception as e:
            LOG.error(f"[jellyskip] Fallback seek failed: {e}")

    def _deferred_play(self, url):
        """
        Stop propre puis lecture avec attente active.
        Indispensable sur Android où player.stop() est asynchrone.
        """
        player = xbmc.Player()

        if player.isPlaying():
            player.stop()

        # Attente active que le player soit vraiment arrêté
        timeout = 30  # 3 secondes max (30 × 100ms)
        while player.isPlaying() and timeout > 0:
            xbmc.sleep(100)
            timeout -= 1

        if timeout == 0:
            LOG.warning("[jellyskip] Player did not stop cleanly after 3s, forcing play anyway")

        # Délai de sécurité supplémentaire (décodeur HW Android)
        xbmc.sleep(300)

        # ListItem explicite — obligatoire sur Android
        listitem = xbmcgui.ListItem(path=url)
        listitem.setProperty('IsPlayable', 'true')

        LOG.info(f"[jellyskip] _deferred_play: launching {url}")
        player.play(item=url, listitem=listitem)

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
                # trigger_next_episode() appelé dans un thread — il gère lui-même
                # l'attente de fermeture de l'animation via _wait_for_dialog_close()
                threading.Thread(target=self.trigger_next_episode, daemon=True).start()
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
                # Lancer dans un thread pour ne pas bloquer le thread GUI
                # trigger_next_episode() attend lui-même la fin de l'animation
                threading.Thread(target=self.trigger_next_episode, daemon=True).start()
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
