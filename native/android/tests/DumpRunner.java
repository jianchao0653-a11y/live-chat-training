package com.conversationlens.ime.qa;

import android.app.Activity;
import android.app.Instrumentation;
import android.app.UiAutomation;
import android.accessibilityservice.AccessibilityServiceInfo;
import android.os.Bundle;
import android.graphics.Rect;
import android.view.accessibility.AccessibilityNodeInfo;
import android.view.accessibility.AccessibilityWindowInfo;
import android.util.Xml;
import org.xmlpull.v1.XmlSerializer;
import java.io.StringWriter;

/** Separate emulator-only test APK; not packaged in the input method. */
public final class DumpRunner extends Instrumentation {
    private Bundle arguments;
    @Override public void onCreate(Bundle arguments) { super.onCreate(arguments); this.arguments=arguments; start(); }
    @Override public void onStart() {
        Bundle result = new Bundle();
        try {
            UiAutomation ui = getUiAutomation();
            AccessibilityServiceInfo info = ui.getServiceInfo();
            info.flags |= AccessibilityServiceInfo.FLAG_RETRIEVE_INTERACTIVE_WINDOWS;
            ui.setServiceInfo(info);
            Thread.sleep(250);
            if(arguments.containsKey("hint")){
                boolean changed=false;
                for(AccessibilityWindowInfo window:ui.getWindows())changed|=setText(window.getRoot());
                if(!changed)throw new Exception("Synthetic field not found");
            }
            StringWriter writer = new StringWriter();
            XmlSerializer xml = Xml.newSerializer(); xml.setOutput(writer);
            xml.startTag(null, "hierarchy");
            for (AccessibilityWindowInfo window : ui.getWindows()) node(xml, window.getRoot(), 0);
            xml.endTag(null, "hierarchy"); xml.endDocument();
            result.putString("hierarchy", writer.toString());
            finish(Activity.RESULT_OK, result);
        } catch (Exception error) {
            result.putString("error", error.toString()); finish(Activity.RESULT_CANCELED, result);
        }
    }
    private boolean setText(AccessibilityNodeInfo node){
        if(node==null)return false;
        if("com.conversationlens.ime".contentEquals(node.getPackageName()==null?"":node.getPackageName()) && node.isEditable() && arguments.getString("hint").contentEquals(node.getHintText()==null?"":node.getHintText())){
            Bundle data=new Bundle();data.putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,new String(android.util.Base64.decode(arguments.getString("value"),android.util.Base64.DEFAULT),java.nio.charset.StandardCharsets.UTF_8));
            return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT,data);
        }
        for(int i=0;i<node.getChildCount();i++)if(setText(node.getChild(i)))return true;
        return false;
    }
    private void node(XmlSerializer xml, AccessibilityNodeInfo node, int depth) throws Exception {
        if (node == null || depth > 30) return;
        xml.startTag(null, "node");
        xml.attribute(null, "text", node.getText() == null ? "" : node.getText().toString());
        xml.attribute(null, "class", String.valueOf(node.getClassName()));
        xml.attribute(null, "package", String.valueOf(node.getPackageName()));
        xml.attribute(null, "enabled", String.valueOf(node.isEnabled()));
        xml.attribute(null, "focused", String.valueOf(node.isFocused()));
        xml.attribute(null, "password", String.valueOf(node.isPassword()));
        xml.attribute(null, "checked", String.valueOf(node.isChecked()));
        xml.attribute(null, "hint", node.getHintText()==null?"":node.getHintText().toString());
        Rect bounds = new Rect(); node.getBoundsInScreen(bounds);
        xml.attribute(null, "bounds", "["+bounds.left+","+bounds.top+"]["+bounds.right+","+bounds.bottom+"]");
        for (int i=0;i<node.getChildCount();i++) node(xml,node.getChild(i),depth+1);
        xml.endTag(null,"node");
    }
}
