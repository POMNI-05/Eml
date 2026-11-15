# 获取 Gmail 凭证并连接邮箱

本教程让新用户从零创建**自己管理的 Google Cloud 项目和 OAuth 客户端**，无需向 Eml 开发者索取凭证。
个人 Gmail 与公司 Google Workspace 都可按各自权限配置；使用 Outlook 不会改变邮箱实际服务商。
在实际使用 Eml 的电脑上操作。Google 密码只在 Google 登录页面输入，不交给 Eml。

Eml 首次登录页有 **Create my Google credentials · 创建自己的凭证** 引导，支持中英文、逐步导航、
Google 控制台链接和本教程下载。引导不替你注册 Google 项目，也不因点击“下一步”就认定设置成功。
如果已经有适用的 Desktop OAuth JSON，可以直接上传，不必重建项目。

## 1. 创建自己的 Google Cloud 项目

1. 打开 [Create a Project](https://console.cloud.google.com/projectcreate)，用负责管理该项目的 Google 账号登录。
2. 项目名可填写 **Eml Personal**。按账号情况选择组织/位置；个人账号没有公司组织不影响采用外部测试方式。
3. 点击 **Create**，等待创建完成，然后在顶部项目选择器选中这个项目。
4. 记住项目名/ID。后续 API、应用受众和客户端必须属于同一个项目。

公司账号如果不能创建项目，需要管理员授予适当权限或协助创建。
参考 [Google 创建项目说明](https://developers.google.com/workspace/guides/create-project)。

## 2. 在该项目启用 Gmail API

打开 [Gmail API 页面](https://console.cloud.google.com/apis/library/gmail.googleapis.com)，
确认顶部是刚创建的项目，点击 **Enable / 启用**；已经启用则继续。
此步骤是读取 Google 邮箱的接口配置，与 Gemini 模型 API key 无关。

## 3. 设置应用信息、受众和测试用户

打开 [Google Auth platform → Branding](https://console.cloud.google.com/auth/branding)。
首次配置时点击 **Get Started**，应用名称填 **Eml Personal**，支持邮箱和联系邮箱填写自己可管理的邮箱。
按实际用途填写并完成 Google 要求的确认。

| 使用情况 | Audience 的选择 | 要添加的账号 |
| --- | --- | --- |
| 自己的个人 Gmail，或组织外测试账号 | **External**，保持 **Testing** | 在 Test users 添加实际要连接的完整邮箱 |
| 只供同一公司 Workspace 组织内部使用 | 由管理员核对 **Internal** 是否适用 | 仅限该组织内用户，仍受公司访问策略限制 |

个人测试：打开 [Audience](https://console.cloud.google.com/auth/audience)，找到 **Test users → Add users**，
填入实际要登录的完整 Gmail 地址并保存。**即使你创建了项目，测试时也要添加自己的邮箱。**
如果创建项目和读取邮件使用不同账号，应添加后者。这里不需要给邮箱用户项目 IAM 管理权限。
Internal 项目不能给组织外的个人 Gmail 授权；公司邮箱后缀本身也不证明项目归属该公司组织。

External + Testing 的 Gmail refresh token 通常七天后失效；到期后重新登录。
这是适合验证的配置，长期公司交接另行核对 Internal 等适用方式，不能只切换 Production 就视为完成验证。
参考 [受众配置](https://developers.google.com/workspace/guides/configure-oauth-consent)和
[token 期限](https://developers.google.com/identity/protocols/oauth2)。

## 4. 添加 Gmail 只读范围

打开 [Data Access](https://console.cloud.google.com/auth/scopes) → **Add or Remove Scopes**，
搜索 Gmail API 或在手动输入框添加以下范围，然后 **Update / Save**：

```text
https://www.googleapis.com/auth/gmail.readonly
```

这是当前 Eml 请求的邮箱权限。它允许查看邮件，但不授予发信或删信权限。
如果列表中找不到 Gmail，回到第 2 步核对 API 是否在当前项目启用。
参考 [Gmail scopes](https://developers.google.com/workspace/gmail/api/auth/scopes)。

## 5. 创建 Desktop OAuth 客户端并下载 JSON

1. 打开 [Clients](https://console.cloud.google.com/auth/clients) → **Create Client**。
2. **Application type 选择 Desktop app**。名称可填 **Eml Windows** 或 **Eml Mac**；不同平台可分别管理客户端。
3. 点击 **Create**，然后 **Download JSON**，把文件保存在本机。
4. 下载文件可能叫 `client_secret_….json`，保留原名即可。

Desktop 客户端无需手填网站地址或固定回调端口；如果页面要求这些，先核对是否误选了 Web application。
下载的是 OAuth 客户端 JSON，不是 API key、service account 密钥或已有用户的 token。
文件应包含 `installed` 配置，Eml 会检查文件类型和 Google 授权地址。
参考 [Google 创建凭证说明](https://developers.google.com/workspace/guides/create-credentials)。

## 6. 回到 Eml 上传并授权

上传刚下载的文件后，Eml 才能发起你的 Gmail 登录。每个人的邮箱授权在各自电脑上生成，
无需向开发者发送 JSON，也不要复制别人的 `token.json`。
JSON 保存成功只代表格式检查通过；项目是否启用 API、账号是否被允许，需要下一步真实连接验证。

1. 打开 Eml，首页左侧先显示 Gmail 登录，右侧是后续工作步骤。
2. 把下载的文件拖入 **Drop Google credentials JSON here**。
3. 点击 **Save and continue**。原下载文件名可以保留，程序会规范保存为 credentials.json。
4. 点击 **Connect Gmail**，在本机打开的浏览器里选择实际需要读取的 Gmail 账户并授权。
5. 返回 App，看到 Connected mailbox 后，右侧会显示 **Client** 和文件夹操作。
   用 **Client management → Add client** 添加客户，或直接选择已有客户。

如果本机已有 credentials.json 或 token.json，首页直接显示登录按钮，不再显示上传区域。
连接后，账户和草稿语言设置收起在顶部 **Gmail connected** 状态按钮内。
需要更换配置时，可在 Connection help 或 Gmail connected 中主动选择更换 Google app file。

| 本机文件 | 用途 |
| --- | --- |
| credentials.json | Google Cloud 生成的 Desktop app 客户端配置 |
| token.json | 完成邮箱授权后自动生成，之后用于继续登录和刷新 |
| clients.json | 可选的旧版客户清单，与 Google 登录无关 |
| data/client_profiles.sqlite3 | 客户档案、背景文件、来源和草稿记录 |

使用 Launch 启动时，凭证和 token 保存在系统用户数据目录的 `auth/` 下，客户数据库也独立于代码目录；
具体位置见[本地安装说明](local_install.md)。上表的项目相对路径仅适用于直接运行旧的 Streamlit 命令。
`EML_AUTH_DIR` 可显式指定凭证目录。
程序不显示文件中的 secret 或 token。更换为不同客户端配置时，需要重新授权。
**Gmail connected → Disconnect Gmail** 只删除本机 token，不撤销 Google 账户后台已授予的权限。

## 常见问题

- **提示需要 Desktop app**：重新建立 Desktop app 类型的 OAuth 客户端，下载它的 JSON。
- **Access denied / app is being tested**：核对 Audience、Test users 和实际登录邮箱。
  Workspace 管理员策略也可能限制第三方应用访问，需要由组织管理员处理。
- **Gmail API 未启用**：在创建该 OAuth 客户端的同一个 Cloud 项目中启用 Gmail API。
- **已保存授权但连接失效**：忘记本地登录，再点击 Connect Gmail 重新授权。
  External + Testing 的 OAuth 项目所发 refresh token 通常七天到期。
  长期公司内部使用应核对 Workspace Internal 等适用配置；公开 Production 与
  restricted-scope 验证不能仅凭一个开关视为完成。参见
  [Google refresh token 说明](https://developers.google.com/identity/protocols/oauth2)。
- **浏览器授权无法返回**：在运行 App 的同一台电脑完成授权。本版使用本机 localhost 回调，
  尚未改造成托管网站的多用户 OAuth 服务。
- **点击 Connect Gmail 后一直等待，没有打开 Google**：点击页面内的
  **Continue to Google sign-in**，在新标签页完成授权；保留 Eml 标签页，三分钟内完成。
  页面内链接不依赖 Python/macOS 自动打开浏览器，因此也可用于自动打开浏览器失败的情况。
  超时后重新点击 Connect Gmail 获取新链接；不要使用旧日志中的链接。
- **Google 页面已完成，但 Eml 提示 DNS lookup failed**：浏览器收到 Google 回调不代表
  Python 已换取 Gmail token。运行 Eml 的电脑仍须能解析并连接
  `oauth2.googleapis.com`，之后还须访问 Gmail API。检查该电脑的网络、DNS、VPN 或代理配置；
  不要关闭证书校验，也不必仅为这个网络错误反复更换 OAuth 文件。

此教程依据 [Google Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
和 [OAuth consent 配置说明](https://developers.google.com/workspace/guides/configure-oauth-consent)。
Google 控制台布局可能调整，以官方页面名称和提示为准。
