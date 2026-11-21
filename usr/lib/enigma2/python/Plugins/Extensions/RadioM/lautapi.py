# -*- coding: utf-8 -*-
"""
RadioM - laut.fm API, cache and artwork helpers.

Everything in this module is blocking and is meant to run in a worker
thread (twisted.internet.threads.deferToThread). No enigma2 GUI calls here.
"""
from __future__ import print_function

import calendar
import codecs
import gzip
import hashlib
import json
import math
import os
import sys
import threading
from datetime import datetime
from os import listdir, makedirs, remove, stat
from os.path import exists, getsize, isdir, ismount, join
from re import sub
from time import time

import requests

try:
    from urllib.parse import quote
except ImportError:
    from urllib import quote

from . import __version__

API = 'https://api.laut.fm'
API_HTTP = 'http://api.laut.fm'
LOG_FILE = '/tmp/radiom.log'
LAST_ERROR = ''
CACHE_DIR = '/tmp/radiom'
STATIONS_CACHE = join(CACHE_DIR, 'stations.json')    # old test builds
PARALLEL_PAGES = 6


def cache_file():
    """Station list cache that survives a reboot: on a mounted hdd/usb
    if there is one, otherwise compressed in /etc/enigma2."""
    for d in ('/media/hdd', '/media/usb', '/media/mmc'):
        try:
            if isdir(d) and ismount(d) and os.access(d, os.W_OK):
                return join(d, 'radiom', 'stations.json.gz')
        except Exception:
            pass
    return '/etc/enigma2/radiom_stations.json.gz'


CACHE_VERSION = 3
CACHE_TTL = 6 * 3600
LISTENERS_TTL = 15 * 60

# browser-like User-Agent: some servers refuse unknown clients
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  'Chrome/125.0.0.0 Safari/537.36',
    'Accept': 'application/json, text/plain, */*',
    # no "br": requests cannot decode brotli without an extra module
    'Accept-Encoding': 'gzip, deflate',
}

# "Top-Genres" as shown on laut.fm/genres
TOP_GENRES = ['Pop', 'Rock', 'Charts', 'Schlager', '80er', '90er', 'Oldies', 'Rap',
              'Hip-Hop', 'Dance & Electronic', 'Techno', 'House', 'Dance',
              'Alternative', 'Hits', 'Metal', '70er', '00er', 'EDM', 'Disco']


def q(text):
    if sys.version_info[0] < 3 and isinstance(text, unicode):  # noqa: F821
        text = text.encode('utf-8')
    return quote(text, safe='')


def ensure_dir(path):
    try:
        if not exists(path):
            makedirs(path)
    except Exception as e:
        print('[RadioM] mkdir %s: %s' % (path, e))


try:
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except Exception:
    pass

_verify = [True]
BASE = [API]          # switched to http:// if https is blocked on the box


def log(msg):
    """Small debug log, useful when something does not work on a box."""
    line = '%s %s' % (datetime.now().strftime('%H:%M:%S'), msg)
    print('[RadioM] ' + line)
    try:
        with codecs.open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except Exception:
        pass


def reset_log():
    try:
        with codecs.open(LOG_FILE, 'w', encoding='utf-8') as f:
            f.write('RadioM %s - python %s - requests %s\n' % (
                __version__, sys.version.split()[0], getattr(requests, '__version__', '?')))
    except Exception:
        pass


def short_error(e):
    name = e.__class__.__name__
    if isinstance(e, requests.exceptions.HTTPError) and e.response is not None:
        return 'HTTP %s' % e.response.status_code
    return name


_local = threading.local()


def session():
    """One keep-alive session per thread: avoids a new TLS handshake for
    every page, which is slow on the boxes."""
    sess = getattr(_local, 'session', None)
    if sess is None:
        try:
            sess = requests.Session()
        except Exception:
            sess = requests
        _local.session = sess
    return sess


def http_get(url, timeout=10, stream=False, headers=None):
    """GET with automatic fallback when the box cannot verify SSL
    certificates (old CA bundle or wrong clock)."""
    headers = headers or HEADERS
    get = session().get
    try:
        r = get(url, headers=headers, timeout=timeout, stream=stream, verify=_verify[0])
    except requests.exceptions.SSLError as e:
        if not _verify[0]:
            raise
        log('SSL error, retrying without certificate check: %s' % e)
        _verify[0] = False
        r = get(url, headers=headers, timeout=timeout, stream=stream, verify=False)
    r.raise_for_status()
    return r


def http_json(url, timeout=10):
    r = http_get(url, timeout)
    try:
        return r.json()
    except ValueError:
        return json.loads(r.content.decode('utf-8', 'ignore'))


def http_file(url, target, timeout=15):
    r = http_get(url, timeout, stream=True, headers={'User-Agent': HEADERS['User-Agent']})
    r.raise_for_status()
    tmp = target + '.part'
    with open(tmp, 'wb') as f:
        for chunk in r.iter_content(32768):
            f.write(chunk)
    try:
        remove(target)
    except Exception:
        pass
    os.rename(tmp, target)
    return target


def md5(text):
    return hashlib.md5(text.encode('utf-8')).hexdigest()


def parse_laut_time(value):
    """'2023-04-14 13:14:15 +0200' -> unix epoch (or None)."""
    try:
        base = datetime.strptime(value[:19], '%Y-%m-%d %H:%M:%S')
        off = value[19:].strip() or '+0000'
        sign = -1 if off.startswith('-') else 1
        off = off.lstrip('+-').replace(':', '')
        seconds = int(off[0:2]) * 3600 + int(off[2:4]) * 60
        return calendar.timegm(base.timetuple()) - sign * seconds
    except Exception:
        return None


# --------------------------------------------------------------------------
#  Stations
# --------------------------------------------------------------------------

def slim_station(st):
    name = st.get('name') if isinstance(st, dict) else None
    if not name:
        return None
    images = st.get('images') or {}

    def num(v):
        try:
            return float(v)
        except (TypeError, ValueError):
            return None
    return {
        'id': name,
        'title': st.get('display_name') or name,
        'url': st.get('stream_url') or 'https://stream.laut.fm/%s' % name,
        'logo': images.get('station_640x640') or images.get('station_120x120') or images.get('station') or '',
        'genres': st.get('genres') or [],
        'format': (st.get('format') or '').strip(),
        'desc': (st.get('description') or '').strip()[:300],
        'location': (st.get('location') or '').strip(),
        'djs': (st.get('djs') or '').strip(),
        'lat': num(st.get('lat')),
        'lng': num(st.get('lng')),
        'listeners': 0,
        'src': 'laut',
    }


def collect_stations(obj, out=None):
    """Find laut.fm station objects anywhere in a JSON answer.

    The search endpoint wraps stations in result groups; walking the tree
    keeps us independent from the exact envelope."""
    if out is None:
        out = []
    if isinstance(obj, dict):
        if obj.get('name') and any(k in obj for k in ('stream_url', 'display_name', 'api_urls', 'page_url', 'images')):
            out.append(obj)
            return out
        for v in obj.values():
            collect_stations(v, out)
    elif isinstance(obj, list):
        for v in obj:
            collect_stations(v, out)
    return out


def fetch_listeners():
    data = http_json(BASE[0] + '/listeners', timeout=15)
    return data if isinstance(data, dict) else {}


def apply_listeners(stations, listeners):
    for rec in stations:
        try:
            rec['listeners'] = int(listeners.get(rec['id'], 0))
        except (TypeError, ValueError):
            rec['listeners'] = 0
    stations.sort(key=lambda r: (-r['listeners'], r['title'].lower()))
    return stations


def fetch_all_stations(per_page=100, max_pages=120, progress=None):
    """All laut.fm stations, sorted by listeners.

    The first page is tried with different URLs (https/http, offset/page
    paging) so that one blocked variant does not leave the list empty.
    LAST_ERROR keeps a short reason to show on screen.
    progress(list) is called from the worker thread with partial,
    already sorted results so the GUI can fill the list while loading."""
    global LAST_ERROR
    LAST_ERROR = ''
    stations, seen = [], set()
    lock = threading.Lock()
    listeners = {}

    def snapshot():
        with lock:
            part = [dict(r) for r in stations]
        return apply_listeners(part, listeners)

    def notify():
        if progress:
            try:
                progress(snapshot())
            except Exception as e:
                log('progress error: %r' % e)

    def add(items):
        new = 0
        with lock:
            for st in items:
                rec = slim_station(st)
                if rec and rec['id'] not in seen:
                    seen.add(rec['id'])
                    stations.append(rec)
                    new += 1
        return new

    # (base, paging, limit, extra query). The second one is exactly what
    # RadioM 1.x used, known to work on the boxes.
    attempts = [
        (API, 'offset', per_page, ''),
        (API, 'page', 50, '&order=click&reverse=1'),
        (API, 'page', 50, ''),
        (API_HTTP, 'offset', per_page, ''),
        (API_HTTP, 'page', 50, '&order=click&reverse=1'),
    ]

    def make_url(b, m, limit, extra, index):
        key = 'offset' if m == 'offset' else 'page'
        return '%s/stations?limit=%d&%s=%d%s' % (b, limit, key, index, extra)

    # listeners first (one small call): partial lists are already sorted
    try:
        listeners.update(fetch_listeners())
    except Exception as e:
        log('listeners error: %s %r' % (short_error(e), e))

    chosen = None
    errors = []
    for b, m, limit, extra in attempts:
        url = make_url(b, m, limit, extra, 0 if m == 'offset' else 1)
        try:
            items = collect_stations(http_json(url, timeout=20))
            log('%s -> %d stations' % (url, len(items)))
            if items:
                add(items)
                chosen = [b, m, limit, extra]
                BASE[0] = b
                break
            errors.append('empty answer')
        except Exception as e:
            log('%s -> %s %r' % (url, short_error(e), e))
            errors.append(short_error(e))
    if not stations:
        LAST_ERROR = ', '.join(sorted(set(errors))) or 'no data'
        return []

    notify()
    b, m, limit, extra = chosen

    def fetch_page(page):
        url = make_url(b, m, limit, extra, page * limit if m == 'offset' else page + 1)
        for attempt in (1, 2):
            try:
                return collect_stations(http_json(url, timeout=20))
            except Exception as e:
                log('%s -> %s %r (attempt %d)' % (url, short_error(e), e, attempt))
        return None

    # page 1 alone: tells whether the server honours "offset"
    items = fetch_page(1)
    if items is not None and add(items) == 0 and m == 'offset':
        m = 'page'
        log('offset ignored, switching to page=N')
        items = fetch_page(1)
        if items is not None:
            add(items)
    if items is None or len(items) < limit:
        max_pages = 0
    notify()

    try:
        from concurrent.futures import ThreadPoolExecutor
        pool = ThreadPoolExecutor(PARALLEL_PAGES)
    except Exception:
        pool = None     # python 2: one page at a time
    page = 2
    while page < max_pages:
        batch = list(range(page, min(page + (PARALLEL_PAGES if pool else 1), max_pages)))
        results = list(pool.map(fetch_page, batch)) if pool else [fetch_page(batch[0])]
        done = False
        for items in results:
            if items is None:
                done = True
                continue
            if add(items) == 0 or len(items) < limit:
                done = True
        notify()
        if done:
            break
        page += len(batch)
    if pool:
        pool.shutdown(wait=False)
    log('total stations: %d' % len(stations))
    return apply_listeners(stations, listeners)


def merge_known(found, known_by_id):
    """Turn raw API stations into records, reusing cached listener counts."""
    out, seen = [], set()
    for st in found:
        rec = slim_station(st)
        if not rec or rec['id'] in seen:
            continue
        seen.add(rec['id'])
        known = known_by_id.get(rec['id'])
        if known:
            rec['listeners'] = known.get('listeners', 0)
        out.append(rec)
    return out


def search_stations(query, known_by_id, limit=100):
    """Server side search (station names, descriptions, artists played...)."""
    url = '%s/search/stations?query=%s&limit=%d' % (BASE[0], q(query), limit)
    return merge_known(collect_stations(http_json(url, timeout=15)), known_by_id)


def stations_by_genre(genre, known_by_id, limit=200):
    url = '%s/stations/genre/%s?limit=%d' % (BASE[0], q(genre), limit)
    recs = merge_known(collect_stations(http_json(url, timeout=15)), known_by_id)
    recs.sort(key=lambda r: (-r['listeners'], r['title'].lower()))
    return recs


def load_cache():
    for path in (cache_file(), STATIONS_CACHE):
        try:
            if path.endswith('.gz'):
                with gzip.open(path, 'rb') as f:
                    data = json.loads(f.read().decode('utf-8'))
            else:
                with codecs.open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            if data.get('v') == CACHE_VERSION and data.get('stations'):
                return data.get('ts', 0), data.get('lts', 0), data['stations']
        except Exception:
            pass
    return 0, 0, []


def save_cache(stations, ts=None, lts=None):
    path = cache_file()
    ensure_dir(os.path.dirname(path))
    now = time()
    try:
        raw = json.dumps({'v': CACHE_VERSION, 'ts': ts or now, 'lts': lts or now,
                          'stations': stations}, ensure_ascii=False, separators=(',', ':'))
        tmp = path + '.tmp'
        with gzip.open(tmp, 'wb') as f:
            f.write(raw.encode('utf-8'))
        os.rename(tmp, path)
        log('cache saved: %s (%d stations)' % (path, len(stations)))
    except Exception as e:
        log('cache save error: %r' % e)


def read_txt_playlist(folder, filename):
    out = []
    try:
        with codecs.open(join(folder, filename), 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.strip()
                if '###' not in line:
                    continue
                name, url = line.split('###', 1)
                if name and url:
                    out.append({'id': '', 'title': name.strip(), 'url': url.strip(),
                                'logo': '', 'genres': [], 'format': '',
                                'desc': filename.replace('.txt', ''),
                                'location': '', 'djs': '', 'lat': None, 'lng': None,
                                'listeners': 0, 'src': 'custom'})
    except Exception as e:
        print('[RadioM] playlist error: %s' % e)
    return out


# --------------------------------------------------------------------------
#  "Near you"
# --------------------------------------------------------------------------

def get_location():
    """Approximate position of the box from its public IP."""
    for url, keys in (('https://ipapi.co/json/', ('latitude', 'longitude', 'city')),
                      ('http://ip-api.com/json/', ('lat', 'lon', 'city'))):
        try:
            data = http_json(url, timeout=8)
            lat, lng = float(data[keys[0]]), float(data[keys[1]])
            return {'lat': lat, 'lng': lng, 'city': data.get(keys[2]) or ''}
        except Exception as e:
            print('[RadioM] location %s: %s' % (url, e))
    return None


def distance_km(lat1, lng1, lat2, lng2):
    p = math.pi / 180.0
    a = (0.5 - math.cos((lat2 - lat1) * p) / 2 +
         math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lng2 - lng1) * p)) / 2)
    return 12742 * math.asin(math.sqrt(max(0.0, a)))


def stations_near(stations, loc, max_km=400, limit=150):
    out = []
    for r in stations:
        if r.get('lat') is None or r.get('lng') is None:
            continue
        if r['lat'] == 0 and r['lng'] == 0:
            continue
        d = distance_km(loc['lat'], loc['lng'], r['lat'], r['lng'])
        if d <= max_km:
            rec = dict(r)
            rec['_dist'] = int(round(d))
            out.append(rec)
    out.sort(key=lambda r: (r['_dist'], -r['listeners']))
    return out[:limit]


# --------------------------------------------------------------------------
#  Now playing data
# --------------------------------------------------------------------------

def fetch_song_info(station_id):
    """current song, recently played, upcoming artists, listeners."""
    out = {'song': None, 'history': [], 'listeners': None, 'next': []}
    base = '%s/station/%s' % (BASE[0], q(station_id))
    try:
        out['song'] = http_json(base + '/current_song')
    except Exception as e:
        print('[RadioM] current_song error: %s' % e)
    try:
        hist = http_json(base + '/last_songs')
        out['history'] = hist if isinstance(hist, list) else []
    except Exception as e:
        print('[RadioM] last_songs error: %s' % e)
    try:
        lst = http_json(base + '/listeners')
        out['listeners'] = lst if isinstance(lst, int) else (
            lst.get('listeners') if isinstance(lst, dict) else None)
    except Exception:
        pass
    try:
        nxt = http_json(base + '/next_artists')
        names = []
        for a in (nxt if isinstance(nxt, list) else []):
            n = a.get('name') if isinstance(a, dict) else a
            if n and n not in names:
                names.append(n)
        out['next'] = names[:6]
    except Exception:
        pass
    return out


def download_logo(url):
    """Download a station logo into the cache, return local path."""
    if not url or not url.startswith('http'):
        return None
    ensure_dir(join(CACHE_DIR, 'logos'))
    target = join(CACHE_DIR, 'logos', md5(url) + '.png')
    if exists(target) and getsize(target) > 0:
        return target
    try:
        return http_file(url, target)
    except Exception as e:
        print('[RadioM] logo error: %s' % e)
        return None


def prune_cache(folder, keep=40):
    try:
        files = [join(folder, f) for f in listdir(folder)]
        files.sort(key=lambda p: stat(p).st_mtime, reverse=True)
        for p in files[keep:]:
            remove(p)
    except Exception:
        pass


def normalise_jpeg(path):
    try:
        from PIL import Image
        with Image.open(path) as img:
            img.load()
            if img.format != 'JPEG' or img.mode != 'RGB':
                img.convert('RGB').save(path + '.tmp', 'JPEG', quality=90)
                os.rename(path + '.tmp', path)
        return path
    except Exception as e:
        print('[RadioM] invalid image: %s' % e)
        try:
            remove(path)
        except Exception:
            pass
        return None


def make_backdrop(cover):
    """Small blurred + darkened 16:9 copy of the cover, upscaled by ePicLoad."""
    try:
        from PIL import Image, ImageFilter, ImageEnhance
        target = cover.rsplit('.', 1)[0] + '_bg.jpg'
        if exists(target):
            return target
        with Image.open(cover) as img:
            img = img.convert('RGB')
            w, h = img.size
            crop_h = int(w * 9 / 16.0)
            top = max(0, (h - crop_h) // 2)
            img = img.crop((0, top, w, min(h, top + crop_h))).resize((320, 180))
            img = img.filter(ImageFilter.GaussianBlur(9))
            img = ImageEnhance.Brightness(img).enhance(0.42)
            img.save(target, 'JPEG', quality=85)
        return target
    except Exception as e:
        print('[RadioM] backdrop error: %s' % e)
        return None


def fetch_cover(artist, title, fallback_logo):
    """iTunes artwork -> (cover_path, backdrop_path)."""
    ensure_dir(join(CACHE_DIR, 'covers'))
    cover = None
    query = ('%s %s' % (artist, sub(r'\([^)]*\)|\[[^\]]*\]', '', title))).strip()
    if query:
        target = join(CACHE_DIR, 'covers', md5(query.lower()) + '.jpg')
        if exists(target) and getsize(target) > 2048:
            cover = target
        else:
            for entity in ('song', 'album'):
                try:
                    url = 'https://itunes.apple.com/search?term=%s&entity=%s&limit=1' % (q(query), entity)
                    data = http_json(url)
                    if data.get('resultCount', 0):
                        art = data['results'][0].get('artworkUrl100', '')
                        if art:
                            http_file(art.replace('100x100bb', '600x600bb'), target)
                            cover = normalise_jpeg(target)
                            break
                except Exception as e:
                    print('[RadioM] cover error: %s' % e)
    if not cover:
        cover = download_logo(fallback_logo)
    backdrop = make_backdrop(cover) if cover else None
    prune_cache(join(CACHE_DIR, 'covers'))
    return cover, backdrop
