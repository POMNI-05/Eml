# 本地 AI 与自动生成

本版使用本机 Ollama 的结构化输出接口，不需要商业模型 API key。
模型需要先下载到电脑；生成速度、长文档能力和判断质量需要在实际电脑上测试。

## 启动本地模型

1. 从 [Ollama 官网](https://ollama.com/download) 安装并打开 Ollama。
2. 在终端下载一个本地模型。例如：

~~~bash
ollama pull qwen3:8b
ollama list
~~~

可以选择其他已下载、支持结构化输出的本地模型。上面只是接入示例，不保证适合所有电脑。
Linux 等未自动启动服务的环境，需要先运行 ollama serve。

3. 在 Eml 左侧展开 **Local AI setup**，保留本机地址：

~~~text
http://127.0.0.1:11434
~~~

4. 点击 **Load local models**，选择本地模型、上下文大小和输出语言。
本版只连接 localhost，不选择 cloud 模型，不自动下载模型。

## 让背景文件参与工作

1. 在 **Background documents** 上传客户资料、公司关系说明或 engagement 文件。
   Word 表格和可搜索 PDF 的页码/位置会保留；扫描页不做 OCR。
2. 点击 **Analyse documents with AI**，获得公司、联系人、关系、业务和服务范围候选。
3. 在 **Client context** 核对引用并确认。未确认的解释不进入已确认客户档案。
4. 在 **Choose emails → Client search** 中，已确认的公司名、联系人邮箱和别名会参与检索。
   最终邮件仍由用户在 Include these messages 中选择。
5. 在 **Generate draft** 选择要交给模型的背景文件，点击 **Generate work record draft**。

每次生成传入的是：

- 该客户已确认的档案，包括公司关系、业务说明、合作范围和来源；
- 明确选择的背景文件内容及位置；
- 明确选择的邮件正文、日期、发件人和 message ID；
- 范围是否完整、排除了哪些邮件，以及输出语言。

**背景帮助理解，工作活动必须有本次选中邮件支持。**
模型不会生成工时、费率或金额。请求、进行中、明确完成和状态不明分别记录；
这些分类仍需人工核对。引用不在选中邮件中、引用原文不存在或 JSON 格式不合格时，
程序不会保存这次草稿。

## 审核和输出

生成后可以修改活动描述、对应公司、状态和审核备注，排除不需要的记录，
查看原邮件引用，下载 Word，以及保存编辑后的草稿。
Word 包含客户背景、工作记录、待确认问题和邮件证据索引。
未经审核的版本保留 draft 标记。保存的历史草稿绑定当时的输入快照。
查看或转换包含中文的 Word 时，电脑需要可用的中文字体，例如 Noto Sans CJK SC；
导出的文档为中日韩文字设置了该字体名，Word 也可使用本机中文字体替代。

更换客户、邮件、背景、已确认档案或模型后，旧草稿不会作为新输入的当前结果显示。
仍可在 Saved drafts 中明确打开旧快照。

上下文超过设置时程序会报错，不静默截断或遗漏文档。可以减少选中的材料，
或在电脑和模型支持时增加 Model context size。尚未加入多轮分块总结或 OCR。

没有启动模型时，也可以在 Generate draft 下载 **AI evidence package**，
其中包含客户背景、文档和邮件，便于后续使用其他已获准的分析方式。

## 验证边界

代码测试覆盖本地 HTTP 接口、数据包、引用检查和 Word 生成。开发环境没有读取真实客户邮箱，
也没有用客户材料测试实际 Ollama 模型；真实 OAuth、Mac Outlook 与模型质量需要在目标电脑验证。

官方资料：[Ollama quickstart](https://docs.ollama.com/quickstart)、
[Structured outputs](https://docs.ollama.com/capabilities/structured-outputs)、
[Chat API](https://docs.ollama.com/api/chat)、
[Qwen3 8B 示例](https://ollama.com/library/qwen3:8b)。
