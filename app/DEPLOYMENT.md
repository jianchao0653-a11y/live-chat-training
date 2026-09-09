# 原生专用入口与本机管理边界

v0.15.1，MADR-038。当前是单人管理工作区，不是公网多租户产品。

启动 `npm.cmd start` 同时创建两个仅本机监听的 HTTP 端口：

| 端口 | 用途 | 远程代理 |
|---|---|---|
| 4317（PORT） | 本机网页、设置、配对码、撤销、导出；兼容原 USB 合成测试 | **禁止转发** |
| 4318（LENS_NATIVE_PORT） | 只接受 `/api/native/`，其余规范化路径均返回 403 | HTTPS 唯一允许的 upstream |

两个监听器共享同一进程内设备授权和工作区，不使用另一个进程复制设备 token。管理工作区拒绝非 loopback 连接；旧的 `LENS_HOST=0.0.0.0` 加共享口令方式已停止支持。`LENS_ACCESS_TOKEN` 不再作为远程管理认证。

HTTPS 代理即使删除全部转发标记、把 Host 改为 localhost，只要 upstream 是 4318，仍不能进入管理路由。代理到错误的 4317 依然违反部署边界，系统不能识别所有伪装成本机的进程。部署验收必须检查实际监听、upstream 与外部路径结果，不能只检查配置文件。

下面是 Nginx server 配置片段；域名与证书路径须由实际部署提供，本轮未签发证书或部署公开服务：

```nginx
server {
    listen 443 ssl;
    server_name lens.example.com;
    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    client_max_body_size 7m;
    location ^~ /api/native/ {
        proxy_pass http://127.0.0.1:4318;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_read_timeout 190s;
    }
    location / { return 403; }
}
```

真实部署前从外部合成客户端验证 `/`、`/api/bootstrap`、`/api/export`、`/api/devices/pairing`、`/api/settings` 全部拒绝；无 token 的 `/api/native/roster` 为 401；电脑生成一次性配对码后仅可读指定主播 roster；电脑撤销后同 token 必须失效。服务端单测已用真实本地 HTTP 代理回放上述路径（包含路径穿越规范化），但没有证明任何未来生产代理已按此配置。

模型预算按进程共享，单次模型调用 90 秒超时；分析有独立生成和终审。手机客户端仍有自己的超时。实际延迟和重试体验须通过真实模型验收，不自动重试付费操作。配对、撤销和授权票据均在内存；服务重启后需要重新配对。
