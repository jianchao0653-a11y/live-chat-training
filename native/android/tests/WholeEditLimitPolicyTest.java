package com.conversationlens.ime;

public final class WholeEditLimitPolicyTest {
    private static int assertions;
    private static void check(boolean condition, String message) {
        assertions++;
        if (!condition) throw new AssertionError(message);
    }
    private static String repeat(String value, int count) {
        StringBuilder text = new StringBuilder();
        for (int i = 0; i < count; i++) text.append(value);
        return text.toString();
    }
    private static String edit(String destination, int replaceStart, int replaceEnd,
                               CharSequence source, int start, int end, int maximum) {
        CharSequence replacement = WholeEditLimitPolicy.filter(source, start, end, destination, replaceStart, replaceEnd, maximum);
        CharSequence inserted = replacement == null ? source.subSequence(start, end) : replacement;
        return destination.substring(0, replaceStart) + inserted + destination.substring(replaceEnd);
    }
    public static void main(String[] args) {
        String longPaste = repeat("字", 3997) + "不要联系";
        check(longPaste.length() == 4001, "synthetic paste crosses the conversation limit by one");
        check(edit("", 0, 0, longPaste, 0, longPaste.length(), 4000).isEmpty(), "oversized initial paste is wholly rejected, never leaving a shortened negative instruction");
        String original = "对方：暂时不聊。";
        check(edit(original, 3, 7, longPaste, 0, longPaste.length(), 4000).equals(original), "rejected replacement preserves selected text and both surrounding regions");
        check(edit(original, original.length(), original.length(), longPaste, 0, longPaste.length(), 4000).equals(original), "rejected append preserves all previous approved text");
        for (int maximum : new int[]{1000, 2000, 4000, 12000}) {
            String exact = repeat("甲", maximum - 4) + "不要联系";
            check(edit("", 0, 0, exact, 0, exact.length(), maximum).equals(exact), "all assistant fields accept exact limit including complete negative phrase");
            check(edit(exact, maximum, maximum, "乙", 0, 1, maximum).equals(exact), "all assistant fields reject one more unit without altering prior content");
        }

        check(edit("abcdef", 1, 5, "XY", 0, 2, 6).equals("aXYf"), "selection replacement subtracts replaced length");
        check(edit("abcdef", 2, 4, "UVWX", 0, 4, 8).equals("abUVWXef"), "replacement at exact resulting limit accepted");
        check(edit("abcdef", 2, 4, "UVWXY", 0, 5, 8).equals("abcdef"), "oversized replacement does not delete the selected original range");
        check(edit("abcd", 1, 3, "XX你好YY", 2, 4, 4).equals("a你好d"), "source start/end count only the actual composed edit range");
        check(edit("abcd", 1, 3, "XX你好再见YY", 2, 6, 4).equals("abcd"), "oversized source range is rejected whole");
        check(edit("abcdef", 2, 4, "", 0, 0, 3).equals("abef"), "deletion remains available in an already oversized legacy draft");
        check(edit("abcd", 0, 4, "", 0, 0, 4).isEmpty(), "clearing a field remains possible");

        String emoji = "\uD83D\uDE42";
        check(emoji.length() == 2, "supplementary code point uses two service-compatible UTF-16 units");
        check(edit("甲", 1, 1, emoji, 0, 2, 2).equals("甲"), "one remaining unit cannot split a surrogate pair");
        check(edit("甲", 1, 1, emoji, 0, 2, 3).equals("甲" + emoji), "whole surrogate pair accepted at exact limit");
        check(edit("甲" + emoji + "乙", 1, 3, "不会", 0, 2, 4).equals("甲不会乙"), "replacing a supplementary character respects its two-unit selected length");
        check(edit("", 0, 0, "e\u0301", 0, 2, 1).isEmpty(), "over-limit combining sequence is wholly rejected, not reduced to its base letter");
        check(edit("", 0, 0, "e\u0301", 0, 2, 2).equals("e\u0301"), "accepted combining sequence is unchanged");

        // Composition updates replace the previous composition instead of appending to it.
        String composing = edit("对方：", 3, 3, "bu", 0, 2, 7);
        check(composing.equals("对方：bu"), "short composing buffer accepted");
        composing = edit(composing, 3, composing.length(), "buyao", 0, 5, 7);
        check(composing.equals("对方：bu"), "over-limit composition preserves the previous whole composition");
        composing = edit(composing, 3, composing.length(), "不要", 0, 2, 7);
        check(composing.equals("对方：不要"), "committing a shorter Chinese candidate remains possible after rejected composing update");
        check(edit(composing, 3, composing.length(), "不要联系我", 0, 5, 7).equals(composing), "oversized composed candidate never loses its final words");

        StyledSequence styled = new StyledSequence("原选区", "retained-style");
        CharSequence rejection = WholeEditLimitPolicy.filter("过长的替换", 0, 5, styled, 0, 3, 3);
        check(rejection instanceof StyledSequence, "rejection retains destination subsequence type instead of stripping span-capable metadata");
        check(((StyledSequence) rejection).style.equals("retained-style") && rejection.toString().equals("原选区"), "selected text and metadata preserved on rejection");
        check(WholeEditLimitPolicy.filter(styled, 0, 3, "", 0, 0, 3) == null, "accepted styled/composing source is returned untouched to Android");

        ConversationContinuationPolicy continuation = new ConversationContinuationPolicy();
        ConversationContinuationPolicy.Binding binding = new ConversationContinuationPolicy.Binding("customer", "pair", "host", "scene", "connection");
        check(continuation.start(binding, 100), "synthetic continuation starts");
        ConversationContinuationPolicy.Request first = continuation.prepare(binding, repeat("甲", 3997), "关心近况", "context", "first", true, 101).request;
        check(continuation.finish(binding, first, 102), "first long approved fragment commits");
        String next = edit("", 0, 0, "不要联系", 0, 4, 4000);
        check(next.equals("不要联系"), "second fragment remains complete before cumulative validation");
        ConversationContinuationPolicy.Decision decision = continuation.prepare(binding, next, "关心近况", "context2", "second", true, 103);
        check(decision.code == ConversationContinuationPolicy.Code.LIMIT_REACHED && !decision.canSend(), "cumulative overflow still refused by continuation without clipping new fragment");
        check(continuation.approvedText().equals(first.text), "cumulative refusal retains previous approved history");
        System.out.println("WHOLE_EDIT_LIMIT_POLICY_PASS (" + assertions + " assertions)");
    }

    /** Stand-in verifies that policy does not discard Android Spanned's subsequence object. */
    private static final class StyledSequence implements CharSequence {
        private final String text, style;
        StyledSequence(String text, String style) { this.text = text; this.style = style; }
        public int length() { return text.length(); }
        public char charAt(int index) { return text.charAt(index); }
        public CharSequence subSequence(int start, int end) { return new StyledSequence(text.substring(start, end), style); }
        public String toString() { return text; }
    }
}
