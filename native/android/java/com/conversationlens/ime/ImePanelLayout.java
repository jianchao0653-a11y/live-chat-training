package com.conversationlens.ime;

/** Page geometry, separate from component appearance. Screen measurements stay
 * dynamic; these bounds preserve the existing IME/host space allocation.
 */
final class ImePanelLayout {
    private ImePanelLayout() {}
    static final int GUTTER_DP=LensTokens.PANEL_GUTTER_DP;
    static final int COMPACT_TOP_DP=LensTokens.PANEL_TOP_COMPACT_DP;
    static final int RELAXED_TOP_DP=LensTokens.PANEL_TOP_RELAXED_DP;
    static final int ROSTER_MAX_DP=240, ROSTER_MIN_DP=88;
    static final float ROSTER_SCREEN_FRACTION=.30f;
    static final int ASSISTANT_MAX_DP=280, ASSISTANT_MIN_DP=88;
    static final float ASSISTANT_SCREEN_FRACTION=.34f;
    static final int DETAILS_MAX_DP=300, DETAILS_MIN_DP=96;
    static final float DETAILS_SCREEN_FRACTION=.36f;
    static final int IMAGE_PREVIEW_MAX_DP=130;
    static final int EDITOR_MIN_LINES=2, ASSISTANT_EDITOR_MAX_LINES=5, DETAILS_EDITOR_MAX_LINES=4;
}
