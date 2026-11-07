# scan-marked-papers

可安装版本按下方“安装与更新”核实。已有可用任务会话直接核实身份，未确定路径时才尝试现成独立接入；接口与 CLI 复用已核实会话，保留老师的浏览器。老师交 PDF 或已有批阅台链接后，按选择完成上传、课程班级/名单、扫描或快速/智能批改、整理和真实同步检查；定点步骤通过 83 项受限接口执行。

先和老师确定需求：扫描已批试卷，或批改未批试卷；批改后可停止或继续整理，整理后可只检查或同步课堂。扫描本身包含整理。缺少选项集中问一次，已明确选项不重复询问；不再把“处理一下”自动扩展到整理或同步。统计准确、题目准确优先，严格审查标准题来源，独立计算式拆为分别可订正的单题。学生个人图按异常修复；首次无可靠身份则跳过身份处理，保留原卷与未关联，记录卷数、页码和原因，不追加放大/OCR、名单排除或反复识别，不追问、不为凑通过重试；继续其余安全整理，不硬干、不猜人。已明确选择跳过无可靠身份时，每次显式使用check/run的--skip-unlinked，按eligible_check报告真实范围结果及full_batch_ready=false；不持久化范围、不授权同步，不以范围达标冒充全批通过。其他blocker和覆盖不足仍如实报告。

## 安装与更新

分发入口为仓库main的 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)。可安装版本以已核实官方main的 [SKILL.md](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/SKILL.md) 元信息及对应提交为准，[GitHub Releases](https://github.com/leondasdasdasd/scan-marked-papers/releases) 中历史包请勿与main混用。下载后核对固定提交来源、包完整性与metadata.version，按变化摘要和CLI help判断兼容性；不全仓源码diff，不要求包附带tests/docs。安装后回读实际版本，不以文档标题认定安装成功。

正常使用先运行`python3 <技能目录>/scripts/skill_update.py ensure`，每天首次按本机自然日检查官方main；当天已有记录就读缓存，有更高版本自动校验、备份并只更新本技能，成功后回读新技能。版本相同或本地较新只记录，不降级；网络失败记录当天失败，不在每个步骤重复联网。只看版本用离线`status`，明确立即刷新才`ensure --force`。用户明确关闭时由智能体设置PAPERFLOW_AUTO_UPDATE=0（false/off也可），force仍不绕过。此检查不是后台定时任务，无人使用不会唤醒。

v1.9.0起分发包内置release-manifest.json作为文件校验和本地基线；本地修改冲突自动保留旧版，旧安装缺manifest时需先显式升级至1.9.0，不自动强覆盖。登录态、checkpoint及其他技能不受更新操作影响。开发Git checkout及离线help/api-list/collect/离线review不触发自动更新。

WorkBuddy 使用“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”导入 ZIP；不保证对话粘贴 GitHub 链接即可安装。已有本地技能目录的工具按自身规范安装，例如 Codex 保留解压后的 scan-marked-papers/ 目录。安装前备份旧目录、保留本地修改；只查看更新不自动下载安装。无Python或可靠文件替换能力的办公产品不能保证自动更新，按现有工具与真实能力处理。细节见 [技能更新流程](references/skill-update.md) 和 [办公接入说明](references/office-agents.md)。

## 使用与执行路径

把PDF交给智能体后，可直接说“扫描，整理后检查”“扫描并同步课堂”“批改，批完停止”“批改，整理后检查”或“批改，整理并同步课堂”。未说明时智能体先补齐选择；已有批阅台链接则恢复同一记录及已确认终点。新未批卷需明确快速/智能模式；智能批改需要等长答案卷。使用真实有权访问的批阅台账号、学校与课程/班级，登录材料只允许内置脚本受控使用，不进入聊天、日志或文件；新卷无指定地址时使用 https://piyue.yungu.org，先核实环境，不凭域名称生产。

全流程先完成每日 ensure 并回读实际技能；已有本轮可用后端与任务会话时直接 access；尚未确定路径才尝试一次 session-connect，复用已核验的独立会话，或从现成已授权 CDP 定点迁移必要登录态。连接成功后，正常 CLI 按同 origin 和任务会话名自动使用独立浏览器；access 核验身份与课堂会话，classes/class-students 读取目录，upload 经 FormData 创建批次，scope 保存本次课程班级，run 按真实模式及教师选择的终点推进。只批改用 --stop-after grading，整理路径用 --stop-after check，同步再单独执行已授权 sync；文件工具仅在需要时注入文件。上传已授权时优先用回执preview_papers现成平台原页核来源/结构；尚未绑定范围时先核图再scope，已有可靠确认的scope-plan可随上传正常绑定，CLI不拦截，不默认本地渲染或额外snapshot；意图未定不为看图先建批次。

- 有独立会话：用 --batch-url 和同一 --browser-session 续做；--browser-backend isolated 可明确禁止回退用户页面，run --follow 有界跟进到审图/目录/阻塞/终点。
- 无既有独立记录且缺接入能力、但已有兼容后端和实际授权会话：按诊断使用现有 playwright/agent-browser；有失效独立记录时保留恢复点，确需回退先 session-close 再核验其他授权会话，不静默切换。这不代表已迁移成功。
- 无兼容后端、但现有工具能执行命令和浏览器evaluate：--emit-script生成一次加载的引擎与小步骤脚本。首次或导航后加载engine_file，后续同页面只执行小步骤并collect，避免逐轮展开完整引擎；--standalone-script保留旧兼容形式。生成不是执行，emit只有单轮预算，不手写fetch/XHR或猜路由。
- 编排未覆盖的定点步骤先查api-list，用受限api-call；每项接口的功能、关键字段与前置条件见 [API参考](references/api.md)。写计划保留真实证据与当前版本，imports仅可走明确授权的专用sync命令。
- evaluate 是同源接口执行宿主，无法仅靠 document.cookie 迁移 HttpOnly 登录态；除正常登录、确需文件注入和必要图证外，只有接口/工具具体不兼容才使用页面。缺能力时给已核实接入方法或恢复点，不要求老师配置参数，不擅装 Agent Browser、插件、Codex、Docker、浏览器或运行时。

CLI入口需要现有Python3，普通编排使用标准库；新PDF优先用现有解析器核页数，均缺时保留header/hash/size、page_count=null，待服务端权威校验，离线结果不证明PDF有效。可选本地review渲染另需PyMuPDF/Pillow，不自动安装，不是零依赖；独立会话另外要求现有带内置 WebSocket 的 Node、Chrome/Edge/Chromium，以及已开放且已授权的来源 CDP。当前支持 piyue.yungu.org、HTTPS 的 *.app.yungu.org 及 loopback，不保证任意办公产品都能静默读取用户登录态。源页不导航、不点击，不读取或解密浏览器 Cookie 数据库，不重启用户 Chrome 开调试；目标仅接收缩到本 host 的 SESSION，建立新的 paper_session，并核验同一教师、学校和有效课堂会话。Cookie 只在受控进程内存中传递，受限本地控制记录不含 Cookie/令牌；任务结束用 session-close 清理目标上下文及本次自建浏览器，不退出源登录态、不跟随 SSO 全局退出。

`access` 检查身份和课堂会话，失效时 `relogin` 启动一次既有登录导航；独立会话的恢复只在独立页进行，之后重新验证同一教师与学校。`roster` 一次给出关联覆盖及未关联卷定位；初次常规查看清楚者可批量关联；身份无可靠证据就停止关联并跳过身份处理；仅本次明确授权时可采用[SKILL.md](SKILL.md)规定的首轮清楚班级/班内number唯一精确匹配且无冲突例外，不追加放大/OCR、不猜编号或用剩余名单试探。媒体运行中由 run --follow 有界等待，检查结论以 completion/remaining 与全批覆盖为准。审图默认用平台现有授权原页/题图和宿主看图能力或现有浏览器截图，题图缺上下文或批注须对照原页；不默认下载整份PDF或生成校对包。本地review仅在离线、平台图不可用或明确像素校准等具体理由下回退，渲染缺依赖不阻断平台图片主路径；URL、图包与标记均不代表实际已审。完整入口与计划见 [CLI 编排](references/cli.md)。

预切正常且有非空题框、实际审过全部参考页后，无修改可零PATCH确认；失败/空框不能批准。目录修改用受限编辑接口保存并回读，catalog --plan只确认已审目录与本批范围，不提交课堂；有重复卷先处理审查边界。已审作答结构可定点修复，保留教师原判。checkpoint是有限恢复记录，不是服务端exactly-once；超时或部分失败先回读，不重放整包。

仅选择整理时，供应商批改完成后接统一organizer；LLM按答案卷与该模式实际整理入口推进，不强套scan参考卷。WorkBuddy有官方ZIP导入路径；豆包办公、千问办公未核实完整包导入/执行契约，Qwen Code不代表千问办公能力，均按当次工具实际接入。

## 验证边界

v1.10.0 本轮通过 150 项隔离回归：92 项原有 JS 状态/业务行为（64+28）、41 项 Python 入口/适配验证、17 项 Node 会话验证，全部通过、无跳过。新增 5 项 Python 验证覆盖独立会话优先级、失效不回退/重放、无批次的会话命令、缺运行时及不确定执行；17 项 Node 验证包含真实双 Chromium 与自建第三个 Chromium，核对源页 URL、未保存输入和全部 Cookie 不变，目标新建应用会话与双层登录校验、复用、身份变化阻断写入/续接、原身份恢复、HTTP 200 内业务 428、CLI 自动路由、文件分块上传、仅目标退出、来源/目标别名识别及自建临时 profile 清理。认证 API 和 PDF 均为本地合成数据，无线上模型调用；真实站认证迁移另列下方，隔离回归不代表课堂导入验收。

2026-11-04 另在 `https://piyue.yungu.org` 完成正式教师账号的真实认证迁移验收：在本次新建来源 Chromium 正常 CAS 登录，未使用身份 Mock；session-connect 将必要登录态在内存中交给另一独立内部 Chromium 的新无痕上下文，返回 isolated_session_connected、classroom_verified=true；主 Python CLI 默认后端取得 access_verified、classroom_valid=true，session-status 为 isolated_session_ready、connected=true。session-close 后，来源浏览器再次读取 session 和 login-check 均有效且仍为教师。凭证未写文件或输出；未上传真实试卷、未启动扫描/批改模型、未提交课堂同步。两个浏览器均在本云主机，该结果不证明教师个人电脑、跨设备/IP 或 WorkBuddy、豆包、千问的工具权限已可用。

历史 v1.9.0 通过 128 项隔离验证：92 项 JS 状态/业务行为、36 项 Python 入口与适配验证。其中新增的 19 项 Python 验证覆盖每日缓存、跨日和手动 force、实际升级、保留 checkpoint 与其他技能、本地修改与新增目标文件冲突、失败缓存、不降级、旧版无 manifest、文件和路径校验、失败回滚、官方删除文件、符号链接、开发 checkout、并发锁与禁用；另验证真实 CLI 入口的自动检查、更新后重启、失败保留旧版继续以及离线命令不联网。本版独立会话结果以上述 150 项回归为准。

2026-11-04 已核对线上 healthz 的 X-Release-Integrity 与保留发布 manifest 一致，认证、应用保护、课堂会话核验、学校授权及名单路由源码哈希均匹配该 manifest。批阅台 paper_session 由服务端校验教师身份、有效期和撤销状态，上游 SESSION 还须核对同一用户与学校；批次访问按学校授权，并非仅限创建者本人，因此智能体仍必须限定老师本次材料。课堂同步继续受真实最新预检、版本、教师确认及本次同步选择约束，隔离登录不会增加业务授权。

历史验证还覆盖教师路径选择与“批完停止”编排、done 但缺结果保留 grading_incomplete、uncertain/unknown 保留、终点持久化和变更，以及目录、受限接口、版本保护、专用同步边界、真实 HTTP multipart 上传、CLI emit/collect、引擎缓存、离线 PDF 校对和错 SHA 拒绝。

历史真实 HTTP 验证使用同一份 2 页合成 PDF 重复接续，仅创建一次文件 POST 和一次班级 PUT，复用原 batch 并核对原字节、幂等与分卷边界。引擎缓存用于同页面复用代码、小步骤推进；历史 v1.8.0 的 classes 样例曾测得 707 字节小步骤与 80974 字节引擎，仅是旧版本脚本文本证据，不代表本版大小、token 用量或线上耗时。上述隔离验证使用合成服务，不调用线上模型，不证明真实 CAS 登录、识别质量、视觉审核或线上性能。

尚未完成WorkBuddy、豆包办公、千问办公实机实卷验收，未验证课堂实际导入及学生订正；技能更新不包含修改或部署应用前后端。历史真实批次结果不能代替本版办公产品或端到端速度证据，不承诺5分钟或固定token节省。结构统计一致不等于全部判断准确。

仓库不包含账号凭证、试卷或学生数据。
