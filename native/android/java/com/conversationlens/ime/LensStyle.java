package com.conversationlens.ime;

import android.app.Activity;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.widget.*;

/** Visual system 1.0. Change shared tokens, not individual screens. */
final class LensStyle {
    static final int BG=LensTokens.BACKGROUND, SURFACE=LensTokens.SURFACE, INK=LensTokens.TEXT_PRIMARY,
        MUTED=LensTokens.TEXT_SECONDARY, GREEN=LensTokens.ACTION_PRIMARY, TINT=LensTokens.SURFACE_SELECTED,
        BORDER=LensTokens.BORDER_DEFAULT, KEYBOARD=LensTokens.KEYBOARD_BACKGROUND,
        NAVIGATION=LensTokens.NAVIGATION_BACKGROUND, DISABLED=LensTokens.SURFACE_DISABLED;
    static int dp(Context c,int n){return Math.round(n*c.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(Context c,int color,int radius,boolean stroke){
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,radius));
        if(stroke)d.setStroke(dp(c,LensTokens.BORDER_DEFAULT_DP),BORDER);return d;
    }
    static void window(Activity a){
        a.getWindow().setStatusBarColor(BG);a.getWindow().setNavigationBarColor(BG);
        a.getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
    }
    static void text(TextView v,int size,boolean heading){
        v.setTextSize(size);v.setTextColor(heading?INK:MUTED);
        if(heading)v.setTypeface(Typeface.create(LensTokens.FONT_HEADING,Typeface.NORMAL));
        v.setLineSpacing(dp(v.getContext(),LensTokens.TEXT_LINE_EXTRA_DP),1);
    }
    static LinearLayout.LayoutParams space(Context c){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(c,LensTokens.STACK_GAP_DP);return p;
    }
    static void button(Button b,boolean primary){
        Context c=b.getContext();b.setAllCaps(false);b.setTextSize(LensTokens.ACTION_TEXT_SP);
        b.setTypeface(Typeface.create(LensTokens.FONT_ACTION,Typeface.NORMAL));
        b.setMinHeight(dp(c,LensTokens.ACTION_MIN_HEIGHT_DP));b.setMinimumHeight(dp(c,LensTokens.ACTION_MIN_HEIGHT_DP));
        b.setPadding(dp(c,LensTokens.ACTION_PADDING_X_DP),dp(c,LensTokens.ACTION_PADDING_Y_DP),dp(c,LensTokens.ACTION_PADDING_X_DP),dp(c,LensTokens.ACTION_PADDING_Y_DP));
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        states.addState(new int[]{-android.R.attr.state_enabled},shape(c,DISABLED,LensTokens.ACTION_RADIUS_DP,false));
        states.addState(new int[]{},shape(c,primary?GREEN:SURFACE,LensTokens.ACTION_RADIUS_DP,!primary));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(LensTokens.ACTION_PRESSED),states,null));
        b.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{MUTED,primary?SURFACE:GREEN}));
        b.setStateListAnimator(null);b.setElevation(0);
    }
    static void field(EditText e){
        Context c=e.getContext();e.setTextSize(LensTokens.FIELD_TEXT_SP);e.setTextColor(INK);e.setHintTextColor(MUTED);
        e.setPadding(dp(c,LensTokens.FIELD_PADDING_X_DP),dp(c,LensTokens.FIELD_PADDING_Y_DP),dp(c,LensTokens.FIELD_PADDING_X_DP),dp(c,LensTokens.FIELD_PADDING_Y_DP));e.setMinHeight(dp(c,LensTokens.FIELD_MIN_HEIGHT_DP));
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        GradientDrawable focused=shape(c,SURFACE,LensTokens.FIELD_RADIUS_DP,false);focused.setStroke(dp(c,LensTokens.BORDER_FOCUS_DP),GREEN);
        states.addState(new int[]{android.R.attr.state_focused},focused);states.addState(new int[]{},shape(c,SURFACE,LensTokens.FIELD_RADIUS_DP,true));e.setBackground(states);
        e.setGravity(android.view.Gravity.TOP|android.view.Gravity.START);
    }
    static void section(LinearLayout body,String title){
        TextView label=new TextView(body.getContext());label.setText(title);text(label,LensTokens.TEXT_SECTION_SP,true);
        LinearLayout.LayoutParams p=space(body.getContext());p.topMargin=dp(body.getContext(),LensTokens.SECTION_BEFORE_DP);p.bottomMargin=dp(body.getContext(),LensTokens.SECTION_AFTER_DP);body.addView(label,p);
        if(android.os.Build.VERSION.SDK_INT>=28)label.setAccessibilityHeading(true);
    }
    static void key(Button b,boolean special){
        Context c=b.getContext();button(b,false);b.setPadding(0,0,0,0);b.setMinWidth(0);b.setMinimumWidth(0);
        b.setTypeface(Typeface.create(LensTokens.FONT_KEY,Typeface.NORMAL));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(LensTokens.KEY_PRESSED),
            new android.graphics.drawable.InsetDrawable(shape(c,special?LensTokens.KEY_SPECIAL:SURFACE,LensTokens.KEY_RADIUS_DP,false),dp(c,LensTokens.KEY_INSET_X_DP),dp(c,LensTokens.KEY_INSET_Y_DP),dp(c,LensTokens.KEY_INSET_X_DP),dp(c,LensTokens.KEY_INSET_Y_DP)),null));
        b.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{MUTED,INK}));
    }
}
