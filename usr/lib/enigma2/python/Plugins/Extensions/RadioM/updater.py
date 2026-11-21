# -*- coding: utf-8 -*-
"""
RadioM - self update from GitHub.

The repository workflow (.github/workflows/autotag.yml) creates a GitHub
Release "vX.Y" every time __version__ changes. We read the latest release,
download its source tarball and copy the plugin folder in place.
No opkg/apt needed, so it works the same on OE images and DreamOS.

All functions are blocking: run them with threads.deferToThread.
"""
from __future__ import print_function

import os
import shutil
import tarfile
from os.path import dirname, exists, isdir, join, normpath
from re import sub

import requests

from . import __version__

GITHUB_REPO = 'OwnerPlugins/Radio-80-s'
RELEASE_API = 'https://api.github.com/repos/%s/releases/latest' % GITHUB_REPO
TAGS_API = 'https://api.github.com/repos/%s/tags' % GITHUB_REPO
MAIN_TARBALL = 'https://github.com/%s/archive/refs/heads/main.tar.gz' % GITHUB_REPO
INSTALLER_SH = 'https://raw.githubusercontent.com/%s/main/installer.sh' % GITHUB_REPO
PLUGIN_SUBDIR = 'usr/lib/enigma2/python/Plugins/Extensions/RadioM'
PLUGIN_DIR = dirname(os.path.abspath(__file__))
TMP_TAR = '/tmp/radiom_update.tar.gz'
TMP_DIR = '/tmp/radiom_update'
HEADERS = {'User-Agent': 'RadioM/%s (Enigma2)' % __version__,
           'Accept': 'application/vnd.github+json'}


def version_tuple(v):
    out = []
    for p in str(v).strip().lstrip('vV').split('.'):
        try:
            out.append(int(sub(r'\D', '', p) or 0))
        except ValueError:
            out.append(0)
    while out and out[-1] == 0:
        out.pop()
    return tuple(out)


def is_newer(remote, local=__version__):
    return version_tuple(remote) > version_tuple(local)


def clean_changelog(text):
    lines = []
    for ln in (text or '').replace('\r', '').split('\n'):
        ln = ln.strip()
        if not ln or ln.startswith('##'):
            continue
        # "- message (abc1234)" -> "- message"
        ln = sub(r'\s*\([0-9a-f]{7,40}\)$', '', ln)
        lines.append(ln)
    return '\n'.join(lines[:15])


def check_latest():
    """Return {'version', 'changelog', 'date', 'tarball', 'source'} or None."""
    try:
        r = requests.get(RELEASE_API, headers=HEADERS, timeout=10)
        if r.status_code == 200:
            data = r.json()
            tag = data.get('tag_name', '')
            return {
                'version': tag.lstrip('vV'),
                'changelog': clean_changelog(data.get('body', '')),
                'date': (data.get('published_at') or '')[:10],
                'tarball': 'https://github.com/%s/archive/refs/tags/%s.tar.gz' % (GITHUB_REPO, tag),
                'source': 'release',
            }
        print('[RadioM] release api: HTTP %s' % r.status_code)
    except Exception as e:
        print('[RadioM] release api error: %s' % e)
    # fallback: version line of installer.sh on main
    try:
        r = requests.get(INSTALLER_SH, headers=HEADERS, timeout=10)
        version, changelog = '', ''
        for line in r.text.split('\n'):
            if line.startswith('version='):
                version = line.split("'")[1]
            elif line.startswith('changelog='):
                changelog = line.split("'")[1].replace('\\n', '\n').strip()
        if version:
            return {'version': version, 'changelog': changelog, 'date': '',
                    'tarball': MAIN_TARBALL, 'source': 'main'}
    except Exception as e:
        print('[RadioM] installer.sh check error: %s' % e)
    return None


def _safe_members(tar, prefix):
    for m in tar.getmembers():
        name = m.name
        if not name.startswith(prefix):
            continue
        if m.issym() or m.islnk() or m.isdev():
            continue
        rel = normpath(name[len(prefix):]).lstrip('/')
        if rel.startswith('..') or os.path.isabs(rel):
            continue
        if '__pycache__' in rel.split('/') or rel.endswith('.pyc'):
            continue
        yield m, rel


def install_tarball(url):
    """Download + install. Returns (ok, message)."""
    try:
        r = requests.get(url, headers={'User-Agent': HEADERS['User-Agent']}, timeout=60, stream=True)
        r.raise_for_status()
        with open(TMP_TAR, 'wb') as f:
            for chunk in r.iter_content(65536):
                f.write(chunk)
        with tarfile.open(TMP_TAR, 'r:gz') as tar:
            prefix = None
            for name in tar.getnames():
                if name.endswith(PLUGIN_SUBDIR + '/plugin.py'):
                    prefix = name[:-len('plugin.py')]
                    break
            if not prefix:
                return False, 'plugin.py not found in archive'
            if exists(TMP_DIR):
                shutil.rmtree(TMP_DIR)
            os.makedirs(TMP_DIR)
            count = 0
            for m, rel in _safe_members(tar, prefix):
                target = join(TMP_DIR, rel)
                if m.isdir():
                    if not isdir(target):
                        os.makedirs(target)
                    continue
                src = tar.extractfile(m)
                if src is None:
                    continue
                if not isdir(dirname(target)):
                    os.makedirs(dirname(target))
                with open(target, 'wb') as out:
                    shutil.copyfileobj(src, out)
                count += 1
        if not exists(join(TMP_DIR, 'plugin.py')) or count < 5:
            return False, 'incomplete archive'
        # copy over the running installation (user files are kept)
        for root, dirs, files in os.walk(TMP_DIR):
            rel = os.path.relpath(root, TMP_DIR)
            dest = PLUGIN_DIR if rel == '.' else join(PLUGIN_DIR, rel)
            if not isdir(dest):
                os.makedirs(dest)
            for fn in files:
                shutil.copy2(join(root, fn), join(dest, fn))
        # stale bytecode of the old version
        cache = join(PLUGIN_DIR, '__pycache__')
        if isdir(cache):
            shutil.rmtree(cache, ignore_errors=True)
        for fn in os.listdir(PLUGIN_DIR):
            if fn.endswith(('.pyc', '.pyo')):
                try:
                    os.remove(join(PLUGIN_DIR, fn))
                except Exception:
                    pass
        os.system('sync')
        return True, '%d files' % count
    except Exception as e:
        print('[RadioM] update failed: %s' % e)
        return False, str(e)
    finally:
        for p in (TMP_TAR, TMP_DIR):
            try:
                if isdir(p):
                    shutil.rmtree(p)
                elif exists(p):
                    os.remove(p)
            except Exception:
                pass
