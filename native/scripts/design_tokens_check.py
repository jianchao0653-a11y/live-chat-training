"""Android design-token gate (stdlib only, no build/device access).

Run python native/scripts/design_tokens_check.py. --write-resources deliberately
regenerates only the two theme colors; normal checks never modify source files.
This is a bounded Java syntax guard, not a replacement for compilation/review.
"""
import argparse
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
JAVA = Path('native/android/java/com/conversationlens/ime')
SCOPE = ['LensStyle.java', 'KeyboardAssistantPanel.java', 'ImeAssistantPanel.java', 'ImeCustomerDetailsPanel.java',
         'LensImeService.java', 'SetupActivity.java', 'LibraryActivity.java', 'AssistantActivity.java']
LAYOUTS = {
    'ImePanelLayout': {'ROSTER_MAX_DP', 'ROSTER_MIN_DP', 'ROSTER_SCREEN_FRACTION',
        'ASSISTANT_MAX_DP', 'ASSISTANT_MIN_DP', 'ASSISTANT_SCREEN_FRACTION',
        'DETAILS_MAX_DP', 'DETAILS_MIN_DP', 'DETAILS_SCREEN_FRACTION',
        'IMAGE_PREVIEW_MAX_DP', 'EDITOR_MIN_LINES', 'ASSISTANT_EDITOR_MAX_LINES', 'DETAILS_EDITOR_MAX_LINES'},
    'KeyboardLayout': {'HEADER_SWITCH_WIDTH_DP', 'VIEWPORT_MIN_DP', 'LANDSCAPE_SCREEN_FRACTION',
        'PORTRAIT_SCREEN_FRACTION', 'NINE_BOARD_MIN_DP', 'SIDE_MIN_DP', 'SIDE_MAX_DP', 'SIDE_SCREEN_FRACTION',
        'LANDSCAPE_PUNCTUATION_WIDTH_DP', 'FULL_ROW_INDENT_DP', 'LANDSCAPE_ROW_DP', 'NINE_ROW_DP', 'FULL_ROW_DP',
        'FONT_GROWTH_MAX_DP', 'FONT_GROWTH_STEP_DP', 'BACKSPACE_WEIGHT', 'RETURN_WEIGHT', 'SPACE_WEIGHT',
        'SHIFT_WEIGHT', 'LANGUAGE_WEIGHT', 'NUMERIC_SPACE_WEIGHT', 'NINE_MAX_LINES', 'KEY_MAX_LINES'},
    'ActivityLayout': {'EDITOR_MIN_LINES', 'LIBRARY_EDITOR_MIN_LINES', 'IMAGE_PREVIEW_MAX_PX'},
}
TOKEN_CLASS = r'(?:LensTokens|'+'|'.join(LAYOUTS)+r')'
TOKEN_REF = TOKEN_CLASS+r'\.[A-Z_0-9]+'
THEME = Path('native/android/res/values/styles.xml')
COLORS = Path('native/android/res/values/design_token_colors.xml')
RESOURCE_COLORS = [('lens_navigation_background','NAVIGATION_BACKGROUND'),('lens_action_primary','ACTION_PRIMARY'),
                   ('lens_launcher_background','LAUNCHER_BACKGROUND'),('lens_launcher_foreground','LAUNCHER_FOREGROUND')]
LEXEMES = re.compile(r'//[^\n]*|/\*[\s\S]*?\*/|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'')
NUMBER = re.compile(r'(?<![\w.])(?:0x[\da-fA-F]+|(?:\d*\.\d+|\d+)(?:[fFdDlL])?)(?!\w)')


def mask(source):
    return LEXEMES.sub(lambda m: ''.join('\n' if c == '\n' else ' ' for c in m[0]), source)


def calls(source):
    """Yield callee and exact argument spans, respecting nested Java syntax."""
    code = mask(source)
    for match in re.finditer(r'\b([\w.]+)\s*\(', code):
        start = match.end()
        stack = ['(']
        args = []
        for i in range(start, len(code)):
            c = code[i]
            if c in '([{':
                stack.append(c)
            elif c in ')]}':
                if not stack or stack[-1] != {')': '(', ']': '[', '}': '{'}[c]:
                    break
                stack.pop()
                if not stack:
                    args.append((start, i))
                    yield match[1], args
                    break
            elif c == ',' and len(stack) == 1:
                args.append((start, i))
                start = i+1


def declarations(source):
    found = {}
    for match in re.finditer(r'static final (int|float|String)\s+([^;]+);', source):
        for assignment in match[2].split(','):
            name, value = assignment.strip().split('=', 1)
            if name in found:
                raise ValueError('Duplicate token '+name)
            found[name.strip()] = value.strip()
    return found


def definitions(root=ROOT):
    source = (root/JAVA/'LensTokens.java').read_text(encoding='utf-8')
    base_start = source.index('private static final class Base {')
    base_end = source.index('\n    }', base_start)
    base = declarations(source[base_start:base_end])
    semantic = declarations(source[base_end:])
    layout = {owner+'.'+k: v for owner in LAYOUTS
              for k,v in declarations((root/JAVA/(owner+'.java')).read_text(encoding='utf-8')).items()}
    raw = {**{'Base.'+k: v for k, v in base.items()},
           **{'LensTokens.'+k: v for k, v in semantic.items()},
           **layout}
    for key, value in semantic.items():
        if not re.fullmatch(r'Base\.[A-Z][A-Z_0-9]*', value):
            raise ValueError('Semantic token must reference Base: '+key)
    resolved = {}
    def resolve(key, visiting=()):
        if key in resolved:
            return resolved[key]
        if key not in raw or key in visiting:
            raise ValueError('Undefined/cyclic token '+key)
        value = raw[key]
        if re.fullmatch(r'(?:Base|'+TOKEN_CLASS+r')\.[A-Z_0-9]+', value):
            value = resolve(value, visiting+(key,))
        elif not re.fullmatch(r'(?:0x[\da-fA-F]+|\d*\.?\d+[fF]?|"[\w-]+")', value):
            raise ValueError('Unsupported token value '+key)
        resolved[key] = value
        return value
    for key in raw:
        resolve(key)
    return raw, resolved


def violations(source, filename, defined):
    code = mask(source)
    errors = []
    def error(offset, message):
        errors.append(f'{filename}:{source.count(chr(10), 0, offset)+1}: {message}')
    for match in re.finditer(r'\b'+TOKEN_CLASS+r'\.[A-Za-z_][\w.]*', code):
        if match[0] not in defined:
            error(match.start(), 'undefined/forbidden token '+match[0])
    for match in re.finditer(r'\bBase\.', code):
        error(match.start(), 'components cannot reference Base')
    for match in re.finditer(r'\b0x[\da-fA-F]{6,8}\b', code):
        if filename == 'EditorPolicy.java' and any(a<=match.start()<b for a,b in
                (m.span() for m in re.finditer(r'\(options & 0x1000000\) != 0',code))):
            continue  # Exact IME_FLAG_NO_PERSONALIZED_LEARNING contract, not a color.
        error(match.start(), 'hardcoded color')
    for match in re.finditer(r'\.\s*(topMargin|bottomMargin|leftMargin|rightMargin|width|height)\s*=\s*(-?\d+(?:\.\d+)?[fF]?)\s*;', code):
        allowed = {'0', '-1', '-2'} if match[1] in ('width', 'height') else {'0'}
        if match[2] not in allowed:
            error(match.start(), 'hardcoded layout field '+match[1])
    # Resolve simple local numeric aliases in design arguments as well as literals.
    aliases = {m[1]: m[2] for m in re.finditer(r'\b(?:int|float|double)\s+(\w+)\s*=\s*(\d+(?:\.\d+)?[fF]?)\s*;', code)}
    for name, spans in calls(source):
        method = name.rsplit('.', 1)[-1]
        values = [source[a:b].strip() for a, b in spans]
        positions = []
        unit = None
        if method == 'dp':
            positions = [len(spans)-1]; unit = '_DP'
        elif method in ('text', 'label') and len(spans) in (3, 4):
            positions = [1 if method == 'text' else 2]; unit = '_SP'
        elif method == 'label' and len(spans) == 2:
            positions = [1]; unit = '_SP'
        elif method == 'styleKey' and len(spans) == 4:
            positions = [3]; unit = '_SP'
        elif method == 'addColumnKey' and len(spans) == 5:
            positions = [4]; unit = '_SP'
        elif method == 'addKey' and len(spans) == 4:
            positions = [3]; unit = '_WEIGHT'
        elif method == 'RelativeSizeSpan':
            positions = [0]; unit = '_FRACTION'
        elif method == 'setAutoSizeTextTypeUniformWithConfiguration':
            positions = [0, 1, 2]; unit = '_SP'
        elif method == 'InsetDrawable' and len(spans) == 5:
            positions = [1, 2, 3, 4]
        elif method == 'setTextSize':
            positions = [len(spans)-1]; unit = '_SP'
        elif method == 'shape' and len(spans) == 4:
            positions = [1, 2]
        elif method.startswith('set') and method in (
                'setPadding', 'setPaddingRelative', 'setMinHeight', 'setMinimumHeight',
                'setMaxHeight', 'setHeight', 'setWidth', 'setMinWidth', 'setMinimumWidth',
                'setMaxWidth', 'setElevation', 'setTranslationZ', 'setCornerRadius',
                'setStroke', 'setTextColor', 'setHintTextColor', 'setBackgroundColor',
                'setColor', 'setMargins', 'setMinLines', 'setMaxLines', 'setAlpha',
                'setLetterSpacing', 'setShadowLayer', 'setDuration', 'setLineSpacing'):
            positions = list(range(len(spans)))
        elif method == 'LayoutParams':
            positions = list(range(len(spans)))
        elif method in ('rgb', 'argb') and name.startswith('Color.'):
            positions = list(range(len(spans)))
        elif method == 'parseColor' and values and values[0].startswith('"'):
            error(spans[0][0], 'hardcoded parsed color')
        elif name == 'Typeface.create' and values and values[0].startswith('"'):
            error(spans[0][0], 'hardcoded font family')
        for index in positions:
            value = values[index]
            if method == 'addKey' and value == '1':
                continue  # Equal-width keys, not an arbitrary weight exemption.
            if method == 'LayoutParams' and ((index < 2 and value in ('0', '-1', '-2')) or (index == 2 and value == '1')):
                continue
            if method == 'LayoutParams':
                arms = ('0','-1','-2') if index < 2 else ('0','1')
                conditional = re.fullmatch(r'\w+\s*\?\s*(-?\d+)\s*:\s*(-?\d+)', value)
                if conditional and all(v in arms for v in conditional.groups()):
                    continue
            numeric_value = mask(aliases.get(value, value))
            # Conditions select design values; their string-length/index tests
            # are not design sizes. Scan both arms, never exempt arm literals.
            if method == 'styleKey':
                numeric_value = re.sub(r'^[^?:]+\?', '', numeric_value)
            if method == 'dp':
                numeric_value = numeric_value.replace('scale-1f', 'scaleMinusDefault')
            numbers = list(NUMBER.finditer(numeric_value))
            for n in numbers:
                scalar = n[0].rstrip('fFdDlL')
                zero = re.fullmatch(r'0(?:\.0*)?', scalar)
                line_multiplier = method == 'setLineSpacing' and index == 1 and scalar == '1'
                if not zero and not line_multiplier:
                    error(spans[index][0], 'hardcoded design value in '+method+': '+value)
            expected = '_DP' if method == 'shape' and index == 2 else unit
            if method in ('setPadding', 'setPaddingRelative', 'setMinHeight', 'setMaxHeight',
                          'setMinimumHeight', 'setHeight', 'setWidth', 'setMinWidth', 'setMaxWidth'):
                # Android setters consume PX. References converted inside dp()
                # are checked by the dp branch; bare sizes must be explicit PX.
                converted = re.sub(r'(?:LensStyle\.)?dp\([^()]*\)', '', value)
                for ref in re.findall(TOKEN_CLASS+r'\.([A-Z_0-9]+)', converted):
                    if not ref.endswith('_PX'):
                        error(spans[index][0], 'raw Android size requires PX or dp(): '+ref)
            if expected:
                unit_value = value
                if method == 'dp':
                    # Only a measured DP height multiplied by its registered
                    # dimensionless fraction is a valid DP expression.
                    unit_value = re.sub(r'(?:\bscreen|getResources\(\)\.getConfiguration\(\)\.screenHeightDp)\s*\*\s*ImePanelLayout\.(?:ROSTER|ASSISTANT|DETAILS)_SCREEN_FRACTION', 'measuredHeightDp', value)
                    unit_value = re.sub(r'\bwidth\s*\*\s*KeyboardLayout\.SIDE_SCREEN_FRACTION', 'measuredWidthDp', unit_value)
                for ref in re.findall(TOKEN_CLASS+r'\.([A-Z_0-9]+)', unit_value):
                    if not ref.endswith(expected):
                        error(spans[index][0], 'wrong token unit for '+method+': '+ref)
    return errors


def resource_text(resolved):
    return '<?xml version="1.0" encoding="utf-8"?>\n<!-- Generated from LensTokens by design_tokens_check.py resource writer. -->\n<resources>\n'+''.join(
        f'    <color name="{name}">#{int(resolved["LensTokens."+token], 16):08X}</color>\n' for name, token in RESOURCE_COLORS)+'</resources>\n'


def check(root=ROOT):
    raw, resolved = definitions(root)
    errors = []
    owners={'LensTokens.java',*(n+'.java' for n in LAYOUTS)}
    sources = {p.relative_to(root/JAVA).as_posix():p.read_text(encoding='utf-8')
               for p in sorted((root/JAVA).rglob('*.java')) if p.relative_to(root/JAVA).as_posix() not in owners}
    for name, source in sources.items():
        errors += violations(source, name, raw)
    layouts = {owner: (root/JAVA/(owner+'.java')).read_text(encoding='utf-8') for owner in LAYOUTS}
    # Only the enumerated page rules may own literals. Any expansion needs review.
    for owner, layout in layouts.items():
        for key, value in declarations(layout).items():
            if key not in LAYOUTS[owner] and not value.startswith('LensTokens.'):
                errors.append('Unregistered layout literal: '+owner+'.'+key)
    colors = root/COLORS
    if not colors.exists() or colors.read_text(encoding='utf-8') != resource_text(resolved):
        errors.append('Generated theme colors drifted; review LensTokens then use --write-resources')
    if colors.exists():
        try:
            ET.parse(colors)
        except ET.ParseError as failure:
            errors.append('Invalid generated resource XML: '+str(failure))
    items = {e.attrib['name']: e.text for e in ET.parse(root/THEME).findall('./style/item')}
    for key, value in {'android:navigationBarColor': '@color/lens_navigation_background',
                       'android:colorAccent': '@color/lens_action_primary'}.items():
        if items.get(key) != value:
            errors.append('Theme must reference generated semantic color: '+key)
    consumer = '\n'.join(mask(s) for s in [*sources.values(), *layouts.values()])
    # Include other Java consumers for compatibility aliases when reporting usage.
    used = set(re.findall(TOKEN_REF, consumer))
    used.update('LensTokens.'+token for _,token in RESOURCE_COLORS)
    for value in raw.values():
        if value in raw:
            used.add(value)
    unused = sorted(set(raw)-used)
    from design_resource_rules import check_resources
    resources=check_resources(root)
    errors+=resources['errors']
    return {'status': 'FAIL' if errors else 'PASS', 'scope': list(sources)+resources['scope'],
            'errors': errors, 'unusedTokens': unused,
            'tokens': {k: v for k, v in resolved.items() if not k.startswith('Base.')},
            'limitations': 'All main Java consumers and res XML scanned with bounded syntax rules; token/layout definitions checked separately. Not full Java data-flow analysis, human UI or web acceptance.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--write-resources', action='store_true')
    parser.add_argument('--report', type=Path)
    args = parser.parse_args()
    if args.write_resources:
        (ROOT/COLORS).write_text(resource_text(definitions()[1]), encoding='utf-8')
    result = check()
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))
    sys.exit(0 if result['status'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
