package com.conversationlens.ime;

import com.conversationlens.ime.KeyboardAssistantPolicy.Mode;
import com.conversationlens.ime.KeyboardAssistantPolicy.Segment;
import com.conversationlens.ime.KeyboardAssistantPolicy.Target;

public final class KeyboardAssistantPolicyTest {
    private static int assertions;
    private static void check(boolean value,String message) { assertions++;if(!value)throw new AssertionError(message); }
    public static void main(String[] args) {
        KeyboardAssistantPolicy policy=new KeyboardAssistantPolicy();
        KeyboardAssistantPolicy.Route host=policy.snapshot();check(policy.accepts(host),"normal typing targets host");
        policy.open(Mode.NEW,true);check(policy.target()==Target.BLOCKED,"panel without editor must not type into chat");
        check(!policy.accepts(host),"in-flight host result cannot enter customer form");
        policy.focus(4201);KeyboardAssistantPolicy.Route search=policy.snapshot();check(policy.accepts(search),"search accepts its own result");
        policy.focus(4202);check(!policy.accepts(search),"search composition cannot enter new customer name");
        KeyboardAssistantPolicy.Route name=policy.snapshot();policy.blur(4201);check(policy.accepts(name),"stale blur cannot revoke new field");
        policy.blur(4202);check(policy.target()==Target.BLOCKED,"lost field focus must not fall through to host");
        check(!policy.accepts(name),"late Rime result after blur is discarded");
        policy.focus(4202);name=policy.snapshot();policy.invalidate();check(!policy.accepts(name),"selection changes revoke pending composition");
        name=policy.snapshot();policy.open(Mode.MAINTAIN,true);check(!policy.accepts(name),"mode change revokes local result");
        policy.focus(4202);name=policy.snapshot();policy.reset();check(!policy.accepts(name),"host lifecycle cannot accept customer names");
        check(policy.target()==Target.HOST&&policy.mode()==Mode.NORMAL,"explicit normal mode restores host");
        policy.open(Mode.NEW,false);check(policy.mode()==Mode.NORMAL,"private or unsupported host cannot open assistant");
        policy.focus(4201);check(policy.target()==Target.HOST,"internal field cannot hijack normal mode");
        for(Mode mode:new Mode[]{Mode.NEW,Mode.MAINTAIN}) {
            check(KeyboardAssistantPolicy.visible(mode,Segment.UNCLASSIFIED),"unclassified remains discoverable");
            check(!KeyboardAssistantPolicy.selectable(mode,Segment.UNCLASSIFIED),"unclassified never inferred selectable");
        }
        check(KeyboardAssistantPolicy.selectable(Mode.NEW,Segment.NEW),"new customer selectable in new mode");
        check(!KeyboardAssistantPolicy.visible(Mode.NEW,Segment.MAINTAIN),"maintained customer omitted from new roster");
        check(KeyboardAssistantPolicy.selectable(Mode.MAINTAIN,Segment.MAINTAIN),"maintained customer selectable in maintain mode");
        check(Segment.parse("missing")==Segment.UNCLASSIFIED,"unknown server segment not guessed");
        System.out.println("KEYBOARD_ASSISTANT_POLICY_PASS ("+assertions+" assertions)");
    }
}
