package com.conversationlens.ime;

/** Design values for MADR-050. SP is passed to TextView; DP uses LensStyle.dp.
 * Consumers use semantic names only. Base scales are private to this file.
 */
final class LensTokens {
    private LensTokens() {}
    private static final class Base {
        static final int WHITE=0xffffffff, GRAY_50=0xfff5f7f6, GRAY_100=0xffe8ede9,
            GRAY_200=0xffdde4df, GRAY_300=0xffc3cec7, GRAY_600=0xff58665f,
            GRAY_900=0xff202b27, GREEN_50=0xffe6efe9, GREEN_100=0xffd6e1d9,
            GREEN_700=0xff27634d, GREEN_PRESS=0x2427634d, GREEN_KEY_PRESS=0x3027634d,
            BRAND_RED=0xffd52235;
        static final String SANS="sans-serif", SANS_MEDIUM="sans-serif-medium";
        static final int DP_1=1, DP_2=2, DP_3=3, DP_4=4, DP_6=6, DP_8=8,
            DP_10=10, DP_12=12, DP_14=14, DP_20=20, DP_24=24, DP_48=48, DP_52=52;
        static final int SP_1=1, SP_6=6, SP_12=12, SP_13=13, SP_14=14, SP_15=15, SP_16=16, SP_17=17, SP_18=18,
            SP_20=20, SP_21=21, SP_22=22, SP_24=24, SP_25=25, SP_26=26, SP_27=27, SP_28=28;
        static final int PX_12=12, PX_24=24;
        static final float FRACTION_DIGIT=.52f;
    }

    // Semantic colors, including interaction states. XML theme colors are
    // generated from these references by design_tokens_check.py --write-resources.
    static final int BACKGROUND=Base.GRAY_50;
    static final int SURFACE=Base.WHITE;
    static final int TEXT_PRIMARY=Base.GRAY_900;
    static final int TEXT_SECONDARY=Base.GRAY_600;
    static final int ACTION_PRIMARY=Base.GREEN_700;
    static final int SURFACE_SELECTED=Base.GREEN_50;
    static final int BORDER_DEFAULT=Base.GRAY_300;
    static final int KEYBOARD_BACKGROUND=Base.GRAY_100;
    static final int NAVIGATION_BACKGROUND=Base.GRAY_600;
    static final int SURFACE_DISABLED=Base.GRAY_200;
    static final int ACTION_PRESSED=Base.GREEN_PRESS;
    static final int KEY_PRESSED=Base.GREEN_KEY_PRESS;
    static final int KEY_SPECIAL=Base.GREEN_100;
    static final int LAUNCHER_BACKGROUND=Base.BRAND_RED;
    static final int LAUNCHER_FOREGROUND=Base.WHITE;
    static final String FONT_HEADING=Base.SANS_MEDIUM;
    static final String FONT_ACTION=Base.SANS_MEDIUM;
    static final String FONT_KEY=Base.SANS;

    static final int TEXT_CAPTION_SP=Base.SP_12;
    static final int TEXT_SUPPORT_SP=Base.SP_13;
    static final int TEXT_BODY_SP=Base.SP_14;
    static final int TEXT_SUBHEADING_SP=Base.SP_15;
    static final int TEXT_HEADING_SP=Base.SP_16;
    static final int TEXT_PAGE_TITLE_SP=Base.SP_17;
    static final int TEXT_SECTION_SP=Base.SP_18;
    static final int ACTION_TEXT_SP=Base.SP_15;
    static final int COMPACT_ACTION_TEXT_SP=Base.SP_14;
    static final int FIELD_TEXT_SP=Base.SP_16;
    static final int CHECKBOX_TEXT_SP=Base.SP_14;

    static final int BORDER_DEFAULT_DP=Base.DP_1;
    static final int BORDER_FOCUS_DP=Base.DP_2;
    static final int TEXT_LINE_EXTRA_DP=Base.DP_3;
    static final int STACK_GAP_DP=Base.DP_8;
    static final int ACTION_MIN_HEIGHT_DP=Base.DP_48;
    static final int ACTION_PADDING_X_DP=Base.DP_14;
    static final int ACTION_PADDING_Y_DP=Base.DP_10;
    static final int ACTION_RADIUS_DP=Base.DP_12;
    static final int FIELD_PADDING_X_DP=Base.DP_14;
    static final int FIELD_PADDING_Y_DP=Base.DP_12;
    static final int FIELD_MIN_HEIGHT_DP=Base.DP_52;
    static final int FIELD_RADIUS_DP=Base.DP_12;
    static final int SECTION_BEFORE_DP=Base.DP_24;
    static final int SECTION_AFTER_DP=Base.DP_4;
    static final int KEY_RADIUS_DP=Base.DP_8;
    static final int KEY_INSET_X_DP=Base.DP_2;
    static final int KEY_INSET_Y_DP=Base.DP_3;

    static final int PANEL_RADIUS_DP=Base.DP_10;
    static final int PANEL_GUTTER_DP=Base.DP_8;
    static final int PANEL_TOP_COMPACT_DP=Base.DP_4;
    static final int PANEL_TOP_RELAXED_DP=Base.DP_6;
    static final int LOCAL_FIELD_MIN_HEIGHT_DP=Base.DP_48;
    static final int LOCAL_FIELD_PADDING_X_DP=Base.DP_10;
    static final int LOCAL_FIELD_PADDING_Y_DP=Base.DP_8;
    static final int SELECTOR_MIN_HEIGHT_DP=Base.DP_48;
    static final int CHECKBOX_MIN_HEIGHT_DP=Base.DP_48;
    static final int COMPACT_ACTION_PADDING_X_DP=Base.DP_8;
    static final int ROSTER_ACTION_PADDING_Y_DP=Base.DP_4;
    static final int ASSISTANT_ACTION_PADDING_Y_DP=Base.DP_6;
    static final int CONFIRM_PADDING_DP=Base.DP_8;
    static final int CONFIRM_RADIUS_DP=Base.DP_10;
    static final int CARD_PADDING_X_DP=Base.DP_8;
    static final int CARD_PADDING_Y_DP=Base.DP_6;
    static final int CARD_RADIUS_DP=Base.DP_10;

    static final int KEY_TAB_TEXT_SP=Base.SP_14;
    static final int KEY_ACTION_TEXT_SP=Base.SP_16;
    static final int KEY_LETTER_TEXT_SP=Base.SP_22;
    static final int KEY_NINE_TEXT_SP=Base.SP_25;
    static final int KEY_BACKSPACE_TEXT_SP=Base.SP_26;
    static final int KEY_RESET_TEXT_SP=Base.SP_21;
    static final int KEY_ZERO_TEXT_SP=Base.SP_27;
    static final int KEY_ENTER_TEXT_SP=Base.SP_25;
    static final int CANDIDATE_TEXT_SP=Base.SP_20;
    static final int CANDIDATE_PAGE_TEXT_SP=Base.SP_22;
    static final int KEY_AUTOSIZE_MIN_SP=Base.SP_6;
    static final int KEY_AUTOSIZE_STEP_SP=Base.SP_1;
    static final float KEY_DIGIT_TEXT_FRACTION=Base.FRACTION_DIGIT;
    static final int KEY_SURFACE_RADIUS_DP=Base.DP_10;
    static final int KEY_PUNCTUATION_RADIUS_DP=Base.DP_12;
    static final int KEY_PADDING_X_DP=Base.DP_3;
    static final int CANDIDATE_PADDING_X_DP=Base.DP_12;
    static final int KEYBOARD_GUTTER_DP=Base.DP_4;
    static final int KEYBOARD_STATUS_PADDING_X_DP=Base.DP_8;
    static final int KEYBOARD_STATUS_PADDING_Y_DP=Base.DP_4;
    static final int INSERT_PADDING_X_DP=Base.DP_12;
    static final int INSERT_PADDING_Y_DP=Base.DP_8;
    static final int ACTIVITY_GUTTER_DP=Base.DP_20;
    static final int ACTIVITY_PADDING_Y_DP=Base.DP_24;
    static final int SETUP_TITLE_SP=Base.SP_28;
    static final int ACTIVITY_TITLE_SP=Base.SP_24;
    static final int ACTIVITY_SECTION_SP=Base.SP_20;
    static final int ACTIVITY_CHECKBOX_TEXT_SP=Base.SP_15;
    static final int ACTIVITY_SELECTOR_MIN_HEIGHT_DP=Base.DP_52;
    static final int ACTIVITY_SELECTOR_PADDING_X_DP=Base.DP_12;
    // Legacy OCR dialog used physical pixels. Preserve that contract here.
    static final int OCR_PANEL_PADDING_X_PX=Base.PX_24;
    static final int OCR_PANEL_PADDING_Y_PX=Base.PX_12;
}
