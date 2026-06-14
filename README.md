# About

Those who attempt to play the global version of sif2 may had already noticed that the client is very unstable, for it's always crash after pop "An error has occurred" window.

I analysed the log, and I found the reason is not simply because the bad network connection with remote CDN server, but that the global version of sif2 client always enquiries an nonexistent Google Play product after tap screen, eventually causes Unity IAP Initialize Error, which is a fatal error. Such logic doesn't exist in the japan version of client, so the JP version is fine.

I made a patch script to fix this problem by blocking Google Play Billing Client functions from triggering.

The second script will fix the problem mentioned above as well as modify the client's CDN settings to localhost, it is mainly designed for ZH-CHT language pack support. You can ignore it if you don't need Traditional Chinese support.

尝试游玩 sif2 国际版的玩家可能已经注意到了这个客户端非常不稳定，它总是在弹出“An error has occurred”的弹窗后崩溃。

我分析了日志，发现造成此问题的根本原因不是简单地因为它和远程 CDN 服务器的网络连接质量差，而是因为国际版 sif2 客户端在点击屏幕后总是会向 Google Play 查询一个不存在的商品，最终导致 Unity IAP 初始化错误的致命错误。这种运行逻辑在日本版客户端中并不存在，所以日版没有这种问题。

我做了一个修补脚本，它通过阻断  Google Play Billing Client 相关函数的触发来修复这一问题。

第二个脚本在修复上述问题的同时还会把客户端的CDN设置调整为本地服务器，这么做主要是为了支持繁体中文语言包。如果你不需要繁体中文支持的话你可以忽略它。


p.s. the project's name is based on whose support color matches the project's primary language's color on github :)

<img width="600" height="496" alt="_1689611472_49ac86d2" src="https://github.com/user-attachments/assets/05916e78-1b59-4bdd-9b65-5813a95b572f" />
