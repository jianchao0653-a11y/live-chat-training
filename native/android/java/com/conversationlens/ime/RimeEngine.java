package com.conversationlens.ime;

import android.content.Context;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;

/** Called exclusively on the IME's single engine worker. */
final class RimeEngine {
    static { System.loadLibrary("lens_rime"); }
    static native long open(String shared, String user);
    static native void close(long session);
    static native String[] step(long session, int action, int value);

    static long prepare(Context context) throws Exception {
        File shared = new File(context.getFilesDir(), "rime-shared-v2");
        File user = new File(context.getNoBackupFilesDir(), "rime-user-v2");
        if ((!shared.isDirectory() && !shared.mkdirs()) || (!user.isDirectory() && !user.mkdirs()))
            throw new IllegalStateException("Cannot prepare input data");
        File marker = new File(shared, ".ready");
        if (!marker.isFile()) {
            for (String name : context.getAssets().list("rime")) {
                try (InputStream in = context.getAssets().open("rime/" + name);
                     FileOutputStream out = new FileOutputStream(new File(shared, name))) {
                    byte[] bytes = new byte[65536];
                    int count;
                    while ((count = in.read(bytes)) != -1) out.write(bytes, 0, count);
                }
            }
            if (!marker.createNewFile()) throw new IllegalStateException("Cannot finalize input data");
        }
        return open(shared.getAbsolutePath(), user.getAbsolutePath());
    }
}
