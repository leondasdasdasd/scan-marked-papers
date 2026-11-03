# scan-marked-papers

v1.7.0：老师交 PDF 或已有批阅台链接，即可由智能体推进扫描/批改后的整理和真实同步检查。新增批次链接入口、可交现有浏览器 evaluate 的自包含脚本、离线结果回收、已审目录确认和精确错误诊断。本版通过仓库 main 的 ZIP 分发。

默认完成同步检查并返回批阅台链接，尚不提交课堂；只有本次明确要求同步才执行实际导入。统计准确、题目准确优先，严格审查标准题来源，独立计算式拆为分别可订正的单题。学生个人图按异常修复；姓名看不清暂留未关联，不猜人。实际 blocker 和覆盖不足如实报告，不以部分范围冒充全批通过。

## 安装与更新

从仓库 main 获取 v1.7.0 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)。本轮不创建 GitHub Release，[GitHub Releases](https://github.com/leondasdasdasd/scan-marked-papers/releases) 中旧发布请勿与本版混用；检查最新版本以已核实官方 main 的 [SKILL.md](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/SKILL.md) 元信息及对应提交为准。下载后核对包内 metadata.version 与来源提交，导入或安装后回读实际版本，不以文档标题认定安装成功。

WorkBuddy 使用“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”导入 ZIP；不保证对话粘贴 GitHub 链接即可安装。已有本地技能目录的工具按自身规范安装，例如 Codex 保留解压后的 scan-marked-papers/ 目录。安装前备份旧目录、保留本地修改；只查看更新不自动下载安装。细节见 [技能更新流程](references/skill-update.md) 和 [办公接入说明](references/office-agents.md)。

## 使用与执行路径

把 PDF 交给智能体说“帮我传一下”，或给已有批阅台链接说“接着做到同步检查”。新未批卷需明确快速/智能模式；智能批改需要等长答案卷。使用真实有权访问的批阅台账号、学校与课程/班级，复用实际连接的登录页面，不导出认证材料；新卷无指定地址时使用 https://piyue.yungu.org，先核实环境，不凭域名称生产。

新 PDF 用产品现有文件工具/页面上传，取得批次后，scan 优先内置 CLI：

- 有兼容浏览器后端和实际会话：用 --batch-url 直接传记录链接，run --follow 有界跟进到审图/目录/阻塞/终点。
- 无兼容后端、但现有工具能执行命令和浏览器 evaluate：--emit-script 生成自包含 JS，交目标授权页面原样执行；完整业务结果保存后 collect 回存 checkpoint/output。生成不是执行，emit 只有单轮预算；不另拼 fetch、不猜字段/路由。
- 无 evaluate：按真实页面继续。缺能力时给已核实的接入方法或具体恢复点，不要求老师填写技术参数，不擅装 Agent Browser、插件、Codex、Docker 或运行时。

主 CLI 使用 Python 标准库，正常浏览器后端支持已有 playwright 或兼容 agent-browser，均需真实已登录会话。全参考页校对包渲染另需 pymupdf/Pillow，也可用现有看图工具。CLI 不自动审图、不登录、不接管 Chrome；完整入口与计划见 [CLI 编排](references/cli.md)。

预切正常且有非空题框、实际审过全部参考页后，无修改可零 PATCH 直接确认；预切失败/空框不能这样批准。目录修改仍用真实接口/页面保存，catalog --plan 只确认已审目录与本批范围，不提交课堂；有重复卷先返回审查边界。已审作答结构可定点修复，保留教师原判。checkpoint 是有限恢复记录，不是服务端 exactly-once；超时或部分失败先回读，不重放整包。

grading 的快速/智能批改、目录编辑及未支持步骤沿用真实接口/页面。WorkBuddy 有官方 ZIP 导入路径；豆包办公、千问办公未核实完整包导入/执行契约，Qwen Code 不代表千问办公能力，均按当次工具实际接入。

## 验证边界

v1.7.0通过65项验证：52项 JS 状态/业务行为、4项浏览器后端子进程适配、3项输出/follow、5项 emit/collect/离线渲染入口，以及1项本地 HTTP 隔离全链路。HTTP 验证使用23份合成卷、6道独立题、138条结果，经过参考卷、拆题、目录v2确认的3个审查边界，完成全批 ready；零模型调用。新增离线真实 PDF 校对包渲染及错 SHA 拒绝检查。这验证确定性编排与边界，不代表视觉审核、识别质量、真实登录或线上速度。

本轮未完成 WorkBuddy、豆包办公、千问办公实机实卷验收；未验证课堂实际导入及学生订正，未修改或部署应用前后端。历史真实批次结果不能代替本版办公产品或端到端速度证据，不承诺5分钟或固定token节省。结构统计一致不等于全部判断准确。

仓库不包含账号凭证、试卷或学生数据。
