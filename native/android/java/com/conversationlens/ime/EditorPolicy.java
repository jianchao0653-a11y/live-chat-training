package com.conversationlens.ime;

/** Android integer contracts, isolated for JVM lifecycle policy tests. */
final class EditorPolicy {
    static boolean privateField(int type, int options) {
        int kind = type & 15;
        int variation = type & 0xff0;
        return (kind == 1 && (variation == 0x80 || variation == 0x90 || variation == 0xe0))
            || (kind == 2 && variation == 0x10) || (options & 0x1000000) != 0;
    }
    static boolean numeric(int type) { return (type & 15) == 2 || (type & 15) == 3 || (type & 15) == 4; }
    static boolean chinese(int type, int options) {
        int variation = type & 0xff0;
        return (type & 15) == 1 && !privateField(type, options)
            && variation != 0x10 && variation != 0x20 && variation != 0xd0;
    }
    static boolean newline(int type) { return (type & 15) == 1 && (type & 0x20000) != 0; }
}
