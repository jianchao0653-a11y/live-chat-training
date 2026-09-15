"""Resource color references and exact registered vector geometry exemptions."""
from pathlib import Path
import re
import xml.etree.ElementTree as ET

RES=Path('native/android/res')
ANDROID='{http://schemas.android.com/apk/res/android}'
ICONS={'drawable/ic_lens_launcher_foreground.xml','mipmap-anydpi/ic_launcher.xml','mipmap-anydpi/ic_launcher_round.xml'}
GEOMETRY={'viewportWidth':{'108'},'viewportHeight':{'108'},'strokeWidth':{'5.5'},
          'scaleX':{'1.5'},'scaleY':{'1.5'},'pivotX':{'54'},'pivotY':{'54'}}
SCALAR_DESIGN={'alpha','fillAlpha','strokeAlpha','duration','startOffset','textScaleX',
               'letterSpacing','lineSpacingMultiplier','shadowDx','shadowDy','shadowRadius'}


def check_resources(root):
    errors=[];parsed={}
    for path in sorted((root/RES).rglob('*.xml')):
        name=path.relative_to(root/RES).as_posix()
        try:parsed[name]=ET.parse(path).getroot()
        except ET.ParseError as e:errors.append(name+': invalid XML: '+str(e))
    colors={}
    for name,tree in parsed.items():
        for node in tree.findall('color'):
            key=node.get('name');value=(node.text or '').strip()
            if key in colors:errors.append('Duplicate color '+str(key))
            colors[key]=value
            if name!='values/design_token_colors.xml' and not value.startswith('@color/'):
                errors.append(name+': color must reference generated semantic color: '+str(key))
    def resolved(key,seen=()):
        if key not in colors or key in seen:
            errors.append('Undefined/cyclic resource color: '+key);return
        value=colors[key]
        if value.startswith('@color/'):resolved(value.split('/',1)[1],seen+(key,))
    for key in colors:resolved(key)
    for name,tree in parsed.items():
        for node in tree.iter():
            attrs=dict(node.attrib)
            if node.tag=='item':attrs['itemText']=(node.text or '').strip()
            if node.tag=='dimen' and not (node.text or '').strip().startswith('@dimen/'):
                errors.append(name+': unregistered dimension definition '+str(node.get('name')))
            for attr,value in attrs.items():
                key=attr.removeprefix(ANDROID)
                if value.startswith('@color/'):resolved(value.split('/',1)[1])
                if re.fullmatch(r'#[\da-fA-F]{3,8}',value):errors.append(name+': hardcoded color '+key)
                if key in SCALAR_DESIGN and re.fullmatch(r'-?[\d.]+',value) and float(value)!=0:
                    errors.append(name+': unregistered scalar design value '+key+'='+value)
                if key=='pathData' and name in ICONS:continue
                if re.fullmatch(r'-?[\d.]+(?:dp|dip|sp|px)',value):
                    unit_exempt=name in ICONS and key in ('width','height') and value==('108dp' if name.startswith('drawable/') else '48dp')
                    if not unit_exempt and value not in ('0dp','0sp','0px'):errors.append(name+': unregistered dimension '+key+'='+value)
                if key in GEOMETRY and not (name in ICONS and value in GEOMETRY[key]):
                    errors.append(name+': unregistered vector geometry '+key+'='+value)
    return {'errors':errors,'scope':[(RES/name).as_posix() for name in parsed]}
