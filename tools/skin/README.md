# RadioM skin sources

The skins are designed once at 1920x1080 (`*_fhd.xml`) and scaled to HD/WQHD.

```bash
SKIN=usr/lib/enigma2/python/Plugins/Extensions/RadioM/skin
python3 tools/skin/gen_assets.py $SKIN          # regenerate graphics (needs Pillow + DejaVu fonts)
python3 tools/skin/build_skins.py tools/skin $SKIN   # write radiom.xml / radiom80.xml for hd, fhd, wqhd
```
