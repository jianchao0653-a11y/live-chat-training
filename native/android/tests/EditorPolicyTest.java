package com.conversationlens.ime;

public final class EditorPolicyTest {
    private static int assertions;
    private static void check(boolean value, String message) {
        assertions++;
        if (!value) throw new AssertionError(message);
    }
    public static void main(String[] args) {
        check(EditorPolicy.chinese(1, 0), "ordinary text supports Chinese");
        check(EditorPolicy.chinese(0x20001, 0), "multiline supports Chinese");
        for (int type : new int[]{0x81, 0x91, 0xe1, 0x12}) {
            check(EditorPolicy.privateField(type, 0), "password flag: " + type);
            check(!EditorPolicy.chinese(type, 0), "password must bypass engine");
        }
        check(EditorPolicy.privateField(1, 0x1000000), "NO_PERSONALIZED_LEARNING is honored");
        check(!EditorPolicy.chinese(1, 0x1000000), "no-learning field bypasses engine");
        for (int type : new int[]{0, 2, 3, 4, 0x11, 0x21, 0xd1})
            check(!EditorPolicy.chinese(type, 0), "raw/number/phone/date/URL/email field: " + type);
        check(EditorPolicy.newline(0x20001), "explicit multiline accepts newline");
        check(!EditorPolicy.newline(1), "single-line field has no send action");
        check(!EditorPolicy.newline(2), "number field has no send action");
        System.out.println("EDITOR_POLICY_PASS (" + assertions + " assertions)");
    }
}
