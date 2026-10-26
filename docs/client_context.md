# 文件夹、邮件选择与客户资料：设计和复用

这版解决两件事：老板界定本次使用的邮件；客户资料从这些材料中逐步建立，
确认后重复使用。邮件范围、客户背景、已完成工作分别建模。

## 文件夹到底是什么

| Outlook 中看到的内容 | 实际含义 | 本版处理 |
| --- | --- | --- |
| Gmail 账户下通过 IMAP 同步的文件夹 | Gmail 将标签表现为 IMAP 文件夹；一封邮件可有多个标签 | 列出 Gmail 标签，按真实 label ID 读取 |
| On My Computer 本地文件夹 | 仅在 Outlook 本地，未同步到服务器 | 需要另行实现、实测本地读取 |
| Smart Folder / 搜索文件夹 | 保存查询产生的动态结果 | 需要读取结果或重建查询，不能当成 Gmail 标签 |

AppleScript dictionary 描述应用支持的对象、属性和命令，不是实际客户文件夹清单。
目标 Mac 上的具体术语可以用只读诊断工具查看：

~~~bash
python helpers/inspect_outlook_dictionary.py
~~~

它调用系统 sdef，打印文件夹相关定义，不扫描邮件。无 sdef 或 Outlook 时明确失败。
它不承诺直接读取当前文件夹，也不执行猜测的 AppleScript 枚举命令。

在已登录 Gmail 的原项目目录中列出真实服务端标签：

~~~python
from fetch_emails import get_gmail_service
from eml_core import GmailMailbox

mailbox = GmailMailbox(get_gmail_service())
for label in mailbox.list_labels(user_only=True):
    print(label["id"], label["name"])
~~~

先核对 Outlook 文件夹所属账户、Gmail 网页标签和少量邮件是否一致，再建立映射。
同名不足以确认映射。嵌套标签默认不包含，开启后按完整路径的 / 前缀展开。

## 老板选定的邮件范围

~~~python
from datetime import date
from eml_core import Selection

result = mailbox.select(Selection(
    label_ids=("Label_123", "Label_456"),  # 替换为实际返回的标签 ID
    include_sub_labels=False,
    start_date=date(2026, 10, 1),          # 日期也可以都不提供
    end_date=date(2026, 10, 31),
))
print(len(result.messages), result.complete, result.warnings)
~~~

- 多标签取并集，按 message ID 去重，不误用 Gmail API 的多标签交集。
- 自动读取所有分页；设置 max_messages 后若超限，会标记为不完整。
- 日期包含起止日，按 Australia/Sydney 处理夏令时，并逐封重新检查。
- 标签按邮件读取，不自动拉入同会话中未选中的其他邮件。
- 子标签需要明确选择；显式标签范围也能读取其中的垃圾邮件/垃圾箱邮件。
- 无效标签 ID 会报错，不回退成全邮箱检索；API 失败不报告完整成功。
- 正文支持纯文本和 HTML，不截断 5,000 字；附件仅保留名称，不读取内容。

若 Gmail 把文本正文单独存放为 attachmentId，本版会明确报错而不会当成空正文；
这类邮件的额外正文下载尚未接入。

程序调用还支持具体邮件和整个会话，每次只能提供一种来源：

~~~python
exact = mailbox.select(Selection(message_ids=("gmail-message-id",)))
threads = mailbox.select(Selection(thread_ids=("gmail-thread-id",)))
~~~

选择单封邮件不扩大为整个会话，选择整个会话时仍逐封筛选日期。
Outlook 多选通过 Internet Message-ID 精确映射：

~~~python
from outlook_adapter import get_selected_outlook_message_ids

ids = get_selected_outlook_message_ids()
result = mailbox.select(Selection(internet_message_ids=tuple(ids)))
~~~

匹配不到或有多个匹配时会报错，不按主题猜测。新增 AppleScript 沿用原有
selected objects / headers 术语，必须在实际 Mac 上测试。这不是 Office.js 多选。

## 客户资料从哪里来

1. **现有客户清单。** 有 clients.json 时直接导入。已有 CRM、客户登记表或
   engagement 文件时，可先整理成此格式；本版未连接这些外部系统。
2. **选中的邮件。** 提取联系人和明确写出的公司、行业、业务描述，先作为候选。
   收件人、抄送者可能是第三方，不自动确认为该客户联系人。
3. **人工补充。** 保存客户群、公司业务、已知合作范围、老板备注。
   未写出的信息留空，不按域名或零散关键词猜测。
4. **按需补充历史材料。** 可另选该客户历史邮件更新背景；这些材料不自动成为
   本期收费依据。

背景不完整也能先选邮件。默认规则识别显式行，例如：

~~~text
Company: Example Pty Ltd
Industry: Wholesale
Business: Wholesale supply of household goods
Agreed services: Quarterly bookkeeping review
~~~

它不会理解任意自然语言中的复杂关系，也不会因为出现 BAS/GST 就认定客户需要
某项服务或事务所已完成工作。未确认候选不进入已确认背景。
同一邮箱可出现在多个客户群，一个客户群可包含多个公司，不强行一对一。

## 更新、审核和复用

~~~python
from eml_core import ProfileStore, RuleExtractor, update_profile

with ProfileStore("data/client_profiles.sqlite3") as store:
    client_id = store.create_client("Alex group")  # 以后复用已有 client_id
    summary = update_profile(
        store, client_id, result.account_id, result.messages,
        RuleExtractor(own_addresses=[result.account_id],
                      excluded_domains=["your-firm.example"]),
    )
    for suggestion in store.list_facts(client_id, "pending"):
        print(suggestion["fact_id"], suggestion["value"], suggestion["evidence"])
        # 实际界面由用户逐条决定，不自动全部确认。
    # store.review(client_id, chosen_fact_id, "confirmed")
    # store.review(client_id, chosen_fact_id, "rejected")
    context = store.context(client_id)
~~~

资料默认在 data/client_profiles.sqlite3，Git 忽略该目录。工作界面也支持用
EML_PROFILE_DB 环境变量指定其他数据库位置。

增量提取按客户 ID、邮箱 ID、邮件 ID、内容指纹和提取器版本/配置判断。
候选和已处理记录使用同一事务，失败可重试，重复邮件不重复提取。
新证据不改变已有确认/拒绝状态。行业等单值字段冲突需要明确选择替换，
旧值保留为 superseded。跨客户、跨邮箱的处理记录分别保存。

**本版增量范围：** 每次点击获取仍会重新列出选定范围并读取邮件，再按指纹跳过
重复资料提取。尚未实现 Gmail history 增量同步或正文缓存。高频、大文件夹使用
可再加入缓存和 history，并处理 history 过期后的重新同步。不自动后台扫描全邮箱。

~~~python
with ProfileStore("data/client_profiles.sqlite3") as store:
    store.add_manual(client_id, "business_description", "老板确认的业务说明")
    store.add_manual(client_id, "entities", {"name": "Another Pty Ltd"})
    store.add_manual(client_id, "potential_need", "有待核实的潜在服务需求")
~~~

possible_needs 始终单独作为假设输出，保留它不表示已提供服务。
export_legacy() 导出已确认背景，格式兼容原 app.py，不含待审核候选或潜在需求。
工作界面提供下载，用户核对后可替换原 clients.json。
import_legacy(data) 支持原单对象、列表和包含 clients 列表的格式；
相同 client_id 已存在时不覆盖。

## 后续模型与边界

本地模型可实现 profiles.Extractor 协议，提供稳定 version 和
extract(message, mailbox_id)，返回带 Evidence 的 Candidate。
正文引用必须实际出现在输入邮件，来源 ID 必须属于该输入；输出仍需审核。
模型不能自行确认候选。跨邮件复杂关系推断需要另行设计分组与合并。

本版不包含模型推理、服务活动提取、工时/金额推断、Word 报告或 Office.js 插件。
这些功能可复用本版明确的邮件范围、客户背景和来源 ID。

## 验证与官方资料

~~~bash
python -m eml_core.demo
python -m unittest discover -s tests -v
~~~

自动测试覆盖分页、标签并集、子标签开关、精确选择、跨月与夏令时、MIME 正文、
候选审核、来源校验、重复处理、失败重试、客户/邮箱隔离和界面切换。
Gmail 和 Outlook 使用测试替身；真实 OAuth、标签对应关系、Mac AppleScript
需要在目标环境做一次端到端验证。

- [Gmail IMAP 标签与文件夹](https://developers.google.com/workspace/gmail/imap/imap-extensions)
- [Gmail 标签列表](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.labels/list)
- [Gmail 邮件分页与标签过滤](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/list)
- [Gmail 日期与搜索](https://developers.google.com/workspace/gmail/api/guides/filtering)
- [Gmail 同步与 history 过期](https://developers.google.com/workspace/gmail/api/guides/sync)
- [Outlook Mac 本地文件夹](https://support.microsoft.com/en-us/outlook/about-on-my-computer-folders-in-outlook-for-mac)
- [Outlook Mac Smart Folder](https://support.microsoft.com/en-au/outlook/save-a-search-by-using-a-smart-folder-in-outlook-for-mac)
- [Outlook 插件多选限制](https://learn.microsoft.com/en-us/office/dev/add-ins/outlook/item-multi-select)
