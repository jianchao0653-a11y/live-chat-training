"""Verify a constant-only migration against an immutable explicit source baseline.

Java lexical tokens (including exact strings/operators) must be identical after
expanding semantic constants. This does not claim runtime/pixel verification.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
import design_tokens_check as gate


def lexical(source):
    pattern=r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|\w+|[^\s]'
    return [m[0] for m in re.finditer(pattern,source) if not m[0].startswith(('//','/*'))]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((args.baseline/'receipt.json').read_text(encoding='utf-8'))
    _,resolved=gate.definitions()
    # Every side uses its own source-time definitions. Batch one had literals;
    # later baselines already contain semantic references.
    old_resolved = {}
    if (args.baseline/gate.JAVA/'LensTokens.java').exists():
        token_source=(args.baseline/gate.JAVA/'LensTokens.java').read_text(encoding='utf-8')
        start=token_source.index('private static final class Base {')
        end=token_source.index('\n    }',start)
        raw={'Base.'+k:v for k,v in gate.declarations(token_source[start:end]).items()}
        raw.update({'LensTokens.'+k:v for k,v in gate.declarations(token_source[end:]).items()})
        for owner in gate.LAYOUTS:
            path=args.baseline/gate.JAVA/(owner+'.java')
            if path.exists():raw.update({owner+'.'+k:v for k,v in gate.declarations(path.read_text(encoding='utf-8')).items()})
        def resolve(key):
            value=raw[key]
            return resolve(value) if value in raw else value
        old_resolved={key:resolve(key) for key in raw}
        for relative,digest in manifest['savedFiles'].items():
            if relative.endswith(tuple([n+'.java' for n in gate.LAYOUTS]+['LensTokens.java'])):
                assert hashlib.sha256((args.baseline/relative).read_bytes()).hexdigest()==digest, relative
    def expand(source,definitions):
        edits=[(m.start(),m.end(),definitions[m[0]]) for m in re.finditer(gate.TOKEN_REF,gate.mask(source))]
        for start,end,value in reversed(edits):source=source[:start]+value+source[end:]
        return source
    result={'status':'PASS','baselineApkSha256':manifest['apkSha256'],'checks':{},'sourceHashes':{},
            'scope':'Constant expansion and XML theme color equivalence; not runtime/pixel/quality acceptance'}
    for name in gate.SCOPE:
        relative=(gate.JAVA/name).as_posix()
        old=(args.baseline/relative).read_bytes()
        if hashlib.sha256(old).hexdigest()!=manifest['savedFiles'][relative]:
            raise AssertionError('Baseline modified: '+relative)
        current=(gate.ROOT/relative).read_text(encoding='utf-8')
        # Replace only outside strings/comments, preserving original text exactly.
        same=lexical(expand(old.decode('utf-8'),old_resolved))==lexical(expand(current,resolved))
        result['checks'][relative]='PASS' if same else 'FAIL'
        result['sourceHashes'][relative]=hashlib.sha256((gate.ROOT/relative).read_bytes()).hexdigest()
    relative=gate.THEME.as_posix()
    old_bytes=(args.baseline/relative).read_bytes()
    if hashlib.sha256(old_bytes).hexdigest()!=manifest['savedFiles'][relative]:
        raise AssertionError('Baseline theme modified')
    old=ET.fromstring(old_bytes)
    old_colors_path=args.baseline/gate.COLORS
    if old_colors_path.exists():
        assert hashlib.sha256(old_colors_path.read_bytes()).hexdigest()==manifest['savedFiles'][gate.COLORS.as_posix()]
        old_colors={e.attrib['name']:e.text for e in ET.parse(old_colors_path).getroot()}
        for item in old.findall('./style/item'):
            if (item.text or '').startswith('@color/'):item.text=old_colors[item.text.split('/',1)[1]]
    new=ET.parse(gate.ROOT/gate.THEME).getroot()
    colors={e.attrib['name']:e.text for e in ET.parse(gate.ROOT/gate.COLORS).getroot()}
    for item in new.findall('./style/item'):
        if (item.text or '').startswith('@color/'):
            item.text=colors[item.text.split('/',1)[1]]
    def flatten(root):
        result=[]
        for e in root.iter():
            text=(e.text or '').strip()
            if text.startswith('#'):
                text=text[1:].lower()
                if len(text)==6:text='ff'+text
            result.append((e.tag,sorted(e.attrib.items()),text))
        return result
    result['checks'][relative]='PASS' if flatten(old)==flatten(new) else 'FAIL'
    if 'FAIL' in result['checks'].values():result['status']='FAIL'
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    raise SystemExit(0 if result['status']=='PASS' else 1)


if __name__=='__main__':main()
