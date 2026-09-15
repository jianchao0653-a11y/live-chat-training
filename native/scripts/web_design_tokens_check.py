"""Static gate for the web design-token migration; no browser or runtime data required."""
from pathlib import Path
import hashlib,json,re

ROOT=Path(__file__).resolve().parents[2]
TOKENS=ROOT/'app/public/design-tokens.css'
STYLE=ROOT/'app/public/style.css'
HTML=ROOT/'app/public/index.html'
EXPECTED_SELECTOR_SHA256='fa2cce67ce521fb9e4cdc193e9b130a1e934f3e43173e2e8b6419dfcb95b11af'


def selector_hash(text):
    text=re.sub(r'/\*.*?\*/','',text,flags=re.S)
    headers=[re.sub(r'\s+',' ',match.group(1).strip()) for match in re.finditer(r'([^{}]+)\{',text)]
    return len(headers),hashlib.sha256('\n'.join(headers).encode()).hexdigest()


def check_text(tokens,style,html,enforce_topology=True):
    errors=[]
    token_link=html.find('href="/design-tokens.css"')
    style_link=html.find('href="/style.css"')
    if token_link<0 or style_link<0 or token_link>style_link:errors.append('HTML must load design-tokens.css before style.css')
    if re.search(r'#[0-9a-fA-F]{3,8}\b|\b(?:rgb|hsl)a?\(',style):errors.append('Raw color outside design-tokens.css')
    if re.search(r'font-family:(?!var\(|inherit)',style):errors.append('Raw font family outside design-tokens.css')
    for value in re.findall(r'font-size:([^;}]+)',style):
        if not value.strip().startswith('var('):errors.append('Raw font size outside design-tokens.css: '+value.strip())
    for value in re.findall(r'border-radius:([^;}]+)',style):
        if value.strip()!='50%' and not value.strip().startswith('var('):errors.append('Raw radius outside design-tokens.css: '+value.strip())
    if re.search(r'(?<![-\w])(?:--green|--muted|--line|--paper|--soft|--shadow)(?![-\w])',style):errors.append('Legacy generic design variable remains')
    definitions=set(re.findall(r'(--[a-z0-9-]+)\s*:',tokens))
    references=set(re.findall(r'var\((--[a-z0-9-]+)',tokens+'\n'+style))
    missing=sorted(references-definitions)
    if missing:errors.append('Undefined CSS variables: '+', '.join(missing))
    for breakpoint in ('1450px','1150px','900px','600px'):
        if f'@media(max-width:{breakpoint})' not in style and f'@media(min-width:{breakpoint})' not in style:
            errors.append('Missing responsive breakpoint '+breakpoint)
    if '@media(prefers-reduced-motion:reduce)' not in style:errors.append('Reduced-motion rule missing')
    if enforce_topology:
        count,digest=selector_hash(style)
        if count!=286 or digest!=EXPECTED_SELECTOR_SHA256:errors.append(f'Selector topology changed: {count}/{digest}')
    return errors


def main():
    tokens=TOKENS.read_text(encoding='utf-8')
    style=STYLE.read_text(encoding='utf-8')
    html=HTML.read_text(encoding='utf-8')
    errors=check_text(tokens,style,html)
    result={'status':'PASS' if not errors else 'FAIL','tokenFile':str(TOKENS.relative_to(ROOT)).replace('\\','/'),
            'styleFile':str(STYLE.relative_to(ROOT)).replace('\\','/'),'selectors':selector_hash(style)[0],
            'selectorSha256':selector_hash(style)[1],'errors':errors,
            'limitations':'Static token, source-order and selector-topology gate; browser rendering and human visual review remain separate.'}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    raise SystemExit(0 if not errors else 1)


if __name__=='__main__':main()
