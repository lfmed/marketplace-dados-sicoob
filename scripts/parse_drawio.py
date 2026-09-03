import html, re, sys

path = "/Users/leandro.medeiros/Marketplacededados/Modelo - Motores Governança e Acesso.drawio.html"
data = open(path, encoding="utf-8").read()

# Extract data-mxgraph attribute content
m = re.search(r'data-mxgraph="(.*?)"></div>', data, re.S)
if not m:
    m = re.search(r'data-mxgraph="(.*)"', data, re.S)
raw = m.group(1)
# Unescape HTML entities (attribute uses &quot; etc.)
decoded = html.unescape(raw)
# Now decoded is JSON-ish with \n and \" ; extract xml field
xm = re.search(r'"xml":"(.*)"\}?$', decoded, re.S)
# The xml value is escaped with \" and \n
xml_raw = xm.group(1) if xm else decoded
# Undo JSON string escaping
xml = xml_raw.encode().decode('unicode_escape')
# strip trailing junk after </mxfile>
end = xml.rfind('</mxfile>')
if end != -1:
    xml = xml[:end+len('</mxfile>')]
open("/Users/leandro.medeiros/Marketplacededados/scripts/model.xml","w",encoding="utf-8").write(xml)
print("XML length:", len(xml))
print(xml[:1500])
