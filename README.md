# scan-marked-papers

v1.8.0：老师交PDF或已有批阅台链接，由智能体优先用接口与CLI完成上传、课程班级/名单、扫描或快速/智能批改、整理和真实同步检查。定点步骤通过83项受限接口执行；非必要不操作业务页面。

默认完成同步检查并返回批阅台链接，尚不提交课堂；只有本次明确要求同步才执行实际导入。统计准确、题目准确优先，严格审查标准题来源，独立计算式拆为分别可订正的单题。学生个人图按异常修复；姓名看不清暂留未关联，不猜人。实际 blocker 和覆盖不足如实报告，不以部分范围冒充全批通过。

## 安装与更新

分发入口为仓库main的 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)。可安装版本以已核实官方main的 [SKILL.md](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/SKILL.md) 元信息及对应提交为准，[GitHub Releases](https://github.com/leondasdasdasd/scan-marked-papers/releases) 中历史包请勿与main混用。下载后核对固定提交来源、包完整性与metadata.version，按变化摘要和CLI help判断兼容性；不全仓源码diff，不要求包附带tests/docs。安装后回读实际版本，不以文档标题认定安装成功。

WorkBuddy 使用“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”导入 ZIP；不保证对话粘贴 GitHub 链接即可安装。已有本地技能目录的工具按自身规范安装，例如 Codex 保留解压后的 scan-marked-papers/ 目录。安装前备份旧目录、保留本地修改；只查看更新不自动下载安装。细节见 [技能更新流程](references/skill-update.md) 和 [办公接入说明](references/office-agents.md)。

## 使用与执行路径

把 PDF 交给智能体说“帮我传一下”，或给已有批阅台链接说“接着做到同步检查”。新未批卷需明确快速/智能模式；智能批改需要等长答案卷。使用真实有权访问的批阅台账号、学校与课程/班级，复用实际连接的登录页面，不导出认证材料；新卷无指定地址时使用 https://piyue.yungu.org，先核实环境，不凭域名称生产。

全流程先用内置CLI：access核验会话，classes/class-students读取目录，upload经FormData创建批次，scope保存本次课程班级，run按scan或grading真实阶段推进。文件工具仅在需要时注入文件，不默认点击上传/选班表单。

- 有兼容浏览器后端和实际会话：用 --batch-url 直接传记录链接，run --follow 有界跟进到审图/目录/阻塞/终点。
- 无兼容后端、但现有工具能执行命令和浏览器evaluate：--emit-script生成一次加载的引擎与小步骤脚本。首次或导航后加载engine_file，后续同页面只执行小步骤并collect，避免逐轮展开完整引擎；--standalone-script保留旧兼容形式。生成不是执行，emit只有单轮预算，不手写fetch/XHR或猜路由。
- 编排未覆盖的定点步骤先查api-list，用受限api-call；每项接口的功能、关键字段与前置条件见 [API参考](references/api.md)。写计划保留真实证据与当前版本，imports仅可走明确授权的专用sync命令。
- evaluate是同源接口执行宿主；除正常登录、确需文件注入和必要图证外，只有接口/工具具体不兼容才使用页面。缺能力时给已核实接入方法或恢复点，不要求老师配置参数，不擅装Agent Browser、插件、Codex、Docker或运行时。

主 CLI 使用 Python 标准库，正常浏览器后端支持已有 playwright 或兼容 agent-browser，均需真实已连接会话。`access` 检查身份和课堂会话，失效时 `relogin` 启动一次既有登录导航；导航完成后重新验证同一教师与学校，授权链接只在浏览器内存使用。`roster` 一次给出关联覆盖及未关联卷定位；初次常规查看清楚者可批量关联，模糊者直接暂留，不追加放大/OCR或用剩余名单试探。媒体运行中由 run --follow 有界等待，检查结论以 completion/remaining 与全批覆盖为准。全参考页校对包渲染另需 pymupdf/Pillow，也可用现有看图工具；CLI 不自动审图、不接管 Chrome。完整入口与计划见 [CLI 编排](references/cli.md)。

预切正常且有非空题框、实际审过全部参考页后，无修改可零PATCH确认；失败/空框不能批准。目录修改用受限编辑接口保存并回读，catalog --plan只确认已审目录与本批范围，不提交课堂；有重复卷先处理审查边界。已审作答结构可定点修复，保留教师原判。checkpoint是有限恢复记录，不是服务端exactly-once；超时或部分失败先回读，不重放整包。

供应商批改完成后接统一organizer；LLM按答案卷与该模式实际整理入口推进，不强套scan参考卷。WorkBuddy有官方ZIP导入路径；豆包办公、千问办公未核实完整包导入/执行契约，Qwen Code不代表千问办公能力，均按当次工具实际接入。

## 验证边界

v1.8.0通过99项隔离验证：84项JS状态/业务行为、15项Python入口与适配验证。覆盖scan/grading编排、目录、受限接口与运行时版本保护、专用同步边界，以及真实HTTP multipart上传、CLI emit/collect和回读。同一份2页合成PDF重复接续仅创建一次文件POST和一次班级PUT，复用原batch，核对原字节、幂等与分卷边界；另验证引擎缓存执行。classes样例的小步骤为707字节、一次加载引擎为80974字节，同页后续脚本文本减少99.13%，仅代表该样例脚本文本，不推断token用量或线上耗时。保留原有全链路、离线PDF校对包及错SHA拒绝覆盖；验证使用合成/隔离服务，不调用线上模型，不证明真实CAS登录、识别质量、视觉审核或线上性能。

尚未完成WorkBuddy、豆包办公、千问办公实机实卷验收，未验证课堂实际导入及学生订正；技能更新不包含修改或部署应用前后端。历史真实批次结果不能代替本版办公产品或端到端速度证据，不承诺5分钟或固定token节省。结构统计一致不等于全部判断准确。

仓库不包含账号凭证、试卷或学生数据。
