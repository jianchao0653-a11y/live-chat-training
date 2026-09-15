import importlib.util
from pathlib import Path
import unittest

SCRIPT=Path(__file__).with_name('web_design_tokens_check.py')
SPEC=importlib.util.spec_from_file_location('web_design_tokens_check',SCRIPT)
CHECK=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CHECK)


TOKENS=':root{--font:12px;--color:#fff;--radius:8px}'
HTML='<link rel="stylesheet" href="/design-tokens.css"><link rel="stylesheet" href="/style.css">'


class WebDesignTokenTests(unittest.TestCase):
    def errors(self,style,html=HTML,tokens=TOKENS):
        return CHECK.check_text(tokens,style,html,enforce_topology=False)

    def test_valid_component_tokens(self):
        style='a{color:var(--color);font-size:var(--font);border-radius:var(--radius);font-family:inherit}@media(min-width:1450px){}@media(max-width:1150px){}@media(max-width:900px){}@media(max-width:600px){}@media(prefers-reduced-motion:reduce){}'
        self.assertEqual(self.errors(style),[])

    def test_rejects_raw_color_and_font_size(self):
        errors=self.errors('a{color:#fff;font-size:12px}')
        self.assertTrue(any('Raw color' in error for error in errors))
        self.assertTrue(any('Raw font size' in error for error in errors))

    def test_rejects_raw_non_circular_radius(self):
        self.assertTrue(any('Raw radius' in error for error in self.errors('a{border-radius:8px}')))
        self.assertFalse(any('Raw radius' in error for error in self.errors('a{border-radius:50%}')))

    def test_rejects_undefined_variable(self):
        self.assertTrue(any('Undefined' in error for error in self.errors('a{color:var(--missing)}')))

    def test_requires_token_stylesheet_first(self):
        html='<link href="/style.css"><link href="/design-tokens.css">'
        self.assertTrue(any('before style.css' in error for error in self.errors('',html)))


if __name__=='__main__':unittest.main()
