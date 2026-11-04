# scan-marked-papers

v1.9.0：老师交PDF或已有批阅台链接，由智能体优先用接口与CLI完成上传、课程班级/名单、扫描或快速/智能批改、整理和真实同步检查。定点步骤通过83项受限接口执行；非必要不操作业务页面。

先和老师确定需求：扫描已批试卷，或批改未批试卷；批改后可停止或继续整理，整理后可只检查或同步课堂。扫描本身包含整理。缺少选项集中问一次，已明确选项不重复询问；不再把“处理一下”自动扩展到整理或同步。统计准确、题目准确优先，严格审查标准题来源，独立计算式拆为分别可订正的单题。学生个人图按异常修复；姓名看不清暂留未关联，不猜人。实际 blocker 和覆盖不足如实报告，不以部分范围冒充全批通过。

## 安装与更新

分发入口为仓库main的 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)。可安装版本以已核实官方main的 [SKILL.md](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/SKILL.md) 元信息及对应提交为准，[GitHub Releases](https://github.com/leondasdasdasd/scan-marked-papers/releases) 中历史包请勿与main混用。下载后核对固定提交来源、包完整性与metadata.version，按变化摘要和CLI help判断兼容性；不全仓源码diff，不要求包附带tests/docs。安装后回读实际版本，不以文档标题认定安装成功。

正常使用先运行`python3 <技能目录>/scripts/skill_update.py ensure`，每天首次按本机自然日检查官方main；当天已有记录就读缓存，有更高版本自动校验、备份并只更新本技能，成功后回读新技能。版本相同或本地较新只记录，不降级；网络失败记录当天失败，不在每个步骤重复联网。只看版本用离线`status`，明确立即刷新才`ensure --force`。用户明确关闭时由智能体设置PAPERFLOW_AUTO_UPDATE=0（false/off也可），force仍不绕过。此检查不是后台定时任务，无人使用不会唤醒。

v1.9.0起分发包内置release-manifest.json作为文件校验和本地基线；本地修改冲突自动保留旧版，旧安装缺manifest时需先显式升级至1.9.0，不自动强覆盖。登录态、checkpoint及其他技能不受更新操作影响。开发Git checkout及离线help/api-list/collect/离线review不触发自动更新。

WorkBuddy 使用“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”导入 ZIP；不保证对话粘贴 GitHub 链接即可安装。已有本地技能目录的工具按自身规范安装，例如 Codex 保留解压后的 scan-marked-papers/ 目录。安装前备份旧目录、保留本地修改；只查看更新不自动下载安装。无Python或可靠文件替换能力的办公产品不能保证自动更新，按现有工具与真实能力处理。细节见 [技能更新流程](references/skill-update.md) 和 [办公接入说明](references/office-agents.md)。

## 使用与执行路径

把PDF交给智能体后，可直接说“扫描，整理后检查”“扫描并同步课堂”“批改，批完停止”“批改，整理后检查”或“批改，整理并同步课堂”。未说明时智能体先补齐选择；已有批阅台链接则恢复同一记录及已确认终点。新未批卷需明确快速/智能模式；智能批改需要等长答案卷。使用真实有权访问的批阅台账号、学校与课程/班级，复用实际连接的登录页面，不导出认证材料；新卷无指定地址时使用 https://piyue.yungu.org，先核实环境，不凭域名称生产。

全流程先完成每日ensure并回读实际技能，再用内置CLI：access核验会话，classes/class-students读取目录，upload经FormData创建批次，scope保存本次课程班级，run按scan或grading和教师选择的终点推进；只批改用--stop-after grading，整理路径用--stop-after check，同步再单独执行已授权sync。文件工具仅在需要时注入文件，不默认点击上传/选班表单。

- 有兼容浏览器后端和实际会话：用 --batch-url 直接传记录链接，run --follow 有界跟进到审图/目录/阻塞/终点。
- 无兼容后端、但现有工具能执行命令和浏览器evaluate：--emit-script生成一次加载的引擎与小步骤脚本。首次或导航后加载engine_file，后续同页面只执行小步骤并collect，避免逐轮展开完整引擎；--standalone-script保留旧兼容形式。生成不是执行，emit只有单轮预算，不手写fetch/XHR或猜路由。
- 编排未覆盖的定点步骤先查api-list，用受限api-call；每项接口的功能、关键字段与前置条件见 [API参考](references/api.md)。写计划保留真实证据与当前版本，imports仅可走明确授权的专用sync命令。
- evaluate是同源接口执行宿主；除正常登录、确需文件注入和必要图证外，只有接口/工具具体不兼容才使用页面。缺能力时给已核实接入方法或恢复点，不要求老师配置参数，不擅装Agent Browser、插件、Codex、Docker或运行时。

主 CLI 使用 Python 标准库，正常浏览器后端支持已有 playwright 或兼容 agent-browser，均需真实已连接会话。`access` 检查身份和课堂会话，失效时 `relogin` 启动一次既有登录导航；导航完成后重新验证同一教师与学校，授权链接只在浏览器内存使用。`roster` 一次给出关联覆盖及未关联卷定位；初次常规查看清楚者可批量关联，模糊者直接暂留，不追加放大/OCR或用剩余名单试探。媒体运行中由 run --follow 有界等待，检查结论以 completion/remaining 与全批覆盖为准。全参考页校对包渲染另需 pymupdf/Pillow，也可用现有看图工具；CLI 不自动审图、不接管 Chrome。完整入口与计划见 [CLI 编排](references/cli.md)。

预切正常且有非空题框、实际审过全部参考页后，无修改可零PATCH确认；失败/空框不能批准。目录修改用受限编辑接口保存并回读，catalog --plan只确认已审目录与本批范围，不提交课堂；有重复卷先处理审查边界。已审作答结构可定点修复，保留教师原判。checkpoint是有限恢复记录，不是服务端exactly-once；超时或部分失败先回读，不重放整包。

仅选择整理时，供应商批改完成后接统一organizer；LLM按答案卷与该模式实际整理入口推进，不强套scan参考卷。WorkBuddy有官方ZIP导入路径；豆包办公、千问办公未核实完整包导入/执行契约，Qwen Code不代表千问办公能力，均按当次工具实际接入。

## 验证边界

v1.9.0通过128项隔离验证：92项JS状态/业务行为、36项Python入口与适配验证。本轮新增19项Python验证，覆盖每日缓存、跨日和手动force、实际升级、保留checkpoint与其他技能、本地修改与新增目标文件冲突、失败缓存、不降级、旧版无manifest、文件和路径校验、失败回滚、官方删除文件、符号链接、开发checkout、并发锁与禁用；另验证真实CLI入口的自动检查、更新后重启、失败保留旧版继续以及离线命令不联网。

原有教师路径选择与“批完停止”编排、done但缺结果保留grading_incomplete、uncertain/unknown保留、终点持久化和变更验证仍通过；目录、受限接口、版本保护、专用同步边界、真实HTTP multipart上传、CLI emit/collect、引擎缓存、离线PDF校对和错SHA拒绝覆盖仍保留。

真实HTTP验证使用同一份2页合成PDF重复接续，仅创建一次文件POST和一次班级PUT，复用原batch并核对原字节、幂等与分卷边界。引擎缓存用于同页面复用代码、小步骤推进；历史v1.8.0的classes样例曾测得707字节小步骤与80974字节引擎，仅是旧版本脚本文本证据，不代表本版大小、token用量或线上耗时。全部验证使用合成/隔离服务，不调用线上模型，不证明真实CAS登录、识别质量、视觉审核或线上性能。

尚未完成WorkBuddy、豆包办公、千问办公实机实卷验收，未验证课堂实际导入及学生订正；技能更新不包含修改或部署应用前后端。历史真实批次结果不能代替本版办公产品或端到端速度证据，不承诺5分钟或固定token节省。结构统计一致不等于全部判断准确。

仓库不包含账号凭证、试卷或学生数据。
