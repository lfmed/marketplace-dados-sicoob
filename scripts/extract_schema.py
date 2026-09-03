import re
import xml.etree.ElementTree as ET

xml = open("/Users/leandro.medeiros/Marketplacededados/scripts/model.xml", encoding="utf-8").read()
# Fix mojibake from unicode_escape on utf-8: re-encode latin1 -> utf-8
try:
    xml_fixed = xml.encode('latin1').decode('utf-8')
    xml = xml_fixed
except Exception:
    pass

# Parse all mxCell elements
root = ET.fromstring(xml)
cells = {}
for cell in root.iter('mxCell'):
    cells[cell.get('id')] = cell

# Identify tables (shape=table)
tables = {}
for cid, cell in cells.items():
    style = cell.get('style') or ''
    if 'shape=table' in style:
        tables[cid] = {'name': cell.get('value') or '', 'rows': []}

# Build parent -> children map
children = {}
for cid, cell in cells.items():
    p = cell.get('parent')
    children.setdefault(p, []).append(cid)

def geom_y(cid):
    cell = cells[cid]
    g = cell.find('mxGeometry')
    if g is not None and g.get('y') is not None:
        try: return float(g.get('y'))
        except: return 0.0
    return 0.0

def geom_x(cid):
    cell = cells[cid]
    g = cell.find('mxGeometry')
    if g is not None and g.get('x') is not None:
        try: return float(g.get('x'))
        except: return 0.0
    return 0.0

# For each table, find rows (children with shape=tableRow), then row's cells (partialRectangle) with values
for tid, t in tables.items():
    rows = [c for c in children.get(tid, []) if 'shape=tableRow' in (cells[c].get('style') or '')]
    rows.sort(key=geom_y)
    for rid in rows:
        row_cells = children.get(rid, [])
        # sort by x to get column order (col1 = name, col2 = type, etc.)
        row_cells.sort(key=geom_x)
        vals = [(cells[c].get('value') or '').strip() for c in row_cells]
        vals = [v for v in vals if v != '']
        if vals:
            t['rows'].append(vals)

# Print tables
print("="*80)
print("TABELAS DO MODELO (", len(tables), ")")
print("="*80)
for tid, t in sorted(tables.items(), key=lambda kv: kv[1]['name']):
    print(f"\n### {t['name']}")
    for r in t['rows']:
        print("   - " + " | ".join(r))

# Relationships (edges)
print("\n" + "="*80)
print("RELACIONAMENTOS (edges)")
print("="*80)
def find_table_of(cid, depth=0):
    if cid in tables: return tables[cid]['name']
    cell = cells.get(cid)
    if cell is None or depth>6: return None
    p = cell.get('parent')
    if p in tables: return tables[p]['name']
    return find_table_of(p, depth+1) if p else None

for cid, cell in cells.items():
    if cell.get('edge') == '1':
        s = cell.get('source'); tgt = cell.get('target')
        sn = find_table_of(s) if s else None
        tn = find_table_of(tgt) if tgt else None
        val = (cell.get('value') or '').strip()
        if sn or tn:
            print(f"   {sn}  -->  {tn}   {('['+val+']') if val else ''}")
