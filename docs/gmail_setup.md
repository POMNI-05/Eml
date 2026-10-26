# 获取 Gmail 凭证并连接邮箱

在实际使用的电脑上运行 Eml。这里连接的是 Google 托管的邮箱；
日常使用 Outlook 不会改变邮箱服务商。

## 一次性获取凭证

1. 打开 [Google Cloud Console](https://console.cloud.google.com/)，登录用于管理项目的 Google 账户，
   创建或选择一个项目。
2. 在 API 库中找到 **Gmail API**，点击 **Enable**。
3. 打开 **Google Auth platform → Branding**。首次配置时点击 **Get Started**，
   填写应用名称，例如 Eml Local，以及支持邮箱和联系邮箱。
4. 配置 **Audience**。如果只给同一 Workspace 组织使用且可选 Internal，可以使用 Internal。
   其他测试情形选择 External，并在 Testing 状态下把实际要登录的邮箱加入 **Test users**。
   在 **Data Access** 中使用本应用需要的 Gmail 只读范围 gmail.readonly。
5. 打开 **Google Auth platform → Clients → Create Client**。
   **Application type 必须选择 Desktop app**，填写一个名称并创建。
6. 下载这个 OAuth 客户端的 JSON 文件。不是 API key，不是 service account JSON，
   也不是 Google 账户密码。

## 在 Eml 里上传

1. 展开左侧 **Gmail setup**。
2. 把下载的文件拖入 **Drop Google credentials JSON here**。
3. 点击 **Save Google credentials**。原下载文件名可以保留，程序会规范保存为 credentials.json。
4. 点击 **Connect Gmail**，在本机打开的浏览器里选择实际需要读取的 Gmail 账户并授权。
5. 返回 App，看到 Connected mailbox 后，就可以加载标签和读取选定邮件。

| 本机文件 | 用途 |
| --- | --- |
| credentials.json | Google Cloud 生成的 Desktop app 客户端配置 |
| token.json | 完成邮箱授权后自动生成，之后用于继续登录和刷新 |
| clients.json | 可选的旧版客户清单，与 Google 登录无关 |
| data/client_profiles.sqlite3 | 客户档案、背景文件、来源和草稿记录 |

凭证和 token 默认保存在项目根目录，也可用 EML_AUTH_DIR 指定目录。
程序不显示文件中的 secret 或 token。更换为不同客户端配置时，需要重新授权。
**Forget local Google sign-in** 只删除本机 token，不撤销 Google 账户后台已授予的权限。

## 常见问题

- **提示需要 Desktop app**：重新建立 Desktop app 类型的 OAuth 客户端，下载它的 JSON。
- **Access denied / app is being tested**：核对 Audience、Test users 和实际登录邮箱。
  Workspace 管理员策略也可能限制第三方应用访问，需要由组织管理员处理。
- **Gmail API 未启用**：在创建该 OAuth 客户端的同一个 Cloud 项目中启用 Gmail API。
- **已保存授权但连接失效**：忘记本地登录，再点击 Connect Gmail 重新授权。
- **浏览器授权无法返回**：在运行 App 的同一台电脑完成授权。本版使用本机 localhost 回调，
  尚未改造成托管网站的多用户 OAuth 服务。

此教程依据 [Google Gmail Python quickstart](https://developers.google.com/workspace/gmail/api/quickstart/python)
和 [OAuth consent 配置说明](https://developers.google.com/workspace/guides/configure-oauth-consent)。
Google 控制台布局可能调整，以官方页面名称和提示为准。
