# TLS 证书目录

生产环境请放入由受信任 CA 签发的以下文件：

- `fullchain.pem`
- `privkey.pem`

它们被 `.gitignore` 排除，绝不能提交。开发环境可使用仅供本机测试的自签名证书；浏览器会显示安全警告。
