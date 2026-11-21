#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
#########################################################
#                                                       #
#  RadioM Plugin                                        #
#  Version: 1.6                                         #
#  Created by Lululla (https://github.com/Belfagor2005) #
#  License: Gnu Gpl v2                                  #
#  https://creativecommons.org/licenses/by-nc-sa/4.0    #
#                                                       #
#  Credits:                                             #
#  - Original concept by Lululla                        #
#  - Development by Lululla                             #
#  Usage of this code without proper attribution        #
#  is strictly prohibited.                              #
#  For modifications and redistribution,                #
#  please maintain this credit header.                  #
#########################################################

1.6 changes
 - laut.fm style sections: Top, Favourites, Recent, Near you, Genres, Search
 - online search (station names, descriptions, artists) + genre pages
 - station list loaded in background + local cache (no more GUI freeze)
 - "Now Playing": cover, blurred backdrop, progress bar, recently played,
   upcoming artists, prev/next station, sleep timer, ICY titles
 - About screen with donation QR codes
 - self update from GitHub Releases (notify / automatic / off)
"""

from __future__ import print_function

import codecs
import json
import sys
from os import listdir
from os.path import exists, join, dirname
from time import time, localtime, strftime

from Components.ActionMap import ActionMap
from Components.Label import Label
from Components.MenuList import MenuList
from Components.MultiContent import MultiContentEntryText
try:
    from Components.MultiContent import MultiContentEntryPixmapAlphaBlend
except ImportError:
    from Components.MultiContent import MultiContentEntryPixmapAlphaTest as MultiContentEntryPixmapAlphaBlend
from Components.Pixmap import Pixmap
from Components.ProgressBar import ProgressBar
from Components.ServiceEventTracker import ServiceEventTracker, InfoBarBase
from Plugins.Plugin import PluginDescriptor
from Screens.ChoiceBox import ChoiceBox
from Screens.InfoBarGenerics import (
    InfoBarMenu,
    InfoBarSeek,
    InfoBarNotifications,
    InfoBarShowHide,
)
from Screens.MessageBox import MessageBox
from Screens.Screen import Screen
from Screens.VirtualKeyBoard import VirtualKeyBoard
from enigma import (
    RT_HALIGN_LEFT,
    RT_HALIGN_RIGHT,
    RT_VALIGN_CENTER,
    eListboxPythonMultiContent,
    eServiceReference,
    eTimer,
    gFont,
    gRGB,
    getDesktop,
    iPlayableService,
    iServiceInformation,
    loadPNG,
)
from twisted.internet import reactor, threads

from . import _, Utils, __version__
from . import lautapi as L
from . import updater
from .PicLoader import PicLoader

try:
    from Components.AVSwitch import AVSwitch
    sc = AVSwitch().getFramebufferScale()
except Exception:
    sc = (1, 1)


# --------------------------------------------------------------------------
#  Paths / constants
# --------------------------------------------------------------------------

THISPLUG = dirname(sys.modules[__name__].__file__)
PLAYLISTS = join(THISPLUG, 'Playlists')
SETTINGS_FILE = '/etc/enigma2/radiom.json'

screenWidth = getDesktop(0).size().width()
if screenWidth >= 2560:
    skin_path = join(THISPLUG, 'skin', 'wqhd')
elif screenWidth >= 1920:
    skin_path = join(THISPLUG, 'skin', 'fhd')
else:
    skin_path = join(THISPLUG, 'skin', 'hd')
# every pixel value in the code is designed for 1920 and scaled
SCALE = screenWidth / 1920.0 if screenWidth else 1.0

DEFAULT_LOGO = join(skin_path, 'ft.jpg')

PLAYERS = [('4097', 'GStreamer')]
if exists('/usr/lib/enigma2/python/Plugins/SystemPlugins/ServiceApp'):
    PLAYERS.append(('5002', 'ExtePlayer3'))
PLAYERS.append(('movie', 'MoviePlayer'))

UPDATE_MODES = [('notify', _('Ask before installing')),
                ('auto', _('Install automatically')),
                ('off', _('Never check'))]

TABS = [('top', _('Top')), ('fav', _('Favourites')), ('recent', _('Recent')),
        ('near', _('Near you')), ('genres', _('Genres')), ('search', _('Search'))]

COL_TAB = 0xb8a3dc
COL_TAB_ACTIVE = 0xff4fb0


def S(v):
    """Scale a 1920-based pixel value to the current resolution."""
    return int(round(v * SCALE))


def fmt_time(seconds):
    seconds = max(0, int(seconds))
    return '%d:%02d' % (seconds // 60, seconds % 60)


def station_key(rec):
    return rec.get('id') or rec.get('url', '')


def clean_rec(rec):
    return dict((k, v) for k, v in rec.items() if not k.startswith('_'))


# --------------------------------------------------------------------------
#  Settings
# --------------------------------------------------------------------------

class Settings(object):
    def __init__(self):
        self.data = {
            'favourites': [],
            'recent': [],
            'player': '4097',
            'last_search': '',
            'update_mode': 'notify',
            'location': None}
        try:
            with codecs.open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                self.data.update(json.load(f))
        except Exception:
            pass

    def save(self):
        try:
            with codecs.open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
        except Exception as e:
            print('[RadioM] settings save error: %s' % e)

    def fav_keys(self):
        return set(station_key(r) for r in self.data['favourites'])

    def is_fav(self, rec):
        return station_key(rec) in self.fav_keys()

    def toggle_fav(self, rec):
        key = station_key(rec)
        favs = [r for r in self.data['favourites'] if station_key(r) != key]
        added = len(favs) == len(self.data['favourites'])
        if added:
            favs.append(clean_rec(rec))
        self.data['favourites'] = favs
        self.save()
        return added

    def add_recent(self, rec):
        key = station_key(rec)
        recent = [
            r for r in self.data.get(
                'recent',
                []) if station_key(r) != key]
        recent.insert(0, clean_rec(rec))
        self.data['recent'] = recent[:25]
        self.save()


settings = Settings()


# --------------------------------------------------------------------------
#  Shared playback state (survives closing the player screen)
# --------------------------------------------------------------------------

class NowPlaying(object):
    rec = None
    sref_old = None
    session = None
    sleep_timer = None
    sleep_end = 0

    @classmethod
    def play(cls, session, rec, player):
        url = rec['url'].replace(':', '%3a').replace(' ', '%20')
        stype = player if player in ('4097', '5002') else '4097'
        ref = eServiceReference('%s:0:2:0:0:0:0:0:0:0:%s' % (stype, url))
        ref.setName(rec['title'])
        if cls.sref_old is None:
            cls.sref_old = session.nav.getCurrentlyPlayingServiceReference()
        session.nav.stopService()
        session.nav.playService(ref)
        cls.rec = rec
        cls.session = session
        settings.add_recent(rec)

    @classmethod
    def stop(cls, session):
        if cls.rec is None:
            return
        cls.rec = None
        try:
            session.nav.stopService()
            if cls.sref_old:
                session.nav.playService(cls.sref_old)
        except Exception as e:
            print('[RadioM] stop error: %s' % e)
        cls.sref_old = None
        cls.cancel_sleep()

    @classmethod
    def is_playing(cls, rec=None):
        if cls.rec is None:
            return False
        return rec is None or station_key(rec) == station_key(cls.rec)

    @classmethod
    def set_sleep(cls, minutes):
        cls.cancel_sleep()
        if not minutes:
            return
        cls.sleep_timer = make_timer(cls._sleep_fire)
        cls.sleep_timer.start(minutes * 60 * 1000, True)
        cls.sleep_end = time() + minutes * 60

    @classmethod
    def cancel_sleep(cls):
        if cls.sleep_timer:
            cls.sleep_timer.stop()
        cls.sleep_timer = None
        cls.sleep_end = 0

    @classmethod
    def _sleep_fire(cls):
        print('[RadioM] sleep timer expired')
        if cls.session:
            cls.stop(cls.session)


# --------------------------------------------------------------------------
#  Helpers for screens
# --------------------------------------------------------------------------

def load_skin(name):
    with codecs.open(join(skin_path, name), 'r', encoding='utf-8') as f:
        return f.read()


def make_timer(callback):
    t = eTimer()
    try:
        t._conn = t.timeout.connect(callback)
    except AttributeError:
        t.callback.append(callback)
    return t


def set_color(label, rgb):
    try:
        label.instance.setForegroundColor(gRGB(rgb))
        label.instance.invalidate()
    except Exception:
        pass


class ImageWidget(object):
    """Async decode of a file into a Pixmap widget."""

    def __init__(self, widget):
        self.widget = widget
        self.loader = PicLoader()
        self.loader.addCallback(self._done)
        self.current = None

    def show(self, path):
        if not path or not exists(path) or path == self.current:
            return
        inst = self.widget.instance
        if inst is None:
            return
        self.current = path
        size = inst.size()
        self.loader.setPara(
            (size.width(),
             size.height(),
             sc[0],
                sc[1],
                False,
                1,
                '#00000000'))
        self.loader.startDecode(path)

    def _done(self, info=None):
        try:
            ptr = self.loader.getData()
            if ptr is not None and self.widget.instance:
                self.widget.instance.setPixmap(ptr)
                self.widget.show()
        except Exception as e:
            print('[RadioM] image error: %s' % e)


class StationList(MenuList):
    def __init__(self):
        MenuList.__init__(self, [], True, eListboxPythonMultiContent)
        self.l.setItemHeight(S(86))
        self.l.setFont(0, gFont('Regular', S(34)))
        self.l.setFont(1, gFont('Regular', S(25)))
        self.l.setFont(2, gFont('Regular', S(21)))
        self.icons = dict(
            (k,
             loadPNG(
                 join(
                     skin_path,
                     'ic_%s.png' %
                     k))) for k in (
                'fav',
                'radio',
                'play',
                'genre',
                'genre_top'))
        self.width = S(1120)

    def _row(self, rec, icon, title, subtitle, big='', small=''):
        w, h = self.width, S(86)
        res = [rec,
               MultiContentEntryPixmapAlphaBlend(
                   pos=(S(14), (h - S(44)) // 2), size=(S(44), S(44)), png=icon),
               MultiContentEntryText(
                   pos=(S(78), S(8)), size=(w - S(260), S(42)), font=0,
                   text=title, color=0xffffff, color_sel=0xffffff,
                   flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER),
               MultiContentEntryText(
                   pos=(S(78), S(48)), size=(w - S(260), S(32)), font=1,
                   text=subtitle, color=0xb8a3dc, color_sel=0xf3e8ff,
                   flags=RT_HALIGN_LEFT | RT_VALIGN_CENTER)]
        if big:
            res.append(MultiContentEntryText(
                pos=(w - S(170), S(10)), size=(S(150), S(40)), font=0,
                text=big, color=0xff4fb0, color_sel=0xffffff,
                flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER))
            res.append(MultiContentEntryText(
                pos=(w - S(170), S(48)), size=(S(150), S(30)), font=2,
                text=small, color=0x8f7bb0, color_sel=0xf3e8ff,
                flags=RT_HALIGN_RIGHT | RT_VALIGN_CENTER))
        return res

    def build_station(self, rec, fav):
        if NowPlaying.is_playing(rec):
            icon = self.icons['play']
        elif fav:
            icon = self.icons['fav']
        else:
            icon = self.icons['radio']
        parts = []
        if rec.get('_dist') is not None:
            parts.append('%d km' % rec['_dist'])
        if rec.get('genres'):
            parts.append(', '.join(rec['genres'][:3]))
        if rec.get('location'):
            parts.append(rec['location'])
        if not parts:
            parts.append(rec.get('desc') or rec.get('url', ''))
        big = small = ''
        if rec.get('src') == 'laut':
            big, small = str(rec.get('listeners', 0)), _('listeners')
        return self._row(
            rec,
            icon,
            rec['title'],
            '  ·  '.join(parts),
            big,
            small)

    def build_genre(self, rec):
        icon = self.icons['genre_top'] if rec.get(
            'top') else self.icons['genre']
        sub = _('Top genre on laut.fm') if rec.get(
            'top') else (rec.get('example') or '')
        return self._row(
            rec, icon, rec['genre'], sub, str(
                rec['count']), _('stations'))

    def fill(self, items, kind='stations'):
        if kind == 'genres':
            self.setList([self.build_genre(r) for r in items])
        else:
            favs = settings.fav_keys()
            self.setList([self.build_station(r, station_key(r) in favs)
                         for r in items])


# --------------------------------------------------------------------------
#  Update helpers (shared by main and about screens)
# --------------------------------------------------------------------------

def start_update(session, info, status=None):
    """Install a release found by updater.check_latest()."""
    if status:
        status(_('Downloading RadioM %s from GitHub...') % info['version'])

    def done(result):
        ok, msg = result
        if ok:
            if status:
                status(_('RadioM %s installed') % info['version'])
            session.openWithCallback(
                restart_gui,
                MessageBox,
                _('RadioM %s has been installed.\n\nRestart the GUI now to use it?') %
                info['version'],
                MessageBox.TYPE_YESNO)
        else:
            if status:
                status(_('Update failed'))
            session.open(
                MessageBox, _('Update failed:\n%s') %
                msg, MessageBox.TYPE_ERROR)
    threads.deferToThread(
        updater.install_tarball,
        info['tarball']).addCallback(done)


def restart_gui(answer):
    if answer:
        try:
            from Screens.Standby import TryQuitMainloop
            NowPlaying.session.open(TryQuitMainloop, 3)
        except Exception as e:
            print('[RadioM] restart error: %s' % e)


# --------------------------------------------------------------------------
#  Main screen
# --------------------------------------------------------------------------

class RadioMMain(Screen):

    def __init__(self, session):
        self.skin = load_skin('radiom.xml')
        Screen.__init__(self, session)
        self.setTitle('RadioM')
        NowPlaying.session = session
        self.all_stations = []
        self.by_id = {}
        self.view = []
        self.kind = 'stations'
        self.tab = 'top'
        # ('genre', name) | ('search', text) | ('file', name)
        self.sub = None
        self.sub_results = []
        self.genre_back_index = 0
        self.near_results = None
        self.alive = True
        self.loading = False
        self.update_info = None

        self['list'] = StationList()
        self['logo'] = Pixmap()
        for i, (key, label) in enumerate(TABS):
            self['tab_' + key] = Label('%d %s' % (i + 1, label))
        self['mode'] = Label('')
        self['status'] = Label(_('Loading stations...'))
        self['nowplaying'] = Label('')
        self['st_name'] = Label('')
        self['st_genres'] = Label('')
        self['st_meta'] = Label('')
        self['st_desc'] = Label('')
        self['st_listeners'] = Label('')
        self['key_red'] = Label(_('Exit'))
        self['key_green'] = Label(_('Play'))
        self['key_yellow'] = Label(_('Favourite'))
        self['key_blue'] = Label(_('Next section'))
        self['key_menu'] = Label(_('Menu'))
        self['key_about'] = Label(_('About'))

        self.logo = ImageWidget(self['logo'])
        self.logo_timer = make_timer(self.load_logo)

        actions = {
            'ok': self.key_ok,
            'green': self.key_ok,
            'cancel': self.exit,
            'red': self.exit,
            'yellow': self.toggle_fav,
            'blue': self.next_tab,
            'menu': self.open_menu,
            'up': self.key_up,
            'down': self.key_down,
            'left': self.key_left,
            'right': self.key_right,
            'nextBouquet': self.key_left,
            'prevBouquet': self.key_right,
            '0': self.open_about,
        }
        for i, (key, _label) in enumerate(TABS):
            actions[str(i + 1)] = (lambda k=key: self.set_tab(k))
        self['actions'] = ActionMap(
            ['OkCancelActions', 'ColorActions', 'DirectionActions', 'MenuActions',
             'ChannelSelectBaseActions', 'NumberActions'],
            actions, -1)
        # INFO is mapped differently on OpenPLi / OpenATV / DreamOS images
        self['infoActions'] = ActionMap(
            ['EPGSelectActions', 'InfobarEPGActions', 'InfoActions'],
            {'info': self.show_details,
             'showEventInfo': self.show_details,
             'showEventInfoPlugin': self.show_details,
             'showEventInfoSingleEPG': self.show_details}, -1)
        self.last_info = 0
        self.onLayoutFinish.append(self.start)

    # ---------------------------------------------------------------- start
    def start(self):
        L.reset_log()
        self.logo.show(DEFAULT_LOGO)
        ts, lts, cached = L.load_cache()
        now = time()
        if cached:
            self.set_stations(cached)
        self.apply_view()
        if not cached or now - ts > L.CACHE_TTL:
            self.reload_stations()
        elif now - lts > L.LISTENERS_TTL:
            self.refresh_listeners()
        if settings.data.get('update_mode', 'notify') != 'off':
            threads.deferToThread(
                updater.check_latest).addCallback(
                self._update_checked)

    def set_stations(self, stations):
        self.all_stations = stations
        self.by_id = dict((r['id'], r) for r in stations)

    def reload_stations(self):
        if self.loading:
            return
        self.loading = True
        # nothing cached: fill the list while loading
        self.show_partial = not self.all_stations
        self['status'].setText(_('Downloading station list...'))

        def progress(part):
            reactor.callFromThread(self._stations_partial, part)
        d = threads.deferToThread(L.fetch_all_stations, progress=progress)
        d.addCallback(self._stations_done)
        d.addErrback(self._load_error)

    def _stations_partial(self, part):
        if not self.alive or not self.loading or not self.show_partial or not part:
            return
        self.set_stations(part)
        if self.tab == 'top' and not self.sub:
            self.apply_view(keep_selection=True)
        self['status'].setText(_('Loading stations... %d') % len(part))

    def _stations_done(self, stations):
        self.loading = False
        if not self.alive:
            return
        if stations:
            L.save_cache(stations)
            self.set_stations(stations)
            self.near_results = None
            if self.tab == 'near':
                self.load_near()
            self.apply_view(keep_selection=True)
        elif not self.all_stations:
            self.apply_view()
            self['status'].setText(
                _('No stations (%s). Details in %s') %
                (L.LAST_ERROR or '?', L.LOG_FILE))

    def _load_error(self, failure):
        self.loading = False
        L.log('station list failed: %s' % failure.getErrorMessage())
        if self.alive:
            self.apply_view()
            self['status'].setText(
                _('Network error (%s). Details in %s') %
                (failure.getErrorMessage()[
                    :60], L.LOG_FILE))

    def refresh_listeners(self):
        stations = list(self.all_stations)

        def done(result):
            if self.alive and result:
                ts, _lts, _old = L.load_cache()
                L.save_cache(result, ts=ts)
                self.set_stations(result)
                if self.tab == 'top' and not self.sub:
                    self.apply_view(keep_selection=True)
        threads.deferToThread(
            lambda: L.apply_listeners(
                stations,
                L.fetch_listeners())).addCallback(done).addErrback(
            lambda f: print(
                '[RadioM] listeners: %s' %
                f))

    # ----------------------------------------------------------------- tabs
    def set_tab(self, tab):
        if tab == self.tab and not self.sub and tab != 'search':
            return
        self.tab = tab
        self.sub = None
        self['list'].moveToIndex(0)
        if tab == 'near' and self.near_results is None:
            self.load_near()
        self.apply_view()
        if tab == 'search':
            self.ask_search()

    def next_tab(self):
        keys = [k for k, _l in TABS]
        self.set_tab(keys[(keys.index(self.tab) + 1) % len(keys)])

    def update_tabs(self):
        for key, _label in TABS:
            set_color(self['tab_' + key],
                      COL_TAB_ACTIVE if key == self.tab else COL_TAB)

    # ----------------------------------------------------------------- view
    def genre_rows(self):
        counts, example = {}, {}
        for r in self.all_stations:
            for g in r.get('genres', []):
                counts[g] = counts.get(g, 0) + 1
                example.setdefault(g, r)
        rows = []
        lower = dict((g.lower(), g) for g in counts)
        for g in L.TOP_GENRES:
            real = lower.get(g.lower(), g)
            first = example.get(real, {})
            rows.append(
                {
                    'genre': real, 'count': counts.get(
                        real, 0), 'top': True, 'logo': first.get(
                        'logo', ''), 'example': first.get(
                        'title', '')})
        top_lower = set(g.lower() for g in L.TOP_GENRES)
        rest = [(g, n) for g, n in counts.items()
                if g.lower() not in top_lower and n >= 2]
        rest.sort(key=lambda kv: (-kv[1], kv[0].lower()))
        for g, n in rest:
            first = example.get(g, {})
            rows.append({'genre': g, 'count': n, 'top': False, 'logo': first.get('logo', ''),
                         'example': _('e.g. %s') % first.get('title', '') if first else ''})
        return rows

    def apply_view(self, keep_selection=False):
        current = self.selected() if keep_selection else None
        kind, status = 'stations', ''
        if self.sub:
            t, arg = self.sub
            view = self.sub_results
            title = {'genre': _('Genre: %s'), 'search': _('Search: "%s"'),
                     'file': _('Playlist: %s')}[t] % arg.replace('.txt', '')
            if not view:
                status = _('Nothing found')
        elif self.tab == 'fav':
            view, title = list(
                settings.data['favourites']), _('Your favourites')
            if not view:
                status = _('No favourites yet: press YELLOW on a station')
        elif self.tab == 'recent':
            view, title = list(settings.data.get('recent', [])), _(
                'Recently played stations')
            if not view:
                status = _('Nothing played yet')
        elif self.tab == 'near':
            loc = settings.data.get('location') or {}
            view = self.near_results or []
            title = _('Near %s') % loc['city'] if loc.get(
                'city') else _('Stations near you')
            if self.near_results is None:
                status = _('Finding your position...')
            elif not view:
                status = _('No stations with a position near you')
        elif self.tab == 'genres':
            kind, view, title = 'genres', self.genre_rows(), _('All genres')
        elif self.tab == 'search':
            view, title = [], _('Search')
            status = _('Press OK to search stations, artists, genres, cities')
        else:
            view, title = self.all_stations, _('Top stations')
        if self.loading and not view:
            status = _('Downloading station list...')
        self.view, self.kind = view, kind
        self['mode'].setText('%s  ·  %d' %
                             (title, len(view)) if view else title)
        self['list'].fill(view, kind)
        if current:
            key = current.get('genre') or station_key(current)
            for i, r in enumerate(view):
                if (r.get('genre') or station_key(r)) == key:
                    self['list'].moveToIndex(i)
                    break
        self['status'].setText(status)
        self.update_tabs()
        self.update_nowplaying()
        self.selection_changed()

    def update_nowplaying(self):
        self['nowplaying'].setText(
            '♫  ' + NowPlaying.rec['title'] if NowPlaying.rec else '')

    def selected(self):
        idx = self['list'].getSelectionIndex()
        if idx is None or idx < 0 or idx >= len(self.view):
            return None
        return self.view[idx]

    def selection_changed(self):
        rec = self.selected()
        if not rec:
            for k in (
                'st_name',
                'st_genres',
                'st_meta',
                'st_desc',
                    'st_listeners'):
                self[k].setText('')
            self['key_green'].setText(
                _('Search') if self.tab == 'search' else '')
            self['key_yellow'].setText('')
            self.logo_timer.start(350, True)
            return
        if self.kind == 'genres':
            self['st_name'].setText(rec['genre'])
            self['st_genres'].setText(
                _('Top genre') if rec.get('top') else _('Genre'))
            self['st_meta'].setText(
                _('%d stations in the list') %
                rec['count'])
            self['st_desc'].setText(
                _('Press OK to see all the stations of this genre, also the ones not in the top list.'))
            self['st_listeners'].setText('')
            self['key_green'].setText(_('Open'))
            self['key_yellow'].setText('')
        else:
            self['st_name'].setText(rec['title'])
            self['st_genres'].setText(', '.join(rec.get('genres', [])))
            meta = [
                x for x in (
                    ('%d km' % rec['_dist']) if rec.get('_dist') is not None else '',
                    rec.get('location'),
                    ('DJ ' + rec['djs']) if rec.get('djs') else '') if x]
            self['st_meta'].setText('  ·  '.join(meta))
            desc = rec.get('format') or ''
            if rec.get('desc') and rec['desc'] != desc:
                desc = (desc + '\n' + rec['desc']).strip()
            self['st_desc'].setText(desc)
            if rec.get('src') == 'laut':
                self['st_listeners'].setText(
                    _('%d listening now') %
                    rec.get(
                        'listeners', 0))
            else:
                self['st_listeners'].setText(_('Custom stream'))
            self['key_green'].setText(_('Play'))
            self['key_yellow'].setText(
                _('Remove fav.') if settings.is_fav(rec) else _('Favourite'))
        # debounce: download the logo only when the cursor stops
        self.logo_timer.start(350, True)

    def load_logo(self):
        rec = self.selected()
        url = rec.get('logo') if rec else ''
        if not url:
            self.logo.show(DEFAULT_LOGO)
            return

        def done(path):
            cur = self.selected()
            if self.alive and cur and cur.get('logo') == url:
                self.logo.show(path or DEFAULT_LOGO)
        threads.deferToThread(L.download_logo, url).addCallback(done)

    def key_up(self):
        self['list'].up()
        self.selection_changed()

    def key_down(self):
        self['list'].down()
        self.selection_changed()

    def key_left(self):
        self['list'].pageUp()
        self.selection_changed()

    def key_right(self):
        self['list'].pageDown()
        self.selection_changed()

    # ------------------------------------------------------- genres/search
    def open_genre(self, genre):
        self.genre_back_index = self['list'].getSelectionIndex()
        g = genre.lower()
        local = [r for r in self.all_stations if g in [x.lower()
                                                       for x in r.get('genres', [])]]
        self.sub, self.sub_results = ('genre', genre), local
        self['list'].moveToIndex(0)
        self.apply_view()
        self['status'].setText(_('Loading more stations from laut.fm...'))

        def done(online):
            if not self.alive or self.sub != ('genre', genre):
                return
            merged = self.merge(online, local)
            merged.sort(
                key=lambda r: (-r.get('listeners', 0), r['title'].lower()))
            self.sub_results = merged
            self.apply_view(keep_selection=True)

        def fail(f):
            print('[RadioM] genre: %s' % f)
            if self.alive and self.sub == ('genre', genre):
                self['status'].setText('' if local else _('Nothing found'))
        threads.deferToThread(
            L.stations_by_genre,
            genre,
            self.by_id).addCallback(done).addErrback(fail)

    def merge(self, first, second):
        out, seen = [], set()
        for r in list(first) + list(second):
            k = station_key(r)
            if k not in seen:
                seen.add(k)
                out.append(r)
        return out

    def ask_search(self):
        self.session.openWithCallback(
            self.search_done, VirtualKeyBoard,
            title=_('Search: station, artist, genre, city...'),
            text=settings.data.get('last_search', ''))

    def search_done(self, text):
        if text is None:
            return
        text = text.strip()
        if not text:
            return
        settings.data['last_search'] = text
        settings.save()
        ql = text.lower()
        local = [
            r for r in self.all_stations if ql in (
                r['title'] +
                ' ' +
                r['id'] +
                ' ' +
                ' '.join(
                    r.get(
                        'genres',
                        [])) +
                ' ' +
                r.get(
                    'format',
                    '') +
                ' ' +
                r.get(
                    'desc',
                    '') +
                ' ' +
                r.get(
                    'location',
                    '') +
                ' ' +
                r.get(
                    'djs',
                    '')).lower()]
        self.tab = 'search'
        self.sub, self.sub_results = ('search', text), local
        self['list'].moveToIndex(0)
        self.apply_view()
        self['status'].setText(_('Searching on laut.fm...'))

        def done(online):
            if not self.alive or self.sub != ('search', text):
                return
            self.sub_results = self.merge(online, local)
            self.apply_view(keep_selection=True)

        def fail(f):
            print('[RadioM] search: %s' % f)
            if self.alive and self.sub == ('search', text):
                self['status'].setText(
                    _('Online search not available, local results only') if local else _('Nothing found'))
        threads.deferToThread(
            L.search_stations,
            text,
            self.by_id).addCallback(done).addErrback(fail)

    def load_near(self, refresh=False):
        stations = list(self.all_stations)
        loc = settings.data.get('location')

        def work():
            location = loc if (loc and not refresh) else L.get_location()
            if not location:
                return None, []
            return location, L.stations_near(stations, location)

        def done(result):
            location, near = result
            if location:
                settings.data['location'] = location
                settings.save()
            self.near_results = near
            if self.alive and self.tab == 'near' and not self.sub:
                self.apply_view()
                if not location:
                    self['status'].setText(_('Position not available'))
        threads.deferToThread(work).addCallback(done)

    # -------------------------------------------------------------- actions
    def key_ok(self):
        rec = self.selected()
        if self.kind == 'genres':
            if rec:
                self.open_genre(rec['genre'])
            return
        if not rec:
            if self.tab == 'search':
                self.ask_search()
            return
        if settings.data.get('player') == 'movie':
            NowPlaying.stop(self.session)
            settings.add_recent(rec)
            self.session.open(Playstream2, rec['title'], rec['url'])
            return
        idx = self['list'].getSelectionIndex()
        self.session.openWithCallback(
            self.player_closed, RadioMPlayer, self.view, idx)

    def player_closed(self, index=None):
        if self.tab == 'recent' and not self.sub:
            self.view = list(settings.data.get('recent', []))
        self['list'].fill(self.view, self.kind)
        if index is not None and 0 <= index < len(self.view):
            self['list'].moveToIndex(index)
        self.update_nowplaying()
        self.selection_changed()

    def toggle_fav(self):
        rec = self.selected()
        if not rec or self.kind == 'genres':
            return
        added = settings.toggle_fav(rec)
        idx = self['list'].getSelectionIndex()
        if self.tab == 'fav' and not self.sub:
            self.apply_view()
        else:
            self['list'].fill(self.view, self.kind)
            self['list'].moveToIndex(idx)
            self.selection_changed()
        self['status'].setText(_('Added to favourites')
                               if added else _('Removed from favourites'))

    def show_details(self):
        if time() - self.last_info < 1:
            return      # same key delivered by two contexts
        self.last_info = time()
        rec = self.selected()
        if not rec:
            return
        if self.kind == 'genres':
            self.session.open(
                MessageBox,
                '%s\n\n%s' %
                (rec['genre'],
                 _('%d stations in the list') %
                    rec['count']),
                MessageBox.TYPE_INFO)
            return
        lines = [rec['title'], '']
        for label, key in ((_('Genres'), 'genres'), (_('Format'), 'format'),
                           (_('Description'), 'desc'), (_('Location'), 'location'),
                           (_('DJ'), 'djs')):
            val = rec.get(key)
            if isinstance(val, list):
                val = ', '.join(val)
            if val:
                lines.append('%s: %s' % (label, val))
        if rec.get('src') == 'laut':
            lines.append(
                '%s: %d' %
                (_('Listeners now'),
                 rec.get(
                    'listeners',
                    0)))
            lines.append('%s: https://laut.fm/%s' % (_('Page'), rec['id']))
        lines.append('%s: %s' % (_('Stream'), rec['url']))
        self.session.open(MessageBox, '\n'.join(lines), MessageBox.TYPE_INFO)

    def open_menu(self):
        menu = [
            (_('Search'), 'search'),
            (_('Genres'), 'genres'),
            (_('Local playlists'), 'files'),
            (_('Update my position (Near you)'), 'location'),
            (_('Player: %s') % dict(PLAYERS).get(settings.data.get('player'), 'GStreamer'), 'player'),
            (_('Reload station list'), 'reload'),
            (_('About, updates and donations'), 'about'),
        ]
        if NowPlaying.rec:
            menu.insert(0, (_('Stop playback'), 'stop'))
        if self.update_info and updater.is_newer(self.update_info['version']):
            menu.insert(
                0, (_('Install update %s') %
                    self.update_info['version'], 'update'))
        self.session.openWithCallback(
            self.menu_done,
            ChoiceBox,
            title=_('RadioM menu'),
            list=menu)

    def menu_done(self, choice):
        if not choice:
            return
        action = choice[1]
        if action == 'search':
            self.set_tab('search')
        elif action == 'genres':
            self.set_tab('genres')
        elif action == 'files':
            files = sorted(f for f in listdir(PLAYLISTS) if f.endswith(
                '.txt')) if exists(PLAYLISTS) else []
            if not files:
                self.session.open(
                    MessageBox, _('No .txt playlist in %s') %
                    PLAYLISTS, MessageBox.TYPE_INFO, timeout=5)
                return
            self.session.openWithCallback(
                self.file_done, ChoiceBox, title=_('Local playlists'),
                list=[(f.replace('.txt', ''), f) for f in files])
        elif action == 'location':
            self.tab, self.sub, self.near_results = 'near', None, None
            self.apply_view()
            self.load_near(refresh=True)
        elif action == 'player':
            keys = [p[0] for p in PLAYERS]
            cur = settings.data.get('player', '4097')
            nxt = keys[(keys.index(cur) + 1) %
                       len(keys)] if cur in keys else keys[0]
            settings.data['player'] = nxt
            settings.save()
            self['status'].setText(_('Player: %s') % dict(PLAYERS)[nxt])
        elif action == 'reload':
            self.reload_stations()
        elif action == 'stop':
            NowPlaying.stop(self.session)
            self.player_closed(self['list'].getSelectionIndex())
        elif action == 'about':
            self.open_about()
        elif action == 'update':
            start_update(
                self.session,
                self.update_info,
                self['status'].setText)

    def file_done(self, choice):
        if choice:
            self.sub = ('file', choice[1])
            self.sub_results = L.read_txt_playlist(PLAYLISTS, choice[1])
            self['list'].moveToIndex(0)
            self.apply_view()

    def open_about(self):
        self.session.open(RadioMAbout, self.update_info)

    def exit(self):
        if self.sub:
            back_to_genres = self.sub[0] == 'genre'
            self.sub = None
            self.apply_view()
            if back_to_genres:
                self['list'].moveToIndex(self.genre_back_index)
                self.selection_changed()
            return
        if self.tab != 'top':
            self.set_tab('top')
            return
        self.alive = False
        self.logo_timer.stop()
        NowPlaying.stop(self.session)
        self.close()

    # -------------------------------------------------------------- updates
    def _update_checked(self, info):
        if not self.alive or not info:
            return
        self.update_info = info
        if not updater.is_newer(info['version']):
            return
        if settings.data.get('update_mode') == 'auto':
            start_update(self.session, info, self['status'].setText)
            return
        self['status'].setText(
            _('Update %s available: MENU to install') %
            info['version'])
        self.session.openWithCallback(
            lambda yes: yes and start_update(
                self.session,
                info,
                self['status'].setText),
            MessageBox,
            _('RadioM %s is available on GitHub.\n\n%s\n\nInstall it now?') %
            (info['version'],
             info['changelog']),
            MessageBox.TYPE_YESNO,
            timeout=20,
            default=False)


# --------------------------------------------------------------------------
#  About / updates / donations
# --------------------------------------------------------------------------

class RadioMAbout(Screen):

    def __init__(self, session, update_info=None):
        self.skin = load_skin('radiom_about.xml')
        Screen.__init__(self, session)
        self.setTitle(_('About RadioM'))
        self.info = update_info
        self.alive = True
        self['version'] = Label(_('Version %s') % __version__)
        self['latest'] = Label('')
        self['credits'] = Label(
            _('Created by Lululla') + '\n' +
            _('Stations and data: laut.fm (User Generated Radio)') + '\n' +
            _('Cover art: iTunes Search API') + '\n' +
            _('License: GNU GPL v2'))
        self['features'] = Label(
            _('Thousands of web radios sorted by live listeners, favourites, '
              'online search, genres, stations near you, cover art, '
              'recently played songs and sleep timer.'))
        self['repo'] = Label('github.com/' + updater.GITHUB_REPO)
        self['updmode'] = Label('')
        self['donate'] = Label(
            _('Do you like RadioM? Offer a coffee to the developer!'))
        self['keys_hint'] = Label(
            _('Keys 1-6: Top, Favourites, Recent, Near you, Genres, Search  \u00b7  0: this screen'))
        self['scan'] = Label(_('Scan the code with your phone camera'))
        self['thanks'] = Label('\u2665  ' + _('Thank you!'))
        self['qr1_label'] = Label('PayPal')
        self['qr2_label'] = Label('Ko-fi')
        self['key_red'] = Label(_('Close'))
        self['key_green'] = Label(_('Check update'))
        self['key_yellow'] = Label(_('Update mode'))
        self['key_blue'] = Label(_('Changelog'))
        self['actions'] = ActionMap(
            ['OkCancelActions', 'ColorActions'],
            {'cancel': self.close_screen, 'red': self.close_screen, 'ok': self.close_screen,
             'green': self.check, 'yellow': self.cycle_mode, 'blue': self.changelog}, -1)
        self.onLayoutFinish.append(self.start)

    def start(self):
        self.show_mode()
        if self.info:
            self.show_info()
        else:
            self.check()

    def show_mode(self):
        self['updmode'].setText(
            _('Automatic updates: %s') %
            dict(UPDATE_MODES).get(
                settings.data.get(
                    'update_mode',
                    'notify')))

    def show_info(self):
        info = self.info
        if not info:
            self['latest'].setText(_('GitHub not reachable'))
            return
        when = (' (%s)' % info['date']) if info.get('date') else ''
        if updater.is_newer(info['version']):
            self['latest'].setText(
                _('New version %s available%s: press GREEN') %
                (info['version'], when))
            self['key_green'].setText(_('Install %s') % info['version'])
        else:
            self['latest'].setText(
                _('Up to date: latest release is %s%s') %
                (info['version'], when))
            self['key_green'].setText(_('Check update'))

    def check(self):
        if self.info and updater.is_newer(self.info['version']):
            start_update(self.session, self.info, self['latest'].setText)
            return
        self['latest'].setText(_('Checking GitHub...'))

        def done(info):
            if self.alive:
                self.info = info
                self.show_info()
        threads.deferToThread(updater.check_latest).addCallback(done)

    def cycle_mode(self):
        keys = [m[0] for m in UPDATE_MODES]
        cur = settings.data.get('update_mode', 'notify')
        settings.data['update_mode'] = keys[(keys.index(
            cur) + 1) % len(keys)] if cur in keys else 'notify'
        settings.save()
        self.show_mode()

    def changelog(self):
        if self.info and self.info.get('changelog'):
            self.session.open(
                MessageBox,
                _('RadioM %s\n\n%s') %
                (self.info['version'],
                 self.info['changelog']),
                MessageBox.TYPE_INFO)

    def close_screen(self):
        self.alive = False
        self.close()


# --------------------------------------------------------------------------
#  Now playing screen
# --------------------------------------------------------------------------

class RadioMPlayer(Screen):

    def __init__(self, session, stations, index):
        self.skin = load_skin('radiom80.xml')
        Screen.__init__(self, session)
        self.setTitle('RadioM')
        self.stations = stations
        self.index = index
        self.rec = stations[index]
        self.alive = True
        self.fetching = False
        self.song_key = ''
        self.song_start = 0
        self.song_len = 0
        self.next_refresh = 0
        self.station_logo = None

        self['backdrop'] = Pixmap()
        self['cover'] = Pixmap()
        self['stlogo'] = Pixmap()
        self['station'] = Label('')
        self['station_info'] = Label('')
        self['label_now'] = Label(_('NOW PLAYING'))
        self['title'] = Label('')
        self['artist'] = Label('')
        self['album'] = Label('')
        self['progress'] = ProgressBar()
        self['elapsed'] = Label('')
        self['duration'] = Label('')
        self['label_history'] = Label(_('RECENTLY PLAYED'))
        self['history'] = Label('')
        self['coming'] = Label('')
        self['listeners'] = Label('')
        self['state'] = Label('')
        self['key_red'] = Label(_('Back'))
        self['key_green'] = Label(_('Stop'))
        self['key_yellow'] = Label(_('Favourite'))
        self['key_blue'] = Label('')
        self['key_menu'] = Label(_('Sleep timer'))
        self['key_lr'] = Label(_('Prev / next station'))

        self.img_backdrop = ImageWidget(self['backdrop'])
        self.img_cover = ImageWidget(self['cover'])
        self.img_logo = ImageWidget(self['stlogo'])

        self.tick_timer = make_timer(self.tick)
        self.events = ServiceEventTracker(screen=self, eventmap={
            iPlayableService.evUpdatedInfo: self.icy_update,
        })

        self['actions'] = ActionMap(
            ['OkCancelActions', 'ColorActions', 'DirectionActions',
             'MenuActions', 'ChannelSelectBaseActions'],
            {
                'ok': self.toggle_play,
                'green': self.toggle_play,
                'cancel': self.back,
                'red': self.back,
                'yellow': self.toggle_fav,
                'blue': self.switch_player,
                'menu': self.sleep_menu,
                'left': self.prev_station,
                'right': self.next_station,
                'prevBouquet': self.prev_station,
                'nextBouquet': self.next_station,
                'up': lambda: None,
                'down': lambda: None,
            }, -1)
        self.onLayoutFinish.append(self.start)
        self.onClose.append(self.cleanup)

    def start(self):
        self.img_backdrop.show(join(skin_path, 'bg_player.jpg'))
        self.img_cover.show(DEFAULT_LOGO)
        self.load_station(autoplay=True)
        self.tick_timer.start(1000, False)

    # -------------------------------------------------------------- station
    def load_station(self, autoplay=False):
        rec = self.rec
        self.song_key = ''
        self.song_len = 0
        self.next_refresh = 0
        self['station'].setText(rec['title'])
        info = [
            x for x in (
                ', '.join(
                    rec.get(
                        'genres', [])[
                        :4]), rec.get('location')) if x]
        self['station_info'].setText('  ·  '.join(info) or rec.get('desc', ''))
        self['title'].setText(rec['title'])
        self['artist'].setText(rec.get('format') or _('Live stream'))
        for k in ('album', 'history', 'coming', 'elapsed', 'duration'):
            self[k].setText('')
        self['label_history'].setText('')
        self['progress'].setValue(0)
        self['listeners'].setText(
            _('%d listening') %
            rec.get(
                'listeners',
                0) if rec.get('src') == 'laut' else '')
        self['key_yellow'].setText(
            _('Remove fav.') if settings.is_fav(rec) else _('Favourite'))
        self['key_blue'].setText(
            dict(PLAYERS).get(
                settings.data.get('player'),
                'GStreamer'))
        self.station_logo = None
        if rec.get('logo'):
            url = rec['logo']

            def logo_done(path):
                if self.alive and self.rec.get('logo') == url and path:
                    self.station_logo = path
                    self.img_logo.show(path)
                    if not self.song_key:
                        self.img_cover.show(path)
            threads.deferToThread(L.download_logo, url).addCallback(logo_done)
        else:
            self['stlogo'].hide()
        if autoplay and not NowPlaying.is_playing(rec):
            self.play()
        self.update_state()

    def play(self):
        try:
            NowPlaying.play(
                self.session,
                self.rec,
                settings.data.get(
                    'player',
                    '4097'))
        except Exception as e:
            print('[RadioM] play error: %s' % e)
            self['state'].setText(_('Playback error'))
        self.update_state()

    def toggle_play(self):
        if NowPlaying.is_playing(self.rec):
            NowPlaying.stop(self.session)
        else:
            self.play()
        self.update_state()

    def update_state(self):
        playing = NowPlaying.is_playing(self.rec)
        self['key_green'].setText(_('Stop') if playing else _('Play'))
        parts = [_('▶ Playing') if playing else _('■ Stopped')]
        if NowPlaying.sleep_end:
            parts.append(_('sleep in %d min') %
                         max(1, int((NowPlaying.sleep_end - time()) / 60 + 0.5)))
        self['state'].setText('   '.join(parts))

    def step(self, delta):
        if len(self.stations) < 2:
            return
        self.index = (self.index + delta) % len(self.stations)
        self.rec = self.stations[self.index]
        self.load_station(autoplay=True)

    def prev_station(self):
        self.step(-1)

    def next_station(self):
        self.step(1)

    def toggle_fav(self):
        added = settings.toggle_fav(self.rec)
        self['key_yellow'].setText(
            _('Remove fav.') if added else _('Favourite'))

    def switch_player(self):
        keys = [p[0] for p in PLAYERS if p[0] != 'movie']
        cur = settings.data.get('player', '4097')
        nxt = keys[(keys.index(cur) + 1) %
                   len(keys)] if cur in keys else keys[0]
        settings.data['player'] = nxt
        settings.save()
        self['key_blue'].setText(dict(PLAYERS)[nxt])
        if NowPlaying.is_playing(self.rec):
            self.play()

    def sleep_menu(self):
        opts = [(_('Off'), 0)] + [(_('%d minutes') % m, m)
                                  for m in (15, 30, 45, 60, 90, 120)]
        self.session.openWithCallback(
            self.sleep_done,
            ChoiceBox,
            title=_('Sleep timer'),
            list=opts)

    def sleep_done(self, choice):
        if choice is not None:
            NowPlaying.set_sleep(choice[1])
            self.update_state()

    # ----------------------------------------------------------- song info
    def tick(self):
        if not self.alive:
            return
        now = time()
        if self.rec.get(
                'src') == 'laut' and not self.fetching and now >= self.next_refresh:
            self.fetching = True
            station_id = self.rec['id']
            d = threads.deferToThread(L.fetch_song_info, station_id)
            d.addCallback(self.song_info_done, station_id)
            d.addBoth(self._fetch_finished)
        if self.song_len > 0:
            elapsed = min(self.song_len, max(0, now - self.song_start))
            self['progress'].setValue(int(elapsed * 100 / self.song_len))
            self['elapsed'].setText(fmt_time(elapsed))
            self['duration'].setText('-' + fmt_time(self.song_len - elapsed))
        if NowPlaying.sleep_end or (not NowPlaying.is_playing(
                self.rec) and self['key_green'].getText() == _('Stop')):
            self.update_state()

    def _fetch_finished(self, result):
        self.fetching = False
        return None

    def song_info_done(self, info, station_id):
        if not self.alive or station_id != self.rec.get('id'):
            return
        now = time()
        song = info.get('song') or {}
        if info.get('listeners') is not None:
            self['listeners'].setText(_('%d listening') % info['listeners'])
        if info.get('next'):
            self['coming'].setText(
                _('Coming up: %s') %
                ', '.join(
                    info['next']))
        if song and song.get('type', 'song') == 'song':
            artist = (song.get('artist') or {}).get('name', '') or ''
            title = song.get('title', '') or ''
            album = song.get('album', '') or ''
            year = song.get('releaseyear')
            start = L.parse_laut_time(song.get('started_at', ''))
            end = L.parse_laut_time(song.get('ends_at', ''))
            length = song.get('length') or 0
            if start and end and 20 < end - start < 3600:
                length = end - start
            # if the box clock is badly off, fall back to local timing
            if not start or not (-5 < now - start < (length or 900) + 60):
                start = None
            key = artist + '|' + title
            if key != self.song_key:
                self.song_key = key
                self.set_song(
                    artist, title, ('%s (%s)' %
                                    (album, year)) if album and year else album)
                self.song_start = start or now
            self.song_len = length or 0
            if end and now < end < now + 1800 and start:
                self.next_refresh = end + 3
            else:
                self.next_refresh = now + 30
        else:
            self.next_refresh = now + 30
        self.show_history(info.get('history') or [], song)

    def set_song(self, artist, title, album=''):
        self['title'].setText(title or self.rec['title'])
        self['artist'].setText(artist)
        self['album'].setText(album or '')
        key = artist + '|' + title

        def done(result):
            cover, backdrop = result
            if self.alive and key == self.song_key:
                self.img_cover.show(cover or self.station_logo or DEFAULT_LOGO)
                self.img_backdrop.show(
                    backdrop or join(
                        skin_path, 'bg_player.jpg'))
        threads.deferToThread(
            L.fetch_cover, artist, title, self.rec.get(
                'logo', '')).addCallback(done)

    def show_history(self, history, current):
        lines = []
        cur_id = (current or {}).get('id')
        for s in history:
            if cur_id and s.get('id') == cur_id:
                continue
            artist = (s.get('artist') or {}).get('name', '')
            title = s.get('title', '')
            if not title:
                continue
            ts = L.parse_laut_time(s.get('started_at', ''))
            hhmm = strftime('%H:%M', localtime(ts)) if ts else '     '
            lines.append('%s   %s – %s' % (hhmm, artist, title))
            if len(lines) >= 5:
                break
        self['history'].setText('\n'.join(lines))
        self['label_history'].setText(_('RECENTLY PLAYED') if lines else '')

    def icy_update(self):
        """Stream title tag (works for any Shoutcast/Icecast stream)."""
        if self.rec.get('src') == 'laut' and self.song_key:
            return
        try:
            service = self.session.nav.getCurrentService()
            info = service and service.info()
            tag = info.getInfoString(
                iServiceInformation.sTagTitle) if info else ''
        except Exception:
            tag = ''
        if not tag:
            return
        if ' - ' in tag:
            artist, title = tag.split(' - ', 1)
        else:
            artist, title = '', tag
        key = artist + '|' + title
        if key != self.song_key:
            self.song_key = key
            self.song_len = 0
            self['progress'].setValue(0)
            self['elapsed'].setText('')
            self['duration'].setText('')
            self.set_song(artist.strip(), title.strip())

    # ---------------------------------------------------------------- exit
    def back(self):
        self.close(self.index)

    def cleanup(self):
        self.alive = False
        self.tick_timer.stop()


# --------------------------------------------------------------------------
#  Fallback full-screen player (MoviePlayer skin)
# --------------------------------------------------------------------------

class Playstream2(Screen, InfoBarMenu, InfoBarBase, InfoBarSeek,
                  InfoBarNotifications, InfoBarShowHide):
    STATE_PLAYING = 1
    STATE_PAUSED = 2

    def __init__(self, session, name, url):
        Screen.__init__(self, session)
        self.skinName = 'MoviePlayer'
        InfoBarMenu.__init__(self)
        InfoBarNotifications.__init__(self)
        InfoBarBase.__init__(self)
        InfoBarShowHide.__init__(self)
        self['actions'] = ActionMap(
            ['WizardActions', 'MoviePlayerActions', 'EPGSelectActions',
             'MediaPlayerSeekActions', 'ColorActions',
             'InfobarShowHideActions', 'InfobarSeekActions', 'InfobarActions'],
            {
                'leavePlayer': self.stop,
                'back': self.stop,
                'playpauseService': self.playpauseService,
            }, -1)
        self.allowPiP = False
        self.is_playing = False
        InfoBarSeek.__init__(self, actionmap='MediaPlayerSeekActions')
        self.name = name
        self.url = url
        self.state = self.STATE_PLAYING
        self.srefOld = self.session.nav.getCurrentlyPlayingServiceReference()
        self.onLayoutFinish.append(self.openPlay)

    def openPlay(self):
        try:
            url = self.url.replace(':', '%3a').replace(' ', '%20')
            sref = eServiceReference('4097:0:2:0:0:0:0:0:0:0:' + url)
            sref.setName(self.name)
            self.session.nav.stopService()
            self.session.nav.playService(sref)
            self.is_playing = True
        except Exception as e:
            print('[RadioM] openPlay error: %s' % e)

    def stop(self, text=''):
        try:
            self.is_playing = False
            self.session.nav.stopService()
            if self.srefOld:
                self.session.nav.playService(self.srefOld)
        except Exception as e:
            print('[RadioM] stop error: %s' % e)
        Utils.aspect_manager.restore_aspect()
        self.close()

    def playpauseService(self):
        if self.state == self.STATE_PLAYING:
            self.session.nav.pause(True)
            self.state = self.STATE_PAUSED
        else:
            self.session.nav.pause(False)
            self.state = self.STATE_PLAYING


# backwards compatible names (other plugins/skins may reference them)
radiom1 = RadioMMain
radiom80 = RadioMPlayer


def main(session, **kwargs):
    session.open(RadioMMain)


def Plugins(**kwargs):
    return PluginDescriptor(
        name='RadioM',
        description=_('Thousands of web radios, favourites, covers') +
        ' V.' +
        __version__,
        where=[
            PluginDescriptor.WHERE_PLUGINMENU,
            PluginDescriptor.WHERE_EXTENSIONSMENU],
        icon='plugin.png',
        fnc=main,
    )
