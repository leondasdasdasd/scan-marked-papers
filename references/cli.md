# 批量 CLI 编排

本说明对应主入口 `scripts/paperflow.py` 与 `paperflow.js`；`paperflow_base.py`仅为旧兼容入口。三种业务流程——已批扫描、供应商快速批改、答案卷智能批改——直接用专用CLI/run；参数查当前子命令help，本参考只读当前入口或阶段，未覆盖才查api-list及对应契约，不预读API全文或适配器源码。只有接口不支持/不兼容或工具缺能力的具体证据，才定点回退页面。先按SKILL.md让老师选定处理模式、批改后是否整理及是否同步。只批改用run --stop-after grading，整理路径用run --stop-after check；同步在检查后另走明确授权的sync。已有导入与停止标记优先只读。办公接入边界见 [office-agents.md](office-agents.md)。

## 每天首次使用与版本重载

先执行`python3 <本技能目录>/scripts/skill_update.py ensure`，按本机自然日每天首次检查GitHub；同日已有记录只读缓存，不重复联网。官方版本更高会自动校验、备份并更新本技能，之后重新读实际SKILL.md；正常安装目录中的CLI业务入口也会兜底ensure，成功更新后重载代码。固定来源、manifest校验、本地修改保护及失败回滚见 [更新说明](skill-update.md)。

只问版本用`skill_update.py status`，离线返回本地版本与最近记录；必要的只读远端核对不调用ensure。用户明确手动刷新才`ensure --force`，仍不强覆本地改动。网络失败记录当日失败，次日再试；不能把失败缓存当最新。开发Git checkout、离线help/api-list/collect及带metadata的离线review不触发自动更新。用户明确关闭时由智能体设置PAPERFLOW_AUTO_UPDATE=0（false/off同样有效），CLI与ensure --force均遵从；用户未要求恢复前不重新启用。没有命令/Python/可靠安装工具就报告能力缺口，不声称已自动更新；无人使用时不会后台检查。

## 首次材料与能力预检

```bash
python3 <技能目录>/scripts/paperflow.py prepare --file <本轮PDF> --pages-per-paper <已核实每份页数> --read-timeout 10
```

`prepare` 仅在本轮首次接到新文件、需要核实文件或本地执行能力时运行一次，复用结果，不作为每条命令前的重复步骤。`--pages-per-paper` 可省略；未核实分卷边界不能靠工具默认值猜测。它离线运行，无需 batch 或 browser-session，不联网更新、不安装依赖。

文件有界读取并给出 SHA-256、字节数、PDF 头、真实页数、page_geometry（width_points/height_points、按3pt容差确定的A3/A4或null、orientation及pages）及耗时，有每份页数时给paper_count和分卷校验。`prepare` 与 `upload` 使用同一 PDF 预检：当前 Python 缺 pymupdf 时，在原 read-timeout 剩余预算内按下文审图环境发现范围尝试已有解释器，不安装依赖；没有可用解析器返回 `pdf_parser_unavailable`，不将页数未知当作预检成功。无论是否传 pages-per-paper，真实总页数都须为1–600，越界返回 `invalid_pdf_page_count`；需要密码的加密 PDF 返回 `pdf_password_required`，不索要或保存密码、不自动解密。保留 PDF 头、哈希、分卷及100MiB上限校验。

复用已核结果，不因另一个解释器缺模块重复换读法或安装；物理尺寸不等于分卷、页序或双面已审。默认读取上限 10 秒，`pdf_read_timeout` 的下一步是 `use_existing_file_tool_or_accessible_copy`，不推断 TCC 或其他权限根因。停止重复 ls/hash/换读法，回收本轮自建挂起只读任务；由现有已授权文件工具提供可读副本后只验证一次，已有可信源哈希时核对一致，不让老师排查技术参数。不能读取则保留具体阻塞，不把“文件存在”当成可上传。

本地能力摘要只反映 wrapper、agent-browser、Node 等是否存在；指定 `--playwright-cli` 时新增 `playwright_cli_file_exists`，不自动扫描缓存。返回 `browser_authentication_verified:false`；存在不证明命令契约兼容、浏览器连通或已登录。现有 evaluate 必须在产品实际授权页面验证，随后仍用 `access` 核实身份。文件检查与不依赖文件的会话核实可并行。

## 教师选择与阶段终点

老师选择只批改时，`run --stop-after grading`仅推进原始批改，核对全批done、缺失/失败状态与基础结果计数；grading_completed要求本批非空、卷ID无重复、全批done，且每份有results、judgments或provider_results结果证据；done但缺结果仍是grading_incomplete，不自动重批done。基础verdict计数保留uncertain/unknown，不视为全部判断准确；organization_started=false只说明本次命令没有启动整理，不能据此声称服务端以前没有整理。该终点不读取analysis、不生成题框/目录、不准备媒体或preflight。整理路径用`run --stop-after check`；扫描本身包含整理，不能指定grading终点。同步选择先完成check，再按专用sync提交，不让run直接提交课堂。

stop_after在派发前写入本次checkpoint，后续省略--stop-after时沿用；老师明确变更终点时显式传新--stop-after覆盖原目标；旧checkpoint没有该字段时CLI兼容默认check，这只是工具兼容行为，不能替代老师选择，智能体须先补清缺少的业务终点。老师已在当前会话为同一材料明确选择时不再问；跨材料不能照搬。选项未明确时只做只读检查，不以CLI默认值启动写任务。

## 入口与输出

参数由智能体从当前环境获取，不交给老师配置。Python全局参数放在子命令前；zsh复用命令用函数或数组（如 `pf=(python3 <入口> <全局参数>); "${pf[@]}" access`），不把整条命令存字符串 `$PF` 执行；已有链接优先 `--batch-url <记录链接>`，从经核实的http(s)业务路由提取origin/batch id。也可用 `--base-url <origin> --batch-id <ID>`；缺 batch 时从 `--checkpoint` 的同 origin 已绑定 batch_id 恢复，错 origin 拒绝。base-url默认 `https://piyue.yungu.org`，显式参数与链接冲突会拒绝。access/relogin/classes/api-list/api-call/upload及session-connect/status/close可在没有batch时使用，其他命令按实际要求定位本批。默认地址不证明生产；授权浏览器必须同源，不跟随意外重定向。

按现有能力选一路，不擅装工具：

| 路径 | 适用条件与边界 |
| --- | --- |
| `--browser-backend isolated` | 先由下文 `session-connect` 建立同 origin、同 `--browser-session` 的独立会话；后续显式限定只用该会话，没有缓存就返回 missing，不回退老师的页面 |
| `--browser-backend playwright` | 已有真实任务会话。现成 JS 入口用全局 `--playwright-cli <绝对路径>` 内部 Node 直调，优先于 `--wrapper`，不需手写 shim；否则 wrapper 默认 `~/.codex/skills/playwright/scripts/playwright_cli.sh`，可指向现有兼容入口。明确失败不反复调用，不是办公产品安装前提 |
| `--browser-backend agent-browser` | 已有可执行文件支持 `--session <会话> --json eval --stdin`，返回 `success:true`、data.result 为含布尔 ok 的对象。`--browser-executable` 默认 agent-browser；实际 session 须已连接授权页面，仅能点击/截图不证明兼容 |
| `--emit-script <PATH>` + 现有浏览器 evaluate | 不要求browser-session或兼容CLI后端。只生成一次加载的engine_file与小步骤script_file，返回executed=false。首次/导航后先evaluate引擎，再执行小步骤并collect；后续只执行小步骤，不重新拼fetch或逐轮展开完整引擎 |
| 原生页面 | 仅登录、确需文件注入/图证，或已有具体接口/工具缺口时使用；缺能力如实保留阻塞 |

`--playwright-cli` 仅作用于 playwright 后端，检查已有 Node 与入口文件；缺失返回 `existing_playwright_cli_unavailable`，不静默回退 wrapper/npx，不下载依赖。它不证明命令契约、浏览器连通或认证已验证。示例：

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --browser-session <本轮任务名> --playwright-cli <现有playwright-cli.js绝对路径> access
```

同 origin、同 browser-session 已有独立会话缓存时，正常浏览器 CLI 优先使用它，包括默认 playwright 或显式 agent-browser，不再操作老师的页面；隔离会话失效会返回诊断，不静默改用用户页。emit 是独立的脚本生成路径，仍交给实际授权的同源 evaluate 宿主，不自动执行或完成迁移。带 `--metadata` 的 `review` 离线渲染与 `collect` 不要求 browser-session，`review`/`collect` 均不支持 emit。不带 metadata 的 review 仍从浏览器读取 snapshot，需要真实会话。主入口和兼容 `paperflow_base.py` 的正常浏览器后端均支持 isolated/playwright/agent-browser；session-*、batch-url、emit、collect 等命令以主入口 `paperflow.py` 为准。

### 独立会话的确定性接入

已有本轮可用后端与任务会话就直接 access；尚未确定路径时才尝试一次连接，不扫描或测试全部后端。任务会话名由智能体选取（1–80 个字母、数字、下划线或连字符），沿用已核实 origin，不让老师填写技术参数。

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --browser-session <本次任务名> session-connect
```

已有独立会话会先核验并返回 `isolated_session_reused`；否则只读查找本机已知浏览器的 `DevToolsActivePort` 和已开放的 9222/9223 CDP 入口。多个来源不猜测，按已有工具证据指定来源；未开放 CDP 不会自动开启。仅在工具已提供真实定位时使用以下可选参数：

- `--source-url <现成已授权CDP入口>`：也可由运行时 `PAPERFLOW_SOURCE_CDP_URL` 提供。
- `--source-target <真实target ID>`：限定来源页面/上下文，不导航或点击该页。
- `--target-url <独立内部CDP入口>`：使用已有独立浏览器并新建隔离上下文；目标不能是来源浏览器。不传时只启动本机已有浏览器的独立进程。
- `--executable <已有浏览器绝对路径>`：仅指定本机已有 Chrome、Edge 或 Chromium，不下载安装。

来源和目标 CDP 的明文 HTTP/WS 仅接受 loopback；远端入口必须是显式 HTTPS/WSS，不把明文远端调试口作为可用接入。入口仍由智能体从现有授权工具获取，不让老师配置端口。

当前实现要求已有 Python、带内置 WebSocket 的 Node，以及可复用的浏览器；只支持 `https://piyue.yungu.org`、HTTPS 的 `*.app.yungu.org` 和 loopback origin。已有 evaluate、点击或截图能力不证明能读 HttpOnly Cookie，`document.cookie` 不能完成迁移。缺来源能力时不重复试探、不读取或解密浏览器 Cookie 数据库、不重启用户 Chrome 开调试、不安装插件或运行时。没有既有独立记录时，`source_browser_access_unavailable` 只说明既有登录态迁移不可用，可按诊断使用既有授权的 playwright/agent-browser/evaluate 接口，必要时在现有任务浏览器正常登录后用 access 核实；不把无 CDP 当作正常登录不可用，不要求老师开放调试或提供端口；已有记录但失效时先保留恢复点，session-connect 仅尝试从原授权来源续接同一教师与学校，无能力或账号变更就停写。确需改用其他现有授权后端/evaluate，先 session-close 清理本任务失效记录，再重新核验实际会话，不能带旧控制记录强行回退。回退执行不等于已建立独立会话，也不保证所有办公产品都能静默接入。

连接脚本只读取适用于目标 origin 的必要登录 Cookie，在受控进程内存中核实来源教师与学校；目标使用新隔离上下文，仅把 `SESSION` 缩为目标 host，建立新的 `paper_session`，不复制源 `paper_session`。只有目标教师、学校和身份与来源一致，且真实 `/api/classroom/login-check` 有效，才返回 `isolated_session_connected`。上游 SESSION 仍受实际有效期和撤销规则约束，独立上下文不延长登录授权。这只是登录核验，不扩展课程、班级、批次或同步授权；实际请求仍受服务端权限、学校范围和业务版本校验。

Cookie、令牌、授权链接不进入模型、聊天、stdout/stderr、计划、checkpoint 或导出文件，也不生成 storage state。受限控制记录保存在系统用户缓存目录的 `scan-marked-papers-sessions` 下，按 origin 和任务会话名定位，仅含身份与独立浏览器控制信息；目录 0700、记录 0600，不放进项目、技能包或交付材料。后续命令沿用同一任务名，使用 `session-status` 检查 `connected=true`；仍需 `access` 核实本次实际业务会话。

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --browser-session <本次任务名> session-status
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --browser-session <本次任务名> session-close
```

任务结束执行 `session-close`：仅退出目标应用会话，不跟随 SSO 全局 logout_url，销毁本次隔离上下文；脚本自建的浏览器与临时目录一并清理，已有目标浏览器仅清理本次上下文。源浏览器、源登录态和其他页面保持原状。`isolated_cleanup_incomplete` 表示清理尚未完成，保留控制记录，用原任务名再次 session-close，不手删记录或关闭源浏览器来消除错误。处理中需要续做时保留独立会话和原 checkpoint；身份或学校变化停止写入。

可选全局参数：`--timeout`（1–180 秒，默认 45）、`--interval`（2–30 秒，默认 5）、`--checkpoint <本地JSON>`、`--output <完整结果JSON>`、`--verbose`。独立会话连接成功后，沿用同一任务名；以下由智能体替换为实际值：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> --browser-backend isolated --browser-session <本次任务名> --checkpoint <受控目录/cp.json> --output <受控目录/result.json> run --follow --max-seconds 600
```

没有兼容 CLI 后端但现有工具可 evaluate 时：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> --checkpoint <受控目录/cp.json> --emit-script <受控目录/step.js> run
```

生成结果包含engine_file、engine_id与script_file。首次或页面导航后，先将engine_file交给同源授权浏览器evaluate，取得engine_loaded，再执行script_file；同页面、同engine_id的后续步骤只读/执行小步骤文件，不反复读取或向模型展开完整引擎。engine_not_loaded/next_action=evaluate_bootstrap_file表示尚未加载，未请求业务接口，补加载后继续原小步骤，不重建任务。引擎仅驻浏览器内存，不保存凭证；导航/重新登录后须重新加载。

现有 evaluate 宿主只能同步返回、不等待 Promise 时，与 `--emit-script` 同时使用全局 `--sync-evaluate`：

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --emit-script <受控目录/step.js> --sync-evaluate access
```

生成回执含 `script_file`、`poll_file`、`job_id` 与 `evaluate_mode:synchronous_dispatch`。按前述方式先加载引擎，再执行启动脚本；`browser_step_started` 只表示已启动，执行 `poll_file` 得到 `browser_step_running` 时沿原有界预算等待，完成后 poll 直接返回业务原始 envelope，交给 collect。复用生成文件，不手写全局变量包装或重建轮询脚本。

同一页面、同一 script/job 重复启动不重新派业务；仅 `engine_not_loaded` 明确保证尚未发业务请求，可补加载引擎后用原 script 重试。导航丢失 job 返回 `browser_step_missing` / `read_state_before_retry`，先读服务端当前状态，不盲重发。该页内保护不替代 checkpoint、服务端幂等或写入后回读，不是 exactly-once。

执行小步骤后，取evaluate **业务表达式返回的完整JSON envelope** 原样保存到受控browser-result.json；engine_loaded只是加载回执，工具外层包装、截图或compact摘要均不能当业务结果。再离线回收：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> --checkpoint <受控目录/cp.json> --output <受控目录/result.json> collect --result <受控目录/browser-result.json>
```

collect不访问浏览器、不重新执行或再次验证业务，校验布尔ok及checkpoint.origin/batch_id一致后回存checkpoint、完整output并输出compact。保留完整结果中的checkpoint，下一轮生成小步骤复用；正常CLI后端直接运行，不需手动引擎加载。只有现有执行器确需旧兼容形式时加全局`--standalone-script`，生成自包含步骤；这不改变权限或预算。

emit即使带--follow也只运行一轮timeout预算，不持续后台跟进；waiting先collect再生成下一轮，不重复启动。各轮沿用该阶段本轮墙钟累计预算（默认600秒，可按用户明确需要调整），不每轮重置；这不是CLI emit已实现的全局预算。正常running且进度暂不变本身不是失败证据，沿预算等待，只有明确重复错误或不可恢复诊断才提前停止。到限交付“处理中/检查未完成”、进度、链接与原checkpoint，下次续原batch，不无限轮询、重传或假报ready，不按固定轮数判失败。

正常 `run --follow` 跨 waiting 续接时，若上轮已明确分析活跃，内部观察保留 imports/task control 检查，稳定阶段省去重复 batch/catalog 读取；阶段变化后再次检查 control 并作权威读取才继续。此优化不新增 CLI 开关，不改变写前保护或 emit 跨轮管理。状态与进度相同时，等待间隔以1.5倍退避，上限为 `min(3*interval,15秒)`；进度变化回到 interval，睡眠不越过单轮 deadline。分析与媒体共享执行 deadline；Python follow 每轮 timeout 仅取剩余 max-seconds。业务 HTTP 在途仍可能使实际墙钟超过预算，这些预算不是硬超时或服务端完成承诺，减少轮询也不证明真实处理更快。

emit 结果已 collect 且有本地原 PDF 时，可直接复用元数据生成校对包，无须再读浏览器：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> review --metadata <受控目录/result.json> --pdf <本次原PDF> --out <受控目录/review>
```

metadata 接受裸 snapshot、包含 result 的完整 envelope，或 run 的 result.review；必须匹配本次 batch_id，并严格核验原 PDF SHA。校对包输出原页、按参考相对页分组且每张最多6框/限高分页的带上下文逐框联系图，以及frame-index.json；索引绑定source_pdf_sha256与frame_revision，用于定位原页、题框和联系图。所有生成结果始终reviewed=false，不自动认定QA通过，也不继承其他智能体已审。review_dependency_unavailable表示当前执行环境无可用渲染依赖，复用已验证的现成Python或同SHA/frame_revision的现成图包，不自动安装；不能仅凭local_execution_failed错误名推断缺依赖或权限。当前智能体实际核对原页和逐框联系图；来源、题框版本及 frames 均未变时复用本轮已生成图证，不继承其他智能体的审图结论；仅具体未决异常补定位图，一次汇总修改后核验受影响框及全页覆盖，无新异常不重复渲染、放大或裁剪。

当前 Python 缺少 pymupdf/Pillow 时，审图执行按顺序尝试已有可执行的 `PAPERFLOW_PYTHON`、`VIRTUAL_ENV/bin/python`、任务 cwd 及其祖先目录中的 `.venv/bin/python` 或 `venv/bin/python`，本地 worker 上限120秒；不扫描全机、不安装依赖。单个解释器缺依赖不代表任务已有环境均不可用；这些路径均不可用时才按真实诊断保留缺口，不重复换读法。

同一输出目录的图包缓存绑定 batch、原 PDF SHA、frame_revision、参考卷及其起始页、每份页数、frames 和渲染器版本。`review.json` 的 `render_key` 相同且图像及 index 文件的 `file_sha256` 全部校验通过时，返回 `cache_hit=true`、`decoded_pages=0`。题框或 revision 变化须重建叠框图；仅原 PDF、参考卷、页范围一致且原页文件哈希完好时复用原页解码，回执以 `raw_pages_reused` 表示。文件损坏则重建，不沿用旧图包。缓存与新生成产物均为 `reviewed=false`，不继承其他智能体的审图结论；当前智能体仍须实际核对原页、逐框联系图和全参考页覆盖。

输入计划、全局 output、snapshot 输出和 checkpoint 使用不同文件路径；emit 派生的 engine/poll、review 的全部图像/index/JSON资产及 JSON 临时兄弟文件也不得覆盖本次 PDF、metadata、checkpoint、output 等输入输出。相同路径、相对/绝对等价路径及软硬链接碰撞返回 `file_path_conflict`；emit 在 checkpoint 写入前校验，冲突时不向冲突 output 写错误回执。合法的同图包缓存复用仍可使用，不为避冲突删除原件。

备用 Python 审图保留 `source_pdf_hash_mismatch`、`reference_page_out_of_range`、`invalid_review_bbox`、`file_path_conflict` 的具体诊断，其余渲染失败概括为 `review_render_failed`；按实际错误处理，不将所有失败推断为依赖缺失。

默认stdout为紧凑JSON，保留下一步摘要与路径，省去完整checkpoint、调用明细和大块几何；api-call的大data/readback也输出程序摘要，目录、sync-options、links、correction-item保留必要正文。全局`--output`保存去除token等认证字段后的完整业务envelope，按问题定点读取，不反复整份展开；只有诊断需要才--verbose。`snapshot --output <JSON>`位于子命令后，保存裸snapshot，与全局output不同；snapshot包含read_version，可作为review写计划expected.read_version，不能拼造版本。timeout为单轮预算，正常run --follow --max-seconds为跨waiting的有界预算，都不是服务端完成承诺。

`ok`/退出码只说明工具执行，业务完成看outcome、completion、remaining、顶层ready/submitted与真实全批覆盖，不只取原始preflight.ready。upload经FormData创建，scan/grading均由run按已选终点推进；只批改看grading_completed/grading_incomplete与原始全批覆盖，不要求ready；原生文件工具只向接口环境注入PDF，不默认点击上传表单。旧兼容入口的能力以自身help为准，不据此限制主入口的新命令。

| 命令 | 用途与边界 |
| --- | --- |
| `prepare --file <PDF> [--pages-per-paper N] [--read-timeout 10]` | 首次材料有界读取与本地能力摘要；离线、无 batch/会话，不认证浏览器，不重复运行 |
| `session-connect [--source-url <CDP入口>] [--source-target <ID>] [--target-url <独立CDP入口>] [--executable <已有浏览器路径>]` | 复用已核验独立会话，或定点内存迁移必要登录态；不操作源页面、不导出凭证；需全局 browser-session，无需 batch |
| `session-status` | 核验本次独立上下文、同一身份及课堂会话，读 connected/outcome；不以 ok=true 代替 connected=true |
| `session-close` | 仅注销目标应用会话并清理本次上下文/自建浏览器，不跟随全局退出、不关闭源浏览器 |
| `access` | 只读当前批阅台身份及课堂会话，不调用模型能力；返回 principal、classroom_valid 与访问诊断，将非敏感身份回执保存到 checkpoint，身份/学校变化时停写；支持 emit |
| `relogin` | 命令执行时启动平台既有强制登录导航，授权链接仅在浏览器内存中使用；emit 仅生成，evaluate 执行后才导航。导航已启动不等于恢复成功，之后须回原 origin 用 access 核验 |
| `roster` | 一次读批次与名单，输出 revision、papers、linked/unlinked 及未关联卷的份号/PDF页码/姓名状态/原图定位；同名候选仅来自已有识别名，不提供剩余名单猜人；支持 emit |
| `classes --source teaching或general [--grade <值> --subject-id <ID> --course-id <ID>]` | 读取当前允许教学/通用目录，按真实年级、学科、课程逐级选；不保存范围 |
| `class-students --class-id <ID> [同scope查询参数]` | 只读预览当前目录允许班级的真实名单，不关联学生 |
| `scope --plan <JSON>` | 计划含当前roster revision、真实semester_id/class_ids/scope与证据，保存本批范围；不能录入后擅换班 |
| `upload --file <PDF> --pages-per-paper <N> --key <固定键> --workflow scan或grading --engine llm或xueersi或doubao [其他模式/纸张参数]` | 同源FormData接口上传；三种业务模式，固定幂等键、超时查原上传；原生工具仅注入文件，不导出认证材料 |
| `api-list [--operation <名称>]` | 离线列出受限registry的功能、路径、查询及必要字段，不访问业务服务 |
| `api-call --operation <名称> [--plan <JSON>]` | 按已登记操作定点读写；GET不要求证据，写入要求真实证据/当前版本；禁止任意URL，special操作走专用命令 |
| `sync --plan <JSON> --authorize-sync` | 仅用户本次已明确同步时提交或恢复原导入；开关不增加用户授权，默认检查命令绝不提交 |
| `run [--stop-after grading或check] [--reference-paper <已审卷ID>] [--plan <JSON文件>] [--review-pdf <PDF> --review-out <DIR>] [--follow --max-seconds 600]` | 按老师选择的终点和真实阶段推进；waiting 可有界等待，审图、目录校对、失败或终点返回。成对 review 参数复用当前读取生成校对包 |
| `snapshot [--output <裸snapshot JSON>]` | 读批次/catalog，给源PDF SHA、read_version等版本、完整框与精简目录（正文、稳定选项ID、blank_ids、answers/extras）；reviewed=false不证明看过图 |
| `review [--metadata <JSON>] --pdf <原PDF> --out <受控目录>` | 带 metadata 则复用已保存元数据离线渲染，不访问浏览器、不需会话；省略则从浏览器取 snapshot。核验 batch_id 和 PDF SHA，生成原页、按参考页每张最多6框/限高的上下文联系图、frame-index.json与review.json，需 pymupdf/Pillow；绑定来源与题框版本，始终reviewed=false |
| `frames --edits <JSON> [--confirm]` | 本地整包校验 set/shift/split/promote_children，最多一次 PATCH，再按需确认；预切正常、题框非空且实际已审无修改时可 operations=[]，零 PATCH；失败/空框不能批准。保存与确认不是跨请求事务 |
| `catalog --plan <JSON>` | 确认已审目录及本批处理范围，回读真实完整 questions，agent 不必复制富题对象；不修改目录，不提交课堂。run 根 plan.catalog 同效 |
| `associate --plan <JSON>` | 整批证据/版本校验后顺序关联、采用新 roster revision，末尾回读；最多50项，可能部分保存，不是原子事务 |
| `inspect` | 全批人数、叶题、作答、重复遗漏与未关联聚合；不是视觉验收 |
| `check` | 全批检查并给 completion/remaining，不改配置或缩范围；只在媒体 pending、无 blocker/failure、结构/覆盖完整且全关联时可能 start，活跃准备任务复用等待；未关联时同时保留身份与媒体等剩余项 |
| `diagnose` | 读真实 preflight 与阻塞，不启动媒体；诊断成功不代表 ready |
| `retry-precut --page <0-based相对页> --frame-revision <当前值>` | 从返回 retryable_pages 取证后只重试具体页，不自动全页重试 |
| `evidence --paper-id <ID> [--question-id <QID> ...]` | 定点版本、PDF页码、目录与作答证据；不输出 review_token，reviewed=false |
| `responses --plan <JSON>` | 实际审卷后定点修复作答结构，仅 response_only、不改教师判定、不调模型；顺序保存，失败即停，可能部分保存 |
| `usage` | 缺失 usage 保持 null、tokens_complete=false，不以零补齐 |
| `collect --result <完整浏览器业务JSON>` | 离线校验并回存 emit 执行结果，不执行浏览器或改变业务 |

## 目录、上传与文件注入

先 access；课堂会话失效先完成一次 relogin 恢复并重新 access 验证，再用 classes 读取本次真实目录。复用已返回且符合本次选择的 source/course/semester 等精确参数，不重做无过滤查询、不猜 ID；teaching使用教学课程，general按grade、subject-id、course-id逐级读取。class-students使用同一组scope参数核对允许班级名单。多候选需用户决定时集中问业务选择，不让老师填写ID或工具参数。

scope计划与run.scope结构相同：当前revision、semester_id、class_ids、scope对象及evidence_confirmed/evidence_note。scope.source为teaching或general；general还须真实grade/subject_id/course_id。现有批次先读roster取revision；新上传可给`--scope-plan <JSON>`，工具在创建或恢复原batch后读取它的当前revision再绑定，不把旧batch版本套到新记录。保存后回读名单与范围，录入后不擅换班。

upload复用与 prepare 相同的有界文件读取，默认 10 秒；此前预检通过不保证后续文件仍可读，超时按具体诊断恢复，不改键重传。upload必须提供全局`--checkpoint <受控JSON>`、本地PDF、每份页数和固定key；key为8–100位字母/数字/下划线/连字符。模式参数如下，不省略真实业务选择：

| 业务模式 | upload参数 |
| --- | --- |
| 已批教师卷扫描 | `--workflow scan --engine llm`，不加has-answer-paper；默认scan_fast，只有本次既定设置需要才用`--full-scan` |
| 供应商快速批改 | `--workflow grading --engine xueersi`或doubao；仅用户明确第一份答案卷时加`--has-answer-paper`；`--analysis-fast`仅保留该模式既有整理设置 |
| 答案卷智能批改 | `--workflow grading --engine llm --has-answer-paper --model <当前允许模型>`；第一整份为等长答案卷，至少再有一份学生卷 |

纸张参数为`--paper-size A4或A3 --orientation portrait或landscape --paper-sides single或double`。每份1–12页，double须偶数，文件不超过100MB/600页，总页数可整除，不静默删页、补页或换模式。模型与供应商能力只在对应阶段核实。

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --browser-backend isolated --browser-session <本次任务名> --checkpoint <受控目录/upload.json> --output <受控目录/upload-result.json> upload --file <原PDF> --pages-per-paper <真实页数> --key <本次固定键> --workflow scan --engine llm --scope-plan <受控目录/scope.json>
```

上传经当前授权浏览器的 FormData 接口执行，不导出认证材料，不让模型读取或手工拼接 PDF 的 base64。脚本自建的本机独立浏览器用原生 setFileInputFiles；通过 target-url 使用的已有独立浏览器，由 CLI 内部以受控分块传输文件字节，在目标浏览器构造 File、绑定输入后提交 FormData，原文件内容及内部编码不进入提示词、计划或输出。playwright wrapper 默认只为本次创建隐藏 `#paperflow-upload`，用原生 setInputFiles 注入并清理；已有实际 input 可用 `--file-input-selector <已核实选择器>`。其他现有工具只负责原生文件注入，再执行生成的接口脚本，不默认导航或点击上传表单。

emit路径仍加`--emit-script <JS>`，支持三种模式；生成不上传。执行时输入控件未绑定文件返回needs_file_binding，先用该产品已有原生文件工具绑定同一PDF，再执行/collect，不手写文件请求。先查`GET /api/uploads/{key}`，已completed恢复原batch；deleted不自动重建。超时或scope失败保留upload_receipt，继续同key查原状态；upload_uncertain先查状态，不换key或盲重传。uploaded仅表示创建/恢复与必要scope绑定，不等于批改、检查或同步完成。

## 受限接口调用

api-list离线列出83项操作的purpose、method/path、允许query、required、transport和模式限制；按操作名查 [API参考](api.md)，不为正常使用读内部源码。api-call仅按registry生成同源路由，params只填路径中除bid外的真实参数；B路由的bid取当前batch。GET计划可为`{params:{...},query:{...}}`，无需证据；不需要参数时可省略plan。artifact返回artifact_location、真实url、downloaded=false，只给位置，仍需实际读取必要图证。

写计划增加body（仅JSON传输）、`evidence_confirmed:true`和非空evidence_note；transport=empty的操作完全不传body，不用`{}`替代。review类写入还须`expected.read_version`与当前full analysis的read_version一致，工具才运行时注入review_token；task-stop须body.kind和`expected.started_at`匹配当前任务再运行时取控制token。其他操作按真实revision/source_version等字段核对。任何token都禁止人工填入计划或输出。

GET返回api_result/data；成功写入返回api_saved/data，PATCH/PUT另附权威readback。stdout大结果为摘要，核实具体持久化字段时从全局--output的完整去凭证结果读取，不能把摘要缺字段误判为服务端未返回。HTTP200不代表后续任务或全批业务完成。upload、目录确认及imports属于special操作，普通api-call返回dedicated_command_required，分别用upload/catalog/sync，不改registry或手写请求绕过。只有用户本次明确接续时才在适用启动/恢复计划写resume_authorized=true；只读请求不恢复停止任务。

## grading编排与明确同步

run先读live-state/task-control；活跃原始批改返回waiting_for=grading，正在停止返回task_stop或grading_stop，按既定预算等待持久化完成，不抢启新任务。已停止/暂停仅本次明确要求接续时在run计划根给`resume_authorized:true`；该标记体现已有授权，不向老师新增审批。供应商批改done后沿用统一organizer的参考卷、题框、目录边界；LLM用prepare-analysis，不要求选择参考卷或传reference_student_id。

needs_grading_recovery按failed定位缺失/失败卷；`grading_retry:{paper_ids:[本次真实卷ID],evidence_confirmed:true,evidence_note:必要诊断}`只派未done范围，保留人工结果，不把整理重试当原始批改重试。已有done不默认重批；用户本次另有明确重批要求时才按受限grading-retry契约处理保护，不清人工标记绕过。

sync必须同时有本次明确同步授权、`--authorize-sync`和真实计划：revision、source_version、evidence_confirmed/evidence_note、reference_reviewed/scope_reviewed/catalog_reviewed均true、accepted_warning_ids为经审查的最新真实warning集合。这些审查标记只在实际完成对应核验后填写；LLM的reference_reviewed对应实际标准题/答案卷来源核验，不虚构参考学生卷。工具运行时重做全批check和preflight，精确核对配置/来源/warnings后提交，检查token只留内存。

已有attempt默认只读；明确继续原同步时计划给`resume_attempt_id`且必须等于原attempt，不能自动重投。synchronization_accepted或synchronization_resumed只表示已受理/已恢复；用imports/sync-progress有界观察原任务至SUCCEEDED，再用import-links取真实链接。已SUCCEEDED不覆盖。默认run/check及普通api-call绝不提交课堂，不把开关或ready当用户授权。

## 按返回边界推进

先 access 核验身份、学校和课堂会话，再用单个有界 run --follow 跟进并接收结果（emit 单轮执行/collect），同浏览器会话有活跃命令时不并行导航或启动另一条 run；外层读取进程输出不等于业务轮询。复用校对包、计划与已有诊断。等待和序列化交给内置工具，不逐轮 snapshot/roster；失败且能力未变不重复探测或写新恢复计划。仅缺少具体契约时补当前help/api-list与[对应条目](api.md)，可执行阶段继续，真实阻塞保留原checkpoint；只在阶段变化、阻塞或交付时简报。

| 返回边界 | 智能体下一步 |
| --- | --- |
| `needs_reference` | 按真实清晰度、完整性与教师批注实际审阅并选本批参考卷，直接 run --reference-paper <卷ID> --follow；无须单字段plan。若全批已有完整已知verdict，候选按现成正确率排序；否则仍取前几份轻量比较，不增加识别调用。candidates含id/index/pdf_pages/原图URL，correct_rate仅在有真实统计时使用，范围0–1，不把缺失当零或凭空编百分比；候选摘要不是处理范围 |
| `needs_file_binding`、`upload_uncertain` | 前者只补原生文件绑定后执行既有脚本；后者查原key状态并保留upload_receipt，不改文件/参数或盲重传 |
| `needs_grading_recovery`、`needs_analysis_recovery` | 按真实failed/诊断定位原批改或后续整理缺口，分别采用适用的定点恢复计划，不切模式、重跑done或把部分范围当完成 |
| `needs_precut_recovery` | 读 diagnosis 的失败页、issues、revision、retryable_pages；有证据才定点重试，空框候选页不代表已确认失败，不全页空跑。awaiting_frames 下同因重试无效，实际审图后优先用 frames --edits 的 replace_page 保存失败页全部独立题框，CLI保留其他页及ID；跨页题框需显式编辑，不可整页覆盖。回读失败页真实清除、全参考页已审后才正常确认，不伪造审图、不强confirm。仅兼容旧运行时时用 api-call frames-save 按当前 revision 完整保存全套框。无能力或服务端仍拒绝就保留具体恢复点；没有 frames add 操作 |
| `needs_frame_review` | 复用 run 生成的 review 包，实际核对全部参考页，一次整理必要框修改，再应用并确认。没有包且已有本地原 PDF 时才单独 review，已有元数据优先 --metadata 离线复用；已有链接无本地 PDF 时按原技能读取参考页，不索要或重传原卷 |
| `needs_catalog_review` | 一次读取精简目录正文、选项ID与逐空定义，对照已审参考图核对内容、答案和独立题结构；需要修改先集中修改并用 catalog-save-draft/catalog-save-review 保存一次，回读新版本与实际任务状态，历史 ready 作废；实际审完后用catalog --plan确认，再run |
| `needs_targeted_recovery`、partial/failed 或检查阻塞 | 先读具体失败与 review_tasks，以 evidence 取受影响卷/题定位，实际核对必要原卷证据；仅作答结构问题可走 responses，其他按真实恢复接口。不默认重跑全批 |
| `needs_duplicate_review` | 本次范围存在重复学生卷；依据真实证据确定取舍，按当前范围确认契约处理，不自动任选、不提交确认 |
| `identity_pending` | 全批仍有未关联卷；复用 roster 对账定位，清楚身份有证据才整包关联，模糊者直接暂留。保留 remaining 中媒体/结构/范围等其他未完成项，不把 subset ready 或补姓名当作全批通过 |
| `waiting` | 任务仍在进行；`waiting_for=media` 表示媒体准备仍在运行，也可正常 follow。沿用原计划与 checkpoint，或按 emit/evaluate/collect 单轮接续；emit 各轮共用该阶段本轮累计墙钟预算，不重置。正常 running 的进度暂不变仍等待，只有明确重复错误或不可恢复诊断才提前停止；到限时交付处理中/未完成、进度、链接和原 checkpoint，不重复启动任务 |
| `source_stale` | 核实来源变化与版本，重新判断受影响范围，不重批已有人工结果 |
| `existing_import_readonly`、`stopped_readonly` | 只读报告已有同步或停止状态，不恢复会提交的任务 |
| `unsupported_workflow`、`unknown_stage`、`no_progress`、`iteration_limit` | 保留当前状态并按原技能查明或回退；不改 workflow_mode 求通过，不称全批完成 |

完成阶段的 `review_tasks` 按 paper_id/index/pdf_pages 聚合 blocker/failure、相关题目录与 identity_pending，用于一次组织必要证据与修复。没有真正看过图，不能把 `reference_reviewed`、`visual_review_performed` 或客户端回执当视觉完成证明。

## 一次判断、整包应用

**参考与范围。** 选定实际已审阅参考卷后可复用上传checkpoint直接接续；`--reference-paper` 等价于仅含 `reference_student_id` 的计划，不自动填写任何审阅确认标记，与 `--plan` 冲突时拒绝。

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <已核实origin> --checkpoint <本轮上传cp.json> --browser-session <本轮任务名> --playwright-cli <现有JS入口> run --reference-paper <已审阅卷ID> --follow --stop-after check
```

复杂计划仍用 `--plan <JSON文件路径>`，不传 inline JSON；路径不存在返回 `plan_file_not_found`。run 计划根可传 `reference_student_id` 与 `scope`。scope 含实时 revision、semester_id、class_ids、scope 对象、`evidence_confirmed=true` 和非空 evidence_note，仅写已核实的课程/班级与本次授权范围。工具核对当前集合，相同可复用，不同才按当前 roster revision 更新；服务端仍负责权限校验。已有参考不为追求更高正确率重开全批，无证据不造百分比。

**题框。** 计划含 operation_id、当前 frame_revision/source_pdf_sha256/reference_student_id、`reference_reviewed=true`、`scope_reviewed=true`、reviewed_pages（覆盖全部 0-based 参考相对页）、operations，可含 expected_leaf_labels。内部帧 ID 使用 ASCII `[A-Za-z0-9_-]{1,100}`，中文题号放 label；regions 按实际原图给出有限、合法的归一化几何值。第一次保存前集中逐页逐框审清完整题干、全部选项、分数上下界、公共说明、作答空间与批注归属，不以统一 padding 代替边界判断。只有实际审过页和范围才填写确认标记；少量留白或不影响归属的个人框偏移不修。

operations 支持：

- `set`：按 id 改 regions/label；`shift`：用 ids、归一化 dx/dy 移动。
- `split`：原目标无子框时，以至少两个 children（真实 id/label/regions）替换原框，子框 parent_id=null。
- `promote_children`：目标已有直接子框时，显式列全全部直接子框的 id/label/regions；保留子 ID、移除父框，将这些子框提升为独立根题。不能漏列子框，也不支持含孙题的嵌套结构。必须先实际审图，不能仅因已有父子结构自动执行。
- `replace_page`：仅在 awaiting_frames 下，用目标相对页全部经实际审阅的独立题框替换该页现有集合，自动保留其他页及ID；frames须非空，每框的regions只属于该页、parent_id为空，CLI写为独立根题和manual来源。章节、组合题或容器不能充当独立题；原集合含该页跨页框时返回cross_page_frame_requires_explicit_edit，写入前停止，改用显式编辑。复用已核对的真实框，不为调用新操作重新调框。

例如构造operations中的单页补框项；reviewed_page_0_frames来自本批真实框数据与本次审图，不包含推测坐标或审阅标记：

```python
operation = {"type": "replace_page", "page": 0, "frames": reviewed_page_0_frames}
```

将此项放入上述完整计划后执行 `frames --edits <补页计划.json>`；实际审阅已覆盖全部参考页且确认无误时才可加 `--confirm`。保存仍核对当前revision、来源、参考卷及全页审阅契约，操作回执防止重复写入；新框标签进入后续独立业务题粒度核对。成功后简单回读真实框与状态，不重复提交同一几何数据或重新预切。

`frames --confirm` 或 run 计划根的 frames 使用同一计划。run 根还可有 scope、associations、expected_leaf_labels、reference_reviewed。当前部分服务在 frames 确认后以 `catalog_confirmation.kind=confirmed_frames` 自动确认目录并启动全批，不存在可保证的目录先审中间门；去掉 follow 或虚构 stop-after catalog 不能暂停服务端。仅服务端实际返回 awaiting_confirmation 时才走 needs_catalog_review 与 catalog 确认。目录保存可能触发全批重新处理，须读取真实状态并重新全批 check，不沿用历史 ready、不声称仅重算修改题。

**独立计算题。** N个独立算式最终必须是N道可分别查看/订正的业务叶题，不是N框仍一题、N个空或组合题。填写真实expected_leaf_labels，CLI保存并续验粒度目标；核对叶题标签/数量、parent_id=null，排除content.children、composite/virtual_parent、is_composite/isComposite、business_question.isComposite及题型目录isComposite所代表的合题，且无额外父标题题。expected_granularity_verified只是程序核对，不能替代实际目录与必要图证核验。

**关联。** 计划为 `{revision:实时roster版本,assignments:[{paper_id,student_id,evidence_confirmed:true,evidence_note:必要证据摘要}]}`。初次常规查看已有清楚卷面与名单证据的整包应用，脚本中的 true 不是证据。第一次常规查看已模糊或未识别者直接暂留，不放大、新增 OCR、换识别方式或凭剩余名单试探；用户提供新证据或本次明确要求重新识别时，按其范围重新判断，仍不猜人。`roster` 的 exact_name_candidates 只是已有识别名的同名列表，不构成身份确认。继续不依赖该身份的允许步骤，run 在 completed 阶段才应用 associations，其他真实阶段按原技能处理，不能改 scope 求通过。

## 目录确认计划

`catalog --plan` 或 run 根 `catalog` 计划含：operation_id（8–100个字母、数字、下划线或连字符，匹配 `^[A-Za-z0-9_-]{8,100}$`）、当前 source_pdf_sha256/reference_student_id/frame_revision/catalog_revision、`reference_reviewed:true`、`scope_reviewed:true`、`catalog_reviewed:true`、覆盖全部相对页的 reviewed_pages，可含本次 expected_leaf_labels。这些标记只能在实际审图、审范围与审目录后填写，不能作为自动验收证明。

命令回读服务端完整真实questions用于确认；不负责内容编辑。需要修改先用受限catalog-save-draft/review，回读新revision、复核后再给新计划，不能复用旧已审标记。v2仅当前记录source_ids=[]走merge-preflight和confirm-and-start；有重复返回needs_duplicate_review，不确认。旧confirm仅真实版本允许时使用。目录确认不是课堂imports，submitted=false；accepted仍须观察原任务完成。

checkpoint 保留目录确认中/已接受的有限回执。确认超时先只读查原操作与当前目录状态，不循环预检、换 operation_id/幂等键重发；版本/来源变化必须重新判断。未经用户修改却同因409持续发生时按下文有限恢复停止。

## 定点证据与作答结构修复

先用 `review_tasks` 确定卷、题，再调用 `evidence --paper-id <ID> --question-id <QID>`；多个题重复传 question-id，一次取齐。证据包包括 source_pdf_sha256/frame_revision/catalog_revision、paper_id/index/pdf_pages、精简 questions；observations 的真实字段为 question_id、verdict、answer_text、answer_state、response_conversion_status、blanks、response_regions、source_refs，其中 blanks 含 blank_id、answer_text、answer_state、verdict。按定位实际查看必要原卷或已有图证，包本身不证明已审；保留教师原批注与真实不确定状态。

`responses --plan` 根必须含当前 source_pdf_sha256、frame_revision、catalog_revision 和 1–100 个 assignments；每项含 paper_id、question_id、`evidence_confirmed:true`、非空 evidence_note，并按该题真实单一互动元素提供：

- 选择题：`selected_option_positions:[1-based位置]`。例如可见 C 对应位置 3；CLI 根据本次真实目录映射到稳定 option ID。不能把 C 当 ID，也不能凭记忆套旧目录。
- 逐空题：`blanks:[{blank_id,answer_text,answer_state:"answered"或"unanswered"}]`，必须覆盖真实 blank_ids 的全部空位；不能用合并全文或逗号切分猜逐空答案。
- 主观题：`answer_text`，仅填原卷证据支持的实际作答。

该命令仅支持单个互动元素；复杂结构先查question-review/correction-save等已登记接口的真实契约，确无支持才定点回退或报告，不改题型绕过。它先校验整计划的源、版本、题目和证据，再顺序PATCH response_only:true，保持教师判定；review_token仅在内存随响应传递，不写计划或日志。客户端标记不替代真实审卷。

失败后先用 evidence 回读实际已保存范围与当前版本，再拟剩余计划，不能原样重放全包。422 读取 detail 修正真实字段，不反复发送同一无效请求，不直接改库；该命令不提供事务或 exactly-once。修复后重新 run/check，以最新真实全批检查为准。

## 错误诊断与有限恢复

错误返回 status/method/path/message、可用的 server_code、next_action 与 retryable=false。先读原始 detail 和当前状态；retryable=false 表示不要自动重放写请求，不等于永久不可修复。

| 类别 | 下一步 |
| --- | --- |
| `invalid_json_body` | 422 原文“标准卷选择格式无效”；先核对JSON传输/序列化，使用内置脚本，不猜键名。该路由 JSON 解析失败或 body 非对象才触发，ID不存在是另一条错误，不能据此断言平台故障 |
| `validation_failed` | 按真实 detail 修正有证据的格式/字段，不盲试变体 |
| `version_conflict` | 回读当前版本、范围和实际保存内容，再判断剩余动作 |
| `classroom_login_required` | 先 access，再按诊断 relogin 一次；包括HTTP200业务体的已知428失效响应，其他428不推断为登录问题 |
| `login_required`、`permission_denied` | 按当前诊断处理正常登录/权限；不绕过身份或改目标环境 |
| `browser_backend_unavailable` | 当前后端不可用；按 use_emit_script 提示，核实已有浏览器 evaluate 后改用脚本桥接，无此能力则用页面 |
| `existing_playwright_cli_unavailable` | 显式 JS 入口或现有 Node 缺失；保留具体诊断，不回退已失败的 wrapper/npx、不下载安装 |
| `source_browser_access_unavailable`、`node_websocket_unavailable`、`isolated_browser_requires_existing_node`、`isolated_browser_executable_unavailable` | 现成登录态迁移/隔离接入能力不足，不等于正常登录不可用；无既有记录就使用其他现有授权后端/evaluate，必要时正常登录任务页后 access 核实。有失效记录则保留恢复点，确需回退先 session-close；不让老师开 CDP、提供端口，不装工具或获取浏览器数据库 |
| `pdf_read_timeout` | 停止重复文件检查；使用现有已授权文件工具或可读副本做一次验证，不推断权限根因，不重传已成功材料 |
| `source_browser_selection_required`、`source_context_selection_required` | 多个真实来源未能唯一确定；从现有工具取得准确 CDP/target 定位后再连接，不猜来源或让老师配置参数 |
| `source_identity_changed`、`source_identity_mismatch`、`isolated_identity_mismatch`、`isolated_identity_changed` | 来源、目标或已记录身份不一致；停止写入，不换身份或环境绕过 |
| `isolated_session_missing`、`isolated_session_closed`、`isolated_session_expired` | 独立会话缺失或失效；先 session-status 核实，尝试一次 session-connect 续接原身份；无能力则保留恢复点，不静默回退用户页面或重放写请求 |
| `isolated_cleanup_incomplete` | 本次目标上下文/自建浏览器或临时目录清理未完成；保留控制记录，以原任务名 session-close 重试，不手删记录、不关源浏览器 |
| `invalid_api_response` | 返回不是有效业务响应；按 read_state_before_retry 先只读查当前状态，不重放写请求 |
| `contract_mismatch` | 核对真实部署响应与当前参考，必要时用页面，不猜路由或翻压缩源码 |
| `rate_limited` | 按服务端提示有界等待后只读核对，不紧循环重放写 |
| `transport_uncertain` | 请求可能已送达，先读状态与持久化结果，不能直接重发 |

`access` 只读 `/api/session?refresh_profile=false&include_models=false` 和 `/api/classroom/login-check`，返回 `access_verified`、`classroom_login_required` 或 `authentication_unverified`，以及 principal 的 user_id/school_id/identity 和 classroom_valid。它仍受真实权限校验，也不证明模型可用，模型能力只在所需阶段检查；checkpoint.auth_receipt 仅保存非敏感 principal 与 recovery_started，不存 CAS URL，后续 `identity_changed` 时停止写入。

确切课堂失效诊断的 next_action 为 `check_access_then_relogin`。`relogin` 使用既有 `POST /api/login?force=true&return_to=<本批次路径>`，login_url 仅在浏览器内存保留并延迟导航，不进入输出、checkpoint 或日志；使用独立会话时恢复导航也只在该上下文执行，不去老师的源页面操作。emit 生成不导航，evaluate 执行后才导航。`authentication_navigation_started` 仅表示导航启动；`authentication_navigation_deferred` 表示页面有弹窗或焦点编辑，先保留用户未保存草稿；`authentication_recovery_pending` 表示已启动恢复，不再重复登录。回到原 origin 后用 access 验证同一教师、学校及有效课堂会话，再只读当前业务状态后续做；不自动重放写请求。一次恢复仍无效就保留原 batch 与阻塞，不翻源码、猜刷新入口或循环重登，也不据此断言配置故障。

## 恢复与终点

先核对本次选择的stop_after；只批改终点不因批改完成自动扩展到analysis/check。恢复沿用同一材料已确认的终点，用户明确变更才更新；未知业务终点先补问，不能把旧checkpoint兼容默认check当成本次授权。

checkpoint 仅作恢复定位与有限回执，保存 origin/batch_id、题框版本/源/参考/签名/粒度目标和关联目标/版本，权限 0600。它不是服务端幂等、跨步骤事务或 exactly-once。Python/JS 拒绝不同 origin/batch；题框恢复还核对当前源 PDF、参考卷、revision、frames_signature，同 operation_id 的编辑内容变更不能复用旧回执。关联回执仅在目标列表和当前 roster 版本匹配时复用，并回读逐项实际目标。

超时、PATCH 成功但回执丢失、确认超时或顺序关联部分失败，先读取当前状态/版本与实际保存内容，再做剩余步骤；不能重发整个 shift 包。409 回读版本后重新判断，不强改 token/revision；范围确认无用户变化却再次同因 409，按主文保留证据并停止自动循环。partial/failed 只恢复失败范围，stale 先核来源，不删除用户数据重来。

最终直接 check；无具体定位需要时不先重复 inspect。最终检查必须保留整批总数、实际覆盖与未覆盖数。读 `completion` 的阶段布尔及 media_pending、`remaining` 按错误类别与严重程度汇总的身份/结构/范围/媒体计数；`roster_coverage_gap` 不代表身份完整，原始 preflight.ready 可能仅覆盖平台当前已关联 subset。整体通过看顶层 ready/outcome 及全批覆盖，姓名未关联、结构不完整、范围不足或媒体 pending 时，全批仍未通过，不改 scope 求 ready，也不能说手动补姓名即可全量通过。报告区分“已执行检查，未通过/未完成”与“全批检查通过，尚未同步”，如实列出所有剩余项。保留教师原判与 `JUDGMENT_BINARY_MAPPING` 等真实警告，不为消警告改判。检查模式禁止 imports POST、确认同步与提交型 resume；最新全批 ready 且必要核验完成后，给真实批阅台链接、统计、warnings 和验证边界即停止，不自启全量深审。

计划、完整结果、校对图和证据只在本次受控目录使用，不写凭证或学生答案全文到交付报告。报告区分服务端并发任务时长与墙钟耗时；模型 usage 缺失就是未知，不能当零。隔离回放复用旧产物时明确“无新模型调用”，只证明该环境的编排表现，不推断新卷识别质量、真实线上全流程速度或 token 节省。
