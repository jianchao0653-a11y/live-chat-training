package com.conversationlens.ime;

import android.app.Activity;
import android.app.AlertDialog;
import android.os.Bundle;
import android.os.Build;
import android.view.WindowInsets;
import android.graphics.Rect;
import android.content.Intent;
import android.provider.Settings;
import android.text.InputType;
import android.view.View;
import android.view.inputmethod.InputMethodManager;
import android.widget.*;
import java.nio.charset.StandardCharsets;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

public final class SetupActivity extends Activity {
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR | View.SYSTEM_UI_FLAG_LIGHT_NAVIGATION_BAR);
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        LinearLayout body = new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setPadding(24, 32, 24, 24);
        body.setBackgroundColor(0xfff5f7f5);
        scroll.setOnApplyWindowInsetsListener((view, insets) -> {
            int top = insets.getSystemWindowInsetTop(), bottom = insets.getSystemWindowInsetBottom();
            if (Build.VERSION.SDK_INT >= 30) {
                top = insets.getInsets(WindowInsets.Type.systemBars()).top;
                bottom = insets.getInsets(WindowInsets.Type.systemBars() | WindowInsets.Type.ime()).bottom;
            }
            view.setPadding(0, top, 0, bottom);
            View focused = getCurrentFocus();
            if (focused instanceof EditText) scroll.post(() -> focused.requestRectangleOnScreen(new Rect(0, 0, focused.getWidth(), focused.getHeight()), false));
            return insets;
        });
        scroll.addView(body);
        TextView title = new TextView(this);
        title.setText("观微输入法"); title.setTextSize(28); title.setTextColor(0xff174f45);
        body.addView(title);
        TextView info = new TextView(this);
        info.setText("离线中文输入 · 可连接电脑分析服务\n批准片段后才提交，消息由你发送。\n");
        info.setTextSize(16); body.addView(info);
        button(body, "1 · 在系统设置中启用", () -> startActivity(new Intent(Settings.ACTION_INPUT_METHOD_SETTINGS)));
        button(body, "2 · 选择观微输入法", () -> ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).showInputMethodPicker());
        button(body, "连接分析服务", () -> startActivity(new Intent(this, AssistantActivity.class)));
        EditText practice = new EditText(this);
        practice.setHint("在这里试打 nihao、zhongguo、xiexie");
        practice.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        practice.setMinLines(3); practice.setId(1001); practice.setSaveEnabled(false);
        body.addView(practice, 2);
        EditText password = new EditText(this);
        password.setHint("合成密码测试框（英文模式）");
        password.setInputType(InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        password.setId(1002); password.setSaveEnabled(false); body.addView(password, 3);
        button(body, "切回熟悉的输入法", () -> ((InputMethodManager)getSystemService(INPUT_METHOD_SERVICE)).showInputMethodPicker());
        button(body, "开源组件与许可证", () -> showLicense("THIRD_PARTY_NOTICES.txt"));
        button(body, "Android C++ 运行库许可证", () -> showLicense("NDK-NOTICES.txt"));
        setContentView(scroll);
    }
    private void showLicense(String file) {
        try (InputStream in = getAssets().open(file); ByteArrayOutputStream out = new ByteArrayOutputStream()) {
            byte[] data = new byte[8192]; int count;
            while ((count = in.read(data)) != -1) out.write(data, 0, count);
            new AlertDialog.Builder(this).setTitle("开源组件")
                .setMessage(new String(out.toByteArray(), StandardCharsets.UTF_8)).setPositiveButton("关闭", null).show();
        } catch (Exception ignored) { Toast.makeText(this, "许可证文件不可用", Toast.LENGTH_LONG).show(); }
    }
    private void button(LinearLayout body, String label, Runnable action) {
        Button button = new Button(this); button.setText(label); button.setAllCaps(false);
        button.setOnClickListener(view -> action.run()); body.addView(button);
    }
}
