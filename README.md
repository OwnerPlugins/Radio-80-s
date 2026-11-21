<h1 align="center">📻 RadioM - Enigma2 Radio Plugin</h1>

<p align="center">
  <a href="https://github.com/Belfagor2005/Radio-80-s">
    <img src="https://img.shields.io/badge/Version-1.6-blue.svg" alt="Version">
  </a>

  <a href="https://www.enigma2.net">
    <img src="https://img.shields.io/badge/Enigma2-Plugin-ff6600.svg" alt="Enigma2">
  </a>

  <a href="https://www.python.org">
    <img src="https://img.shields.io/badge/Python-3-blue.svg" alt="Python">
  </a>

  <a href="https://www.gnu.org/licenses/gpl-3.0.html">
    <img src="https://img.shields.io/badge/License-GPLv3-blue.svg" alt="GPLv3">
  </a>
</p>

<p align="center">
  <a href="https://github.com/Belfagor2005">
    <img src="https://komarev.com/ghpvc/?username=Belfagor2005&label=Repository%20Views&color=blueviolet" alt="Visitors">
  </a>
</p>

<p align="center">
  <a href="https://ko-fi.com/lululla">
    <img src="https://img.shields.io/badge/_-Donate-red.svg?logo=githubsponsors&labelColor=555555&style=for-the-badge" alt="Ko-fi">
  </a>

  <a href="https://paypal.me/belfagor2005">
    <img src="https://img.shields.io/badge/_-Donate-green.svg?logo=githubsponsors&labelColor=555555&style=for-the-badge" alt="PayPal">
  </a>
</p>
<div align="center">

<img src="https://raw.githubusercontent.com/Belfagor2005/Radio-80-s/main/usr/lib/enigma2/python/Plugins/Extensions/RadioM/skin/fhd/80s.png" width="150" height="150" alt="RadioM Logo">

**Thousands of web radios from laut.fm on your Enigma2 receiver, with an 80s synthwave look**

</div>

## 📷 Screenshots

<p align="center">
  <img src="screen/1.jpg" width="49%" alt="Top stations">
  <img src="screen/2.jpg" width="49%" alt="Favorites">
</p>
<p align="center">
  <img src="screen/3.jpg" width="49%" alt="Recents">
  <img src="screen/4.jpg" width="49%" alt="near you">
</p>
<p align="center">
  <img src="screen/5.jpg" width="49%" alt="Genrse">
  <img src="screen/6.jpg" width="49%" alt="Now Playing">
</p>
<p align="center">
  <img src="screen/7.jpg" width="49%" alt="About and donations">
</p>

| # | Screen |
|---|---|
| 1 | Top stations sorted by live listeners |
| 2 | Genres (laut.fm top genres + all the others) |
| 3 | Online search |
| 4 | Now playing: cover, progress bar, recently played, coming up |
| 5 | About, updates and donations |

## ✨ What's new in 1.6

- New **synthwave skin** for HD, FHD and WQHD
- **Sections like laut.fm**: Top, Favourites, Recent, Near you, Genres, Search
- **Online search** on laut.fm (station names, descriptions, artists played)
- **Genre pages** that also load stations outside the top list
- **Near you**: stations sorted by distance from your receiver
- **Now playing** screen with cover art, blurred backdrop, progress bar,
  recently played songs, upcoming artists, live listeners and sleep timer
- **Faster list**: shown after the first page, downloaded in parallel and cached across reboots
- **Updates from GitHub Releases** (ask / automatic / off) and an **About** screen with donation QR codes
- Fixes: no more GUI freeze at startup, INFO key on all images, robust network handling
- Translations limited to 15 languages to keep the package light

## 📻 Features

- **Massive station database**: thousands of radio stations from laut.fm, sorted by live listeners
- **Sections**: Top, Favourites, Recent, Near you, Genres, Search (keys **1-6**, **BLUE** = next section)
- **Online search**: stations, artists, genres, cities, merged with the local results
- **Genres**: the 20 laut.fm top genres plus all the others, with the number of stations
- **Near you**: stations within 400 km, sorted by distance (approximate position from the public IP,
  requested only when you open the section)
- **Favourites** and **recently played** stations, saved in `/etc/enigma2/radiom.json`
- **Now playing**: cover art (iTunes), blurred backdrop, title / artist / album, progress bar with
  elapsed and remaining time, last 5 songs, upcoming artists, live listeners
- **Previous / next station** while listening (LEFT / RIGHT or CH+ / CH-)
- **Sleep timer**: 15 to 120 minutes
- **Background playback**: the music keeps playing when you go back to the list,
  the TV channel is restored when you leave the plugin
- **Custom playlists** from local `.txt` files, with the song title read from the stream (ICY)
- **Multiple players**: GStreamer (4097), ExtePlayer3 (5002, with ServiceApp), MoviePlayer
- **Fast startup**: list cached on hdd/usb (or compressed in `/etc/enigma2`) and refreshed in background
- **Self update** from GitHub Releases, with GUI restart
- **Responsive UI**: HD, FHD and WQHD skins

## 🚀 Installation

### Online installer
```bash
wget -q --no-check-certificate https://raw.githubusercontent.com/Belfagor2005/Radio-80-s/main/installer.sh -O - | /bin/sh
```

### IPK Package
```bash
opkg install enigma2-plugin-extensions-radiom_1.6_all.ipk
```

### Manual Installation
```bash
# Copy plugin files
cp -r RadioM /usr/lib/enigma2/python/Plugins/Extensions/

# Restart Enigma2
systemctl restart enigma2
```

## 🎮 Usage

1. **Open** Plugin Menu → RadioM
2. **Choose a section** with keys 1-6 or BLUE
3. **Press OK** on a station to play it, or on a genre to open it
4. **YELLOW** adds or removes a favourite, **INFO** shows the station details
5. **MENU** for search, genres, local playlists, position, player and updates
6. **0** opens About, updates and donations

### Remote keys

| Screen | OK / GREEN | YELLOW | BLUE | MENU | 1-6 / 0 | LEFT / RIGHT |
|---|---|---|---|---|---|---|
| Station list | Play / open genre | Add / remove favourite | Next section | Search, genres, playlists, position, player, update | Sections / About | Page up / down |
| Now playing | Play / stop | Add / remove favourite | Change player | Sleep timer | – | Previous / next station |
| About | Check / install update | Update mode | Changelog | – | – | – |

### Player Selection
- **GStreamer (4097)**: default player, works on every image
- **ExtePlayer3 (5002)**: available when the ServiceApp plugin is installed
- **MoviePlayer**: full screen fallback player

Change it from MENU → Player in the list, or with BLUE in the now playing screen.

## 🛠️ Technical Details

### Supported Platforms
- Enigma2-based receivers (OpenPLi, OpenATV, DreamOS, etc.)
- Python 3.x
- Screen resolutions HD, FHD and WQHD

### File Structure
```
RadioM/
├── plugin.py              # Screens: station list, now playing, about
├── lautapi.py             # laut.fm API, station cache, cover art
├── updater.py             # Self update from GitHub Releases
├── PicLoader.py           # Image handling
├── Console.py             # Console operations
├── locale/                # Translations (15 languages)
├── skin/                  # UI skins
│   ├── hd/                # HD resolution
│   ├── fhd/               # Full HD resolution
│   └── wqhd/              # WQHD resolution
└── Playlists/             # Custom playlists directory
```

### Files on the receiver
| File | Content |
|---|---|
| `/etc/enigma2/radiom.json` | Favourites, recent stations, player, update mode |
| `/media/hdd/radiom/stations.json.gz` | Station list cache (or `/etc/enigma2/radiom_stations.json.gz` without hdd/usb) |
| `/tmp/radiom/` | Logos and cover art cache |
| `/tmp/radiom.log` | Debug log: send it when opening an issue |

## 🔧 Configuration

### Custom Playlists
Create `.txt` files in the `Playlists` directory with the following format:
```
Station Name###http://stream.url
Another Station###http://another.stream.url
```
Open them from MENU → Local playlists.

### Updates
Every time `__version__` changes in `__init__.py`, the workflow `.github/workflows/autotag.yml`
creates a GitHub Release `vX.Y`. RadioM checks the latest release at startup and, depending on the
update mode chosen in the About screen (YELLOW), asks before installing, installs automatically or
never checks. The repository is set in `GITHUB_REPO` inside `updater.py`.

### Skin Customization
The skins are designed at 1920x1080 in `tools/skin/*_fhd.xml` and scaled to HD and WQHD:
```bash
SKIN=usr/lib/enigma2/python/Plugins/Extensions/RadioM/skin
python3 tools/skin/gen_assets.py $SKIN                 # graphics (Pillow + qrcode)
python3 tools/skin/build_skins.py tools/skin $SKIN     # radiom.xml, radiom80.xml, radiom_about.xml
```

### Translations
The workflow `update_translations.yml` updates `locale/` for 15 languages:
en, it, de, fr, es, pt, nl, pl, ru, tr, el, cs, hu, ro, ar.

## 🤝 Contributing

We welcome contributions! Please feel free to submit pull requests or open issues for bugs and feature requests.

### Development Setup
```bash
git clone https://github.com/Belfagor2005/Radio-80-s.git
cd Radio-80-s
# Make your changes and test on Enigma2 receiver
```

## 📄 License

This project is licensed under the GPL v2 License - see the [LICENSE](LICENSE) file for details.

## 🙏 Credits

- **Lululla** - Original concept and development
- **laut.fm** - Radio station data and streams
- **iTunes Search API** - Cover art

## 🔗 Links

- [GitHub Repository](https://github.com/Belfagor2005/Radio-80-s)
- [laut.fm](https://laut.fm)
- [Enigma2 Development Forum](http://www.corvoboys.org)

## 📞 Support

For support and questions:
- Open an issue on GitHub (attach `/tmp/radiom.log`)
- Visit Enigma2 development forums

---

<div align="center">

**Enjoy listening to your favorite radio stations! 📻**

</div>
