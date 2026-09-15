"""Regression examples for design-rule enforcement, using synthetic snippets."""
import unittest
import shutil
import tempfile
from pathlib import Path
import design_tokens_check as gate


class DesignGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.defined, _ = gate.definitions()

    def errors(self, source):
        return gate.violations(source, 'Synthetic.java', self.defined)

    def test_real_hardcoding_routes_rejected(self):
        for source in ('v.setTextSize(14);', 'v.setTextSize(14.0f);',
                       'v.setPadding(0, dp(8), 0, 0);', 'shape(c, color, 12, true);',
                       'v.setMinHeight(48);', 'v.setTextColor(0xff123456);',
                       'v.setTextColor(123);', 'Typeface.create("serif", Typeface.NORMAL);',
                       'v.setTextColor(Color.parseColor("#123456"));',
                       'int color=Color.rgb(12,34,56);',
                       'new LinearLayout.LayoutParams(100,-2);',
                       'new LinearLayout.LayoutParams(0,-2,2);',
                       'p.topMargin=8;', 'p.width=100;',
                       'int size=14; v.setTextSize(size);',
                       'label(body, call("nested, commas", 7), 14, false);',
                       'v.setShadowLayer(2, 0, 0, color);', 'v.setDuration(150);'):
            with self.subTest(source=source):
                self.assertTrue(self.errors(source))

    def test_reference_and_unit_rejected(self):
        for source in ('v.setTextSize(LensTokens.MISSING_SP);',
                       'v.setTextSize(LensTokens.FIELD_RADIUS_DP);',
                       'dp(LensTokens.TEXT_BODY_SP);', 'dp(ImePanelLayout.ROSTER_SCREEN_FRACTION);',
                       'v.setTextSize(LensTokens.Base.SP_14);', 'int x=Base.SP_14;'):
            with self.subTest(source=source):
                self.assertTrue(self.errors(source))

    def test_semantic_references_and_layout_exceptions(self):
        source = '''
        v.setTextSize(LensTokens.TEXT_BODY_SP);
        v.setPadding(0, dp(LensTokens.STACK_GAP_DP), 0, 0);
        v.setElevation(0); v.setMinWidth(0);
        v.setLineSpacing(dp(LensTokens.TEXT_LINE_EXTRA_DP), 1);
        new LinearLayout.LayoutParams(0,-2,1);
        new InputFilter.LengthFilter(60);
        int cap=dp(Math.min(ImePanelLayout.ROSTER_MAX_DP,
            Math.max(ImePanelLayout.ROSTER_MIN_DP,Math.round(screen*ImePanelLayout.ROSTER_SCREEN_FRACTION))));
        // v.setTextSize(999); LensTokens.MISSING
        label(body,"Text containing setPadding(8,8,8,8)",LensTokens.TEXT_BODY_SP,false);
        '''
        self.assertEqual([], self.errors(source))

    def test_nested_call_arguments_preserved(self):
        source='label(body, foo("a,b", new int[]{1,2}), 14, false);'
        spans=next(args for name,args in gate.calls(source) if name=='label')
        self.assertEqual([source[a:b].strip() for a,b in spans],
                         ['body','foo("a,b", new int[]{1,2})','14','false'])

    def test_second_batch_helpers_and_units_rejected(self):
        for source in ('label("title",24);', 'styleKey(button,false,false,25);',
                       'styleKey(button,false,false,label.length()>1?16:22);',
                       'addColumnKey(column,"0","0",action,27);',
                       'addKey(row,"space",action,2.2f);', 'new RelativeSizeSpan(.52f);',
                       'v.setAutoSizeTextTypeUniformWithConfiguration(6,size,1,TypedValue.COMPLEX_UNIT_SP);',
                       'new InsetDrawable(drawable,2,3,2,3);',
                       'new LinearLayout.LayoutParams(insert?-1:48,-2);',
                       'new LinearLayout.LayoutParams(-1,-2,insert?0:2);',
                       'v.setMaxHeight(LensTokens.ACTION_MIN_HEIGHT_DP);',
                       'dp(ActivityLayout.IMAGE_PREVIEW_MAX_PX);',
                       'addKey(row,"space",action,LensTokens.TEXT_BODY_SP);',
                       'new RelativeSizeSpan(KeyboardLayout.SPACE_WEIGHT);',
                       'dp(base+Math.round(Math.min(18f,Math.max(0f,scale-1f)*16f)));'):
            with self.subTest(source=source):self.assertTrue(self.errors(source))

    def test_second_batch_exact_exemptions(self):
        self.assertEqual([],self.errors('''
            styleKey(button,false,false,label.length()>1?LensTokens.KEY_ACTION_TEXT_SP:LensTokens.KEY_LETTER_TEXT_SP);
            addKey(row,"space",action,1);
            addKey(row,"space",action,KeyboardLayout.SPACE_WEIGHT);
            new RelativeSizeSpan(LensTokens.KEY_DIGIT_TEXT_FRACTION);
            v.setAutoSizeTextTypeUniformWithConfiguration(LensTokens.KEY_AUTOSIZE_MIN_SP,size,LensTokens.KEY_AUTOSIZE_STEP_SP,TypedValue.COMPLEX_UNIT_SP);
            new LinearLayout.LayoutParams(insert?-1:0,-2,insert?0:1);
            new LinearLayout.LayoutParams(insert?-1:-2,-2);
            v.setMaxHeight(ActivityLayout.IMAGE_PREVIEW_MAX_PX);
            v.setPadding(LensTokens.OCR_PANEL_PADDING_X_PX,0,LensTokens.OCR_PANEL_PADDING_X_PX,0);
            dp(base+Math.round(Math.min(KeyboardLayout.FONT_GROWTH_MAX_DP,Math.max(0f,scale-1f)*KeyboardLayout.FONT_GROWTH_STEP_DP)));
        '''))

    def test_protocol_exception_is_exact(self):
        source='boolean p=(options & 0x1000000) != 0;'
        self.assertEqual([],gate.violations(source,'EditorPolicy.java',self.defined))
        self.assertTrue(self.errors(source))
        self.assertTrue(gate.violations(source+'v.setTextColor(0x1000000);','EditorPolicy.java',self.defined))

    def test_new_java_and_resource_hardcoding_rejected(self):
        with tempfile.TemporaryDirectory(prefix='lens-design-new-',dir=gate.ROOT/'runtime') as folder:
            root=self.staged(folder)
            path=root/gate.JAVA/'FutureView.java'
            path.write_text('class FutureView {void f(){v.setTextSize(18);}}',encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            path.write_text('class FutureView {}',encoding='utf-8')
            nested=root/gate.JAVA/'future/LensTokens.java'
            nested.parent.mkdir();nested.write_text('class LensTokens {void f(){v.setTextSize(14);}}',encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            nested.write_text('class LensTokens {}',encoding='utf-8')
            resources=root/'native/android/res/values/new.xml'
            resources.write_text('<resources><color name="bad">#ffffff</color></resources>',encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            resources.write_text('<resources><color name="bad">@color/missing</color></resources>',encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            resources.write_text('<resources><color name="bad">@color/bad</color></resources>',encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            resources.write_text('<resources><dimen name="bad">12dp</dimen></resources>',encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])

    def test_vector_geometry_is_not_directory_exemption(self):
        from design_resource_rules import check_resources
        with tempfile.TemporaryDirectory(prefix='lens-design-vector-',dir=gate.ROOT/'runtime') as folder:
            root=self.staged(folder)
            path=root/'native/android/res/drawable/ic_lens_launcher_foreground.xml'
            path.parent.mkdir(exist_ok=True)
            path.write_text('<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="108dp" android:height="108dp" android:viewportWidth="108"><path android:strokeWidth="5.5" android:strokeColor="@color/lens_launcher_foreground"/></vector>',encoding='utf-8')
            self.assertEqual([],check_resources(root)['errors'])
            path.write_text(path.read_text(encoding='utf-8').replace('5.5','6'),encoding='utf-8')
            self.assertTrue(check_resources(root)['errors'])
            path.write_text('<vector xmlns:android="http://schemas.android.com/apk/res/android" android:alpha="0.5"/>',encoding='utf-8')
            self.assertTrue(check_resources(root)['errors'])

    def test_repository_gate(self):
        result=gate.check()
        self.assertEqual([],result['errors'])
        self.assertEqual([],result['unusedTokens'])

    def staged(self, folder):
        root=Path(folder)
        for relative in [gate.JAVA/name for name in gate.SCOPE+['LensTokens.java']+[n+'.java' for n in gate.LAYOUTS]]+[gate.THEME,gate.COLORS]:
            destination=root/relative;destination.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(gate.ROOT/relative,destination)
        return root

    def test_actual_resource_drift_and_invalid_xml_rejected(self):
        with tempfile.TemporaryDirectory(prefix='lens-design-rule-',dir=gate.ROOT/'runtime') as folder:
            root=self.staged(folder)
            resource=root/gate.COLORS
            text=resource.read_text(encoding='utf-8')
            resource.write_text(text.replace('#FF58665F','#FF000000'),encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            resource.write_text('<resources><!-- broken -- comment --></resources>',encoding='utf-8')
            self.assertTrue(any('Invalid generated resource XML' in e for e in gate.check(root)['errors']))

    def test_missing_reference_and_unregistered_layout_rejected(self):
        with tempfile.TemporaryDirectory(prefix='lens-design-rule-',dir=gate.ROOT/'runtime') as folder:
            root=self.staged(folder)
            layout=root/gate.JAVA/'ImePanelLayout.java'
            text=layout.read_text(encoding='utf-8')
            layout.write_text(text.replace('static final int GUTTER_DP=LensTokens.PANEL_GUTTER_DP;',
                                            'static final int GUTTER_DP=9;'),encoding='utf-8')
            self.assertEqual('FAIL',gate.check(root)['status'])
            tokens=root/gate.JAVA/'LensTokens.java'
            text=tokens.read_text(encoding='utf-8')
            tokens.write_text(text.replace('BACKGROUND=Base.GRAY_50','BACKGROUND=Base.UNDEFINED'),encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'Undefined/cyclic'):
                gate.check(root)


if __name__ == '__main__':
    unittest.main()
