package com.conversationlens.ime;

import android.content.Context;
import android.content.ContextWrapper;
import android.view.Display;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowManager;
import android.widget.Spinner;

/** Anchored IME choices whose popup has its own screenshot protection on API 26+. */
final class ImeDropdownSpinner extends Spinner {
    ImeDropdownSpinner(Context context) {
        super(new PopupContext(context), Spinner.MODE_DROPDOWN);
    }

    private static final class PopupContext extends ContextWrapper {
        private final WindowManager windows;

        PopupContext(Context context) {
            super(context);
            windows=new SecureWindows((WindowManager)context.getSystemService(Context.WINDOW_SERVICE));
        }

        @Override public Object getSystemService(String name) {
            return Context.WINDOW_SERVICE.equals(name)?windows:super.getSystemService(name);
        }
    }

    /** PopupWindow obtains this public service from its context before adding its decor. */
    private static final class SecureWindows implements WindowManager {
        private final WindowManager delegate;

        SecureWindows(WindowManager delegate) {this.delegate=delegate;}

        private static ViewGroup.LayoutParams protect(ViewGroup.LayoutParams params) {
            if(!(params instanceof WindowManager.LayoutParams))
                throw new IllegalArgumentException("IME popup requires window layout parameters");
            // Keep choices touchable without taking the host's window focus or IME target.
            // A non-focusable popup must also clear ALT_FOCUSABLE_IM to stay above the IME.
            WindowManager.LayoutParams window=(WindowManager.LayoutParams)params;
            window.flags=(window.flags|WindowManager.LayoutParams.FLAG_SECURE
                    |WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE)&~WindowManager.LayoutParams.FLAG_ALT_FOCUSABLE_IM;
            return params;
        }

        @Override public void addView(View view,ViewGroup.LayoutParams params) {
            delegate.addView(view,protect(params));
        }
        @Override public void updateViewLayout(View view,ViewGroup.LayoutParams params) {
            delegate.updateViewLayout(view,protect(params));
        }
        @Override public void removeView(View view) {delegate.removeView(view);}
        @Override public void removeViewImmediate(View view) {delegate.removeViewImmediate(view);}
        @Override public Display getDefaultDisplay() {return delegate.getDefaultDisplay();}
    }
}
