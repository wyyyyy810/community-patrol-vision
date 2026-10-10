import zipfile, re, sys

def to_text(xml):
    # paragraph -> line, table cell -> tab separated, row -> new line
    xml = xml.replace('</w:p>', '\n')
    xml = xml.replace('</w:tr>', '\n')
    xml = xml.replace('</w:tc>', '\t')
    xml = re.sub(r'<w:tab[^>]*/>', '\t', xml)
    xml = re.sub(r'<w:br[^>]*/>', '\n', xml)
    xml = re.sub(r'<[^>]+>', '', xml)
    return xml

def main():
    p = sys.argv[1]
    z = zipfile.ZipFile(p)
    raw = z.read('word/document.xml').decode('utf-8', errors='replace')
    txt = to_text(raw)
    # unescape
    txt = txt.replace('&amp;', '&').replace('&lt;', '<').replace('&gt;', '>').replace('&quot;', '"').replace('&apos;', "'")
    lines = [l.rstrip() for l in txt.split('\n')]
    out = []
    for l in lines:
        if l.strip():
            out.append(l)
    print('\n'.join(out))

main()
