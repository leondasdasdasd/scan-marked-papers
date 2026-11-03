# scan-marked-papers

v1.6.0：试卷批改、扫描与整理技能，支持新卷快速批改、智能批改、已批教师卷扫描，以及从已有记录链接接着做。本版增加 WorkBuddy ZIP 试用说明和可选 Agent Browser CLI 后端；优先使用当前产品已有浏览器与同源接口，没有 CLI 时按真实页面继续。

默认只完成同步检查，交付批阅台链接，不提交课堂；只有本次明确要求实际同步才进入原同步流程。统计准确、题目准确优先，严格核对参考图，独立计算式逐题拆成可订正单题。学生个人图按风险处理，全量准确性深审由老师另选。看不清的姓名暂留未关联，完成后集中报告试卷份号、页码与实际可见特征，不猜人。

## 安装与更新

从本仓库 **main** 下载 v1.6.0 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)。WorkBuddy 按官方入口“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”上传该 ZIP；不保证在对话里贴 GitHub 链接即可安装自有包。详细接入与官方来源见 [office-agents.md](references/office-agents.md)。

已有本地技能目录的工具可按自身规范安装；例如 Codex 解压到 `~/.codex/skills/` 并保留 `scan-marked-papers/` 目录。安装前备份旧目录、保留本地修改；导入或安装后核对实际 `SKILL.md` 的 `metadata.version` 为 `1.6.0`。WorkBuddy 不以安装 Codex、Docker 或云主机 wrapper 为前提。

本版安装包位于仓库 **main**；[GitHub Releases](https://github.com/leondasdasdasd/scan-marked-papers/releases) 中的旧发布不是 v1.6.0，请勿混用。更新流程见 [skill-update.md](references/skill-update.md)，只查看版本不等于安装，不自动更新。豆包办公、千问办公尚未核实自定义完整包的导入/执行契约，也未实测；只能按其当前实际工具能力接入，Qwen Code 的能力不能代替千问办公。

## 使用与依赖

把 PDF 交给智能体说“帮我传一下”，或给已有批阅台链接说“接着做到同步检查”。已有链接由智能体提取 origin；新卷未指定地址时使用 `https://piyue.yungu.org`，先核实真实环境、身份与学校，不凭域名称生产，不让老师填写 CLI 参数。新未批卷需明确快速/智能模式；智能批改需要等长答案卷。使用自己的批阅台账号与对应课程、班级权限，复用实际连接的已授权登录会话，不导出 Cookie、令牌或 storage state，不关闭用户原有页面。

新 PDF 先用产品原生文件工具/页面上传，取得批次后再接可用 CLI。CLI 是可选路径：已有 Python 时可选 `--browser-backend playwright|agent-browser`，默认 playwright 保持兼容；Agent Browser 后端要求现有可执行文件支持 `eval --stdin`、`--session` 和所需 JSON 响应，且实际连接授权会话，不会自动接管用户 Chrome。没有兼容后端就使用原生浏览器，不擅装 Agent Browser、插件或运行时。缺能力时一次说明可执行接入方式或真实阻塞，不反复索要技术参数。CLI 使用 Python 标准库；本地生成全参考页和接触表另需 `pymupdf`、`Pillow`，也可使用产品已有看图工具。完整契约见 [cli.md](references/cli.md)。

新版 CLI 当前仅支持 `workflow_mode=scan`。优先用 `run --follow` 在有界时间内跟进等待，直到需要审图、目录校对、阻塞处理或到达终点；默认输出紧凑摘要，全局 `--output` 保存完整 JSON，必要时用 `--verbose` 查看完整输出。一次生成的校对包和精简目录可复用，避免反复读取大响应。

预切失败通过 `diagnose` 集中诊断；完成阶段的 review_tasks 按卷、题和页码组织阻塞，再用 `evidence` 获取必要的目录与作答证据定位。实际审卷后，可用 `responses --plan` 定点修复作答结构：选择位置映射到真实稳定选项 ID，逐空作答按真实空位对应，保留教师判定；不调用模型，不自动猜答案。已有父子框可在审图后显式提升为独立题。校对包或确认标记本身不代表已完成视觉验收。

grading 的批改、目录内容保存/确认及 CLI 未支持的恢复步骤仍走原接口/页面；CLI 不自动处理所有工作流，也不提交导入。客户端检查点与顺序修复不是服务端 exactly-once 或跨请求事务；超时或部分失败先回读已保存状态，再处理剩余范围，不重放整包动作。

## 验证与速度边界

v1.6.0 完成浏览器后端适配与文档更新，通过 4 项隔离子进程适配测试、39 项既有合成 CLI 回归及 3 项输出/follow 检查。子进程测试不是真浏览器，本轮未安装 Agent Browser，未完成 WorkBuddy 实机实卷联调；豆包办公、千问办公也未实测。可导入试用不等于这些产品已全流程验收。

历史 v1.5.0 曾完成 24 份、288 条作答的真实全批 ready 检查，耗时 8 分 58 秒；该次复用旧身份关联，不是严格前后对照，不能据此推断本版或办公产品耗时。此前真实目录离线输出由 72,346 降至 7,749 字符（89.29%），也只代表输出量，不代表 token 降幅或整体提速。课堂实际导入与学生订正仍未验证；快速/智能批改不在本版 CLI 支持范围。结构统计一致不等于全量判断准确，检查未通过或未关联范围必须如实报告。

仓库不包含账号凭证、试卷或学生数据。
