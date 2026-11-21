"""Scale the FHD skin templates to hd / wqhd and write them into the plugin."""
import re
import sys

PLUG = '/usr/lib/enigma2/python/Plugins/Extensions/RadioM/skin/'
FACTORS = {'hd': 2 / 3.0, 'fhd': 1.0, 'wqhd': 4 / 3.0}


def scale_xml(xml, f):
    def pair(m):
        a, b = m.group(2).split(',')
        return '%s="%d,%d"' % (m.group(1), round(int(a) * f), round(int(b) * f))
    xml = re.sub(r'\b(position|size)="(-?\d+,-?\d+)"', pair, xml)
    xml = re.sub(r'font="Regular;\s*(\d+)"', lambda m: 'font="Regular;%d"' % round(int(m.group(1)) * f), xml)
    return xml


if __name__ == '__main__':
    tools, out = sys.argv[1], sys.argv[2]
    for src, dst in (('radiom_fhd.xml', 'radiom.xml'), ('radiom80_fhd.xml', 'radiom80.xml'), ('radiom_about_fhd.xml', 'radiom_about.xml')):
        tpl = open(tools + '/' + src).read()
        for res, f in FACTORS.items():
            xml = scale_xml(tpl, f).replace('%SKIN%', PLUG + res)
            open('%s/%s/%s' % (out, res, dst), 'w').write(xml)
    print('ok')
