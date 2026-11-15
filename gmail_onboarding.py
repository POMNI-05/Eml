"""User-owned Google project setup instructions; no cloud provisioning calls."""
from pathlib import Path

import streamlit as st

from eml_core.auth import SCOPES


STEPS = (
    ("Create your project", "创建自己的项目", "https://console.cloud.google.com/projectcreate",
     "Sign in with the Google account that will manage your project. Enter a name such as **Eml Personal** and click **Create**. Select that project in the top bar before continuing. If your company controls project creation, ask its administrator for access.",
     "用负责管理项目的 Google 账号登录。项目名可填 **Eml Personal**，点击 **Create**。创建后在顶部项目选择器选中它。公司账号若没有创建权限，需要管理员协助。"),
    ("Enable Gmail API", "启用 Gmail API", "https://console.cloud.google.com/apis/library/gmail.googleapis.com",
     "Check the selected project, then click **Enable** on the Gmail API page. If it is already enabled, continue. Every following step must use this same project.",
     "核对顶部仍是刚建的项目，在 Gmail API 页面点击 **Enable / 启用**。已启用则继续。后面的授权配置和客户端也必须在同一个项目中创建。"),
    ("Set the audience and test users", "设置应用与测试用户", "https://console.cloud.google.com/auth/branding",
     "In **Google Auth platform → Branding**, click **Get Started** if prompted. Use **Eml Personal** as the app name and your email for support/contact.\n\n"
     "For personal Gmail, choose **External** and keep **Testing**. In [Audience](https://console.cloud.google.com/auth/audience), add the exact Gmail address you will connect under **Test users → Add users**, even if you own the project.\n\n"
     "For a company-only Workspace app, an administrator can check whether **Internal** is appropriate. Internal does not accept outside personal Gmail accounts. Test users do not need project IAM membership.",
     "在 **Google Auth platform → Branding** 首次点击 **Get Started**。应用名填 **Eml Personal**，支持邮箱和联系邮箱填自己的邮箱。\n\n"
     "个人 Gmail 选择 **External**，保持 **Testing**。到 [Audience 页面](https://console.cloud.google.com/auth/audience)，在 **Test users → Add users** 添加实际要连接的完整 Gmail 地址；即使自己是项目创建者也要添加。\n\n"
     "只在公司 Workspace 内部使用时，可由管理员核对 **Internal** 是否适用；Internal 不接受组织外个人 Gmail。Test users 不是项目 IAM 成员。"),
    ("Choose Gmail read-only access", "添加 Gmail 只读范围", "https://console.cloud.google.com/auth/scopes",
     "Open **Data Access → Add or Remove Scopes**. Find or manually add the scope below, then **Update / Save**. This is the mailbox permission Eml requests; it does not permit sending or deleting mail.",
     "打开 **Data Access → Add or Remove Scopes**，查找或手动添加下面的范围，然后 **Update / Save**。这是 Eml 连接邮箱所需的只读权限，不授予发信或删信权限。"),
    ("Create a Desktop client and download JSON", "创建 Desktop 客户端并下载 JSON", "https://console.cloud.google.com/auth/clients",
     "Open **Clients → Create Client**. Select **Desktop app**, name it **Eml Windows** or **Eml Mac**, then **Create → Download JSON**. You do not need to enter a website URL or fixed callback port for a Desktop client.\n\n"
     "Keep the downloaded file, often named `client_secret_….json`. Eml needs this OAuth JSON, not an API key, service-account key or an existing user's token.",
     "打开 **Clients → Create Client**，类型选 **Desktop app**，名称填 **Eml Windows** 或 **Eml Mac**，点击 **Create → Download JSON**。Desktop 客户端无需填写网站地址或固定回调端口。\n\n"
     "保留下载的 `client_secret_….json` 文件。Eml 要的是 OAuth JSON，不是 API key、service account 密钥或别人的 token。"),
    ("Upload here, then sign in", "回到 Eml 上传并登录", None,
     "Use **Drop Google credentials JSON here** below and click **Save and continue**. Keep the original filename if you like. Then click **Connect Gmail** and select the account allowed in step 3. Complete authorization on this computer.\n\n"
     "Eml creates your local `token.json` after authorization. Confirm the connected email address before selecting correspondence. Saving the JSON only checks its format; API access and account policies are checked when connecting.",
     "在下方 **Drop Google credentials JSON here** 上传文件，点击 **Save and continue**，无需改下载文件名。随后点击 **Connect Gmail**，选择第 3 步允许的邮箱，在这台电脑上完成授权。\n\n"
     "授权成功后，Eml 自动生成本机 `token.json`。先核对显示的邮箱再选信。保存 JSON 仅验证文件格式；API 是否启用及账号权限还要通过实际登录确认。"),
)


def _move_step(delta):
    st.session_state["gmail_setup_step"] = min(len(STEPS) - 1, max(0, st.session_state.get("gmail_setup_step", 0) + delta))


def setup_guide(root: Path, *, expanded=False):
    with st.expander("Create my Google credentials · 创建自己的凭证", expanded=expanded):
        language = st.selectbox("Guide language / 教程语言", ["English", "中文"], key="gmail_setup_language")
        chinese = language == "中文"
        step = st.selectbox(
            "Setup step / 设置步骤", list(range(len(STEPS))), key="gmail_setup_step",
            format_func=lambda index: f"{index + 1}. {STEPS[index][1 if chinese else 0]}",
        )
        item = STEPS[step]
        st.caption("在 Google 页面由你完成设置；切换步骤不会创建项目或验证配置。" if chinese else
                   "Complete these settings on Google's pages. Step navigation does not create a project or verify its configuration.")
        st.markdown(item[4 if chinese else 3])
        if step == 3:
            st.code("\n".join(SCOPES), language="text")
        if item[2]:
            st.link_button("打开此步骤的 Google 页面" if chinese else "Open this step in Google", item[2])
        left, right = st.columns(2)
        left.button("上一步" if chinese else "Previous step", key="gmail_setup_previous", disabled=step == 0,
                    on_click=_move_step, args=(-1,))
        right.button("下一步" if chinese else "Next step", key="gmail_setup_next", disabled=step == len(STEPS) - 1,
                     on_click=_move_step, args=(1,))
        st.caption("External + Testing 的 Gmail 授权通常七天到期；到期后需重新登录。" if chinese else
                   "With External + Testing, Gmail refresh tokens normally expire after seven days; sign in again when needed.")
        tutorial = root / "docs" / "gmail_setup.md"
        if tutorial.exists():
            content = tutorial.read_text(encoding="utf-8")
            st.download_button("Download full guide · 下载完整教程", content, file_name="eml-google-setup.md", mime="text/markdown")
            with st.expander("完整教程与常见问题 · 中文"):
                st.markdown(content)
