package com.conversationlens.ime;

import android.content.Context;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

final class NativeClient {
    static final ExecutorService IO = Executors.newFixedThreadPool(3);
    private static final String ALIAS = "lens-device-v1";
    final String endpoint, token;
    static final class RequestFailure extends Exception {
        final String retryOf;
        RequestFailure(JSONObject result){super(result.optString("error","请求失败")+(result.has("request_id")?"\n问题编号："+result.optString("request_id"):""));retryOf=result.optString("retry_of");}
    }
    NativeClient(String endpoint, String token) throws Exception {
        URL url = new URL(endpoint.trim());
        if (url.getUserInfo()!=null || url.getQuery()!=null || url.getRef()!=null || !(url.getPath().isEmpty() || url.getPath().equals("/"))) throw new Exception("请输入服务根地址");
        if (!url.getProtocol().equals("https") && !(url.getProtocol().equals("http") && (url.getHost().equals("127.0.0.1") || url.getHost().equals("localhost")))) throw new Exception("远程连接须使用 HTTPS；USB 转发可使用 http://127.0.0.1:4317");
        this.endpoint = endpoint.trim().replaceAll("/+$", ""); this.token = token;
    }
    JSONObject call(String path, JSONObject body) throws Exception {
        HttpURLConnection c = (HttpURLConnection)new URL(endpoint+"/api/native/"+path).openConnection();
        c.setConnectTimeout(10000); c.setReadTimeout(120000); c.setInstanceFollowRedirects(false);
        c.setRequestProperty("Accept", "application/json");
        if (!token.isEmpty()) c.setRequestProperty("Authorization", "Bearer "+token);
        try {
            if (body!=null) {
                c.setRequestMethod("POST"); c.setDoOutput(true); c.setRequestProperty("Content-Type", "application/json");
                byte[] bytes=body.toString().getBytes(StandardCharsets.UTF_8); c.setFixedLengthStreamingMode(bytes.length);
                try(OutputStream out=c.getOutputStream()){out.write(bytes);}
            }
            int status=c.getResponseCode();
            InputStream stream=status>=400?c.getErrorStream():c.getInputStream();
            if(stream==null)throw new Exception("服务未返回内容（"+status+"）");
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            try(InputStream in=stream){byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1){if(out.size()+n>2000000)throw new Exception("响应过大");out.write(bytes,0,n);}}
            JSONObject result=new JSONObject(new String(out.toByteArray(),StandardCharsets.UTF_8));
            if(status<200 || status>=300)throw new RequestFailure(result);
            return result;
        } finally { c.disconnect(); }
    }
    private static SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(store.containsAlias(ALIAS))return (SecretKey)store.getKey(ALIAS,null);
        KeyGenerator generator=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        generator.init(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build());
        return generator.generateKey();
    }
    static synchronized void save(Context context, NativeClient client) throws Exception {
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.ENCRYPT_MODE,key());
        JSONObject value=new JSONObject().put("endpoint",client.endpoint).put("token",client.token).put("cloud",CloudSettings.enabled(context));
        JSONObject encrypted=new JSONObject().put("iv",Base64.encodeToString(cipher.getIV(),Base64.NO_WRAP)).put("data",Base64.encodeToString(cipher.doFinal(value.toString().getBytes(StandardCharsets.UTF_8)),Base64.NO_WRAP));
        android.util.AtomicFile file=new android.util.AtomicFile(new File(context.getNoBackupFilesDir(),"device.enc"));
        FileOutputStream out=file.startWrite();
        try {out.write(encrypted.toString().getBytes(StandardCharsets.UTF_8));file.finishWrite(out);}catch(Exception e){file.failWrite(out);throw e;}
    }
    static synchronized NativeClient load(Context context) throws Exception {
        File file=new File(context.getNoBackupFilesDir(),"device.enc");if(!file.exists())return null;
        byte[] bytes=new android.util.AtomicFile(file).readFully();JSONObject encrypted=new JSONObject(new String(bytes,StandardCharsets.UTF_8));
        Cipher cipher=Cipher.getInstance("AES/GCM/NoPadding");cipher.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,Base64.decode(encrypted.getString("iv"),Base64.NO_WRAP)));
        JSONObject value=new JSONObject(new String(cipher.doFinal(Base64.decode(encrypted.getString("data"),Base64.NO_WRAP)),StandardCharsets.UTF_8));
        if(CloudSettings.enabled(context)&&(!value.optBoolean("cloud")||!CloudSettings.endpoint(context).equals(value.optString("endpoint")))){forget(context);return null;}
        return new NativeClient(value.getString("endpoint"),value.getString("token"));
    }
    static synchronized void forget(Context context){AssistSession.clearFeedback();new android.util.AtomicFile(new File(context.getNoBackupFilesDir(),"device.enc")).delete();}
}
