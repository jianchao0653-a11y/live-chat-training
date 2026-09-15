package com.conversationlens.ime;

/** Keyboard arrangement and measured-space rules, not component appearance. */
final class KeyboardLayout {
    private KeyboardLayout() {}
    static final int GUTTER_DP=LensTokens.KEYBOARD_GUTTER_DP;
    static final int BAR_HEIGHT_DP=LensTokens.ACTION_MIN_HEIGHT_DP;
    static final int HEADER_SWITCH_WIDTH_DP=56, VIEWPORT_MIN_DP=96;
    static final float LANDSCAPE_SCREEN_FRACTION=.86f, PORTRAIT_SCREEN_FRACTION=.78f;
    static final int NINE_BOARD_MIN_DP=192, SIDE_MIN_DP=48, SIDE_MAX_DP=64;
    static final float SIDE_SCREEN_FRACTION=.15f;
    static final int LANDSCAPE_PUNCTUATION_WIDTH_DP=96, FULL_ROW_INDENT_DP=12;
    static final int LANDSCAPE_ROW_DP=48, NINE_ROW_DP=64, FULL_ROW_DP=54;
    static final float FONT_GROWTH_MAX_DP=18f, FONT_GROWTH_STEP_DP=16f;
    static final float BACKSPACE_WEIGHT=1.35f, RETURN_WEIGHT=1.3f, SPACE_WEIGHT=2.2f,
        SHIFT_WEIGHT=.85f, LANGUAGE_WEIGHT=1.1f;
    static final int NUMERIC_SPACE_WEIGHT=2, NINE_MAX_LINES=2, KEY_MAX_LINES=1;
}
