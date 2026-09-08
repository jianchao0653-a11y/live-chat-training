package com.conversationlens.ime;
import android.content.Context;
import org.json.JSONObject;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
final class CloudSettings {
    static String endpoint(Context context) {
        try(InputStream in=context.getAssets().open("cloud-config.json");ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] buf=new byte[1024];int n;while((n=in.read(buf))!=-1){if(out.size()+n>4096)return "";out.write(buf,0,n);}
            return new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8)).getString("endpoint");
        }catch(Exception e){return "";}
    }
    static boolean enabled(Context context){return !endpoint(context).isEmpty();}
}
