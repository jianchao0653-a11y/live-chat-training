package com.conversationlens.ime;

/** Reject an over-limit edit whole, never retain only a prefix of supplied text. */
final class WholeEditLimitPolicy {
    private WholeEditLimitPolicy() {}

    /**
     * Mirrors InputFilter's null-means-accept contract without depending on Android.
     * Returning the original destination range preserves a selection's contents when
     * replacement is rejected. subSequence also lets Android retain styled/composing
     * text through its Spanned implementation; converting it to String would not.
     */
    static CharSequence filter(CharSequence source, int start, int end,
                               CharSequence destination, int replaceStart, int replaceEnd,
                               int maximum) {
        if (source == null || destination == null || maximum < 0
                || start < 0 || end < start || end > source.length()
                || replaceStart < 0 || replaceEnd < replaceStart || replaceEnd > destination.length())
            throw new IllegalArgumentException("Invalid edit bounds");
        // Java and the service both use UTF-16 units. Never slice a supplied surrogate pair.
        long resultingLength = (long) destination.length() - (replaceEnd - replaceStart) + (end - start);
        // Deletion must remain possible even if an older draft is already over the limit.
        if (end == start || resultingLength <= maximum) return null;
        return destination.subSequence(replaceStart, replaceEnd);
    }
}
