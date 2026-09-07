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
    static final int BG=0xfff5f7f6, SURFACE=0xffffffff, INK=0xff202b27,
        MUTED=0xff58665f, GREEN=0xff27634d, TINT=0xffe6efe9,
        BORDER=0xffc3cec7, KEYBOARD=0xffe8ede9, DISABLED=0xffdde4df;
    static int dp(Context c,int n){return Math.round(n*c.getResources().getDisplayMetrics().density);}
    static GradientDrawable shape(Context c,int color,int radius,boolean stroke){
        GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(c,radius));
        if(stroke)d.setStroke(dp(c,1),BORDER);return d;
    }
    static void window(Activity a){
        a.getWindow().setStatusBarColor(BG);a.getWindow().setNavigationBarColor(BG);
        a.getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR|View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
    }
    static void text(TextView v,int size,boolean heading){
        v.setTextSize(size);v.setTextColor(heading?INK:MUTED);
        if(heading)v.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        v.setLineSpacing(dp(v.getContext(),3),1);
    }
    static LinearLayout.LayoutParams space(Context c){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(c,8);return p;
    }
    static void button(Button b,boolean primary){
        Context c=b.getContext();b.setAllCaps(false);b.setTextSize(15);
        b.setTypeface(Typeface.create("sans-serif-medium",Typeface.NORMAL));
        b.setMinHeight(dp(c,48));b.setMinimumHeight(dp(c,48));
        b.setPadding(dp(c,14),dp(c,10),dp(c,14),dp(c,10));
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        states.addState(new int[]{-android.R.attr.state_enabled},shape(c,DISABLED,12,false));
        states.addState(new int[]{},shape(c,primary?GREEN:SURFACE,12,!primary));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x2427634d),states,null));
        b.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{MUTED,primary?SURFACE:GREEN}));
        b.setStateListAnimator(null);b.setElevation(0);
    }
    static void field(EditText e){
        Context c=e.getContext();e.setTextSize(16);e.setTextColor(INK);e.setHintTextColor(MUTED);
        e.setPadding(dp(c,14),dp(c,12),dp(c,14),dp(c,12));e.setMinHeight(dp(c,52));
        android.graphics.drawable.StateListDrawable states=new android.graphics.drawable.StateListDrawable();
        GradientDrawable focused=shape(c,SURFACE,12,false);focused.setStroke(dp(c,2),GREEN);
        states.addState(new int[]{android.R.attr.state_focused},focused);states.addState(new int[]{},shape(c,SURFACE,12,true));e.setBackground(states);
        e.setGravity(android.view.Gravity.TOP|android.view.Gravity.START);
    }
    static void section(LinearLayout body,String title){
        TextView label=new TextView(body.getContext());label.setText(title);text(label,18,true);
        LinearLayout.LayoutParams p=space(body.getContext());p.topMargin=dp(body.getContext(),24);p.bottomMargin=dp(body.getContext(),4);body.addView(label,p);
        if(android.os.Build.VERSION.SDK_INT>=28)label.setAccessibilityHeading(true);
    }
    static void key(Button b,boolean special){
        Context c=b.getContext();button(b,false);b.setPadding(0,0,0,0);b.setMinWidth(0);b.setMinimumWidth(0);
        b.setTypeface(Typeface.create("sans-serif",Typeface.NORMAL));
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(0x3027634d),
            new android.graphics.drawable.InsetDrawable(shape(c,special?0xffd6e1d9:SURFACE,8,false),dp(c,2),dp(c,3),dp(c,2),dp(c,3)),null));
        b.setTextColor(new ColorStateList(new int[][]{new int[]{-android.R.attr.state_enabled},new int[]{}},new int[]{MUTED,INK}));
    }
}
