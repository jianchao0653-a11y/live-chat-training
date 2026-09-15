package com.conversationlens.ime;

/** Existing Activity geometry. PX constants intentionally preserve legacy units. */
final class ActivityLayout {
    private ActivityLayout() {}
    static final int GUTTER_DP=LensTokens.ACTIVITY_GUTTER_DP;
    static final int PADDING_Y_DP=LensTokens.ACTIVITY_PADDING_Y_DP;
    static final int EDITOR_MIN_LINES=3, LIBRARY_EDITOR_MIN_LINES=2;
    static final int IMAGE_PREVIEW_MAX_PX=600;
    static final int LIBRARY_HEADING_ABOVE_SP=LensTokens.ACTIVITY_SECTION_SP;
    static final int ASSISTANT_HEADING_FROM_SP=LensTokens.TEXT_SECTION_SP;
}
