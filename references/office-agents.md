# 办公智能体接入

老师只需提供PDF或已有批阅台链接，地址、会话和工具参数由智能体获取。v1.10.0 每天首次使用检查版本，任务首次尝试独立会话接入，并按教师选择的终点使用上传、选班和 grading 的接口/CLI 主流程。能导入技能或生成脚本不等于已访问授权浏览器、建立独立会话或完成实卷验收。

## WorkBuddy 导入

从仓库main取得 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)，按 [WorkBuddy官方技能管理说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)，在“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”选择ZIP。可安装版本以已核实官方main元信息与对应提交为准；下载后核对包内SKILL.md版本，导入后回读实际版本与目标一致，不与Releases历史包混用。见 [技能更新流程](skill-update.md)。官方对话安装面向技能市场，不保证把GitHub链接贴入对话即可安装本包。

先使用产品现有文件/浏览器工具。[Agent Browser 官方说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/WorkBuddy-Zero-Cost-Skill-Top-10/Agent-Browser) 展示打开、滚动、点击与截图，不能单独证明支持本包 CLI 后端的 eval --stdin/--session、可 evaluate JavaScript、已连接用户 Chrome，或能读取 HttpOnly Cookie。只使用当次实际开放并已授权的能力，不擅装 Agent Browser、插件、浏览器或运行时。

独立会话接入使用本机现成 Node（须有内置 WebSocket）、已有 Chrome/Edge/Chromium 和现成已授权 CDP；`session-connect` 会先复用已核验独立会话，再只读查找已开放来源。源页不导航、不点击，必要 Cookie 仅在受控进程内存中交给新的独立上下文，核验同一教师、学校及有效课堂会话后才继续；Cookie、令牌不交给模型、不粘贴到聊天、不写文件。已有 evaluate 不能靠 document.cookie 读取 HttpOnly 登录态；有点击/截图工具也不能据此声称支持迁移。详细命令、支持的 origin、控制缓存与清理边界见 [CLI](cli.md)。

## 每天首次使用检查更新

现有工具可运行Python时，正常处理材料前先用`skill_update.py ensure`：每天首次按本机自然日查询官方main，同日读取持久记录；有更高版本自动校验并仅更新本技能，成功后回读新SKILL.md。网络失败当天不反复查，次日再试；本地修改冲突或旧安装无manifest时保留旧版，不能强覆或说已是最新版。只问版本用离线status，明确立即刷新才force，详见 [更新说明](skill-update.md)。

现有命令/下载/文件工具能实现同样保护时才按同一逻辑执行；只有ZIP导入页面、无Python或不能可靠写回技能时，明确自动更新不可用并提供官方导入入口，不要求老师安装Codex、Python、插件或新运行时。产品能导入本包不等于能自动更新；这不是无人使用也会运行的后台定时任务。

## 按实际能力执行

1. 收到材料先让老师选择扫描已批卷或批改未批卷；批改时可批完停止或继续整理，整理后只检查或同步课堂。扫描包含整理，明确同步已包含必要整理与检查；已明确项不重复问，缺项集中问一次，选定前只读检查。任务首次由智能体按 [CLI](cli.md) 尝试一次 session-connect，不让老师配置来源端口、任务名或参数；成功后用 access 核实身份、学校、课堂会话和同源，不凭默认地址称生产。新 PDF 用 upload 经 FormData 接口创建，原生文件工具仅在需要时注入文件；已有链接沿用原记录。课程/班级用 classes、class-students、scope，不向老师索取认证材料，不导出 Cookie、令牌或 storage state。
2. 已有独立会话时，正常 CLI 按同 origin 和 browser-session 自动复用；显式 --browser-backend isolated 可限定不回退用户页。没有既有独立记录且来源能力不足，才直接使用其他现有授权后端；已有记录失效则保留恢复点并尝试续接原身份，无法恢复就停写，确需回退先 session-close 再核验实际会话。已有 Python、兼容后端与真实会话时，scan 与 grading 均用 run --follow；只批改加 --stop-after grading，整理路径加 --stop-after check，定点缺口先查 api-list，再用受限 api-call，不默认操作业务页面。
3. 无兼容CLI后端、但产品已有执行命令和浏览器evaluate时，用`--emit-script <PATH>`生成engine_file与小步骤script_file。首次或导航后先evaluate引擎取得engine_loaded，再执行小步骤；同页面后续只读/执行小步骤并collect，复用checkpoint，不反复展开完整引擎。engine_not_loaded时按evaluate_bootstrap_file补加载，尚未发业务请求；--standalone-script仅保留旧兼容形式。生成本身不执行，emit仅单轮预算、不绕过登录；不手写fetch/XHR、猜路由或翻压缩源码。
4. evaluate 只是同源接口执行宿主，不要求逐步导航、点击或截图。正常登录、确需文件注入和必要图证以外，只有接口不支持/不兼容或工具缺能力的具体证据，才定点使用页面。确实缺能力时一次说明可完成步骤、已核实的接入方法或阻塞与恢复点，不把回退执行说成独立接入成功；不反复索要会话名/CLI 参数，不要求安装 Codex、Docker 或云主机 wrapper，不读取/解密浏览器 Cookie 数据库、不重启用户 Chrome 开调试。任务结束用 session-close 仅清理本次独立上下文和自建浏览器，不跟随 SSO 全局退出，不关闭源浏览器。

| 产品 | 验证边界 |
| --- | --- |
| WorkBuddy | 有按官方入口上传 ZIP 的试用路径；未完成该产品的独立会话接入或实机实卷验收，不能据官方点击/截图说明认定可迁移登录态 |
| 豆包办公 | 未核实完整自定义技能包的导入/执行契约，未实机验收；按当次实际文件、网页和执行能力处理 |
| 千问办公 | 同样未核实完整包契约、未实机验收；Qwen Code 的终端/技能能力不能当作千问办公证据 |

CLI覆盖scan、供应商快速批改和答案卷智能批改；83项受限接口的功能、字段和门槛见 [API参考](api.md)。内置工具不替代选参考卷、实际审图、目录校对或用户必要业务判断。已授权检查流程中的框/目录确认、学生关联和既定媒体准备直接推进，不为步骤增加授权询问。

按老师选择交付：只批改核对全批原始done与基础结果计数后停止，不自动整理或同步检查；选择整理时再做全批真实同步前检查。独立计算题、全批统计和标准题来源严审保留，个人图按异常修，姓名不清暂留未关联。覆盖不足不得称 ready 或改 subset 求通过；检查模式不调用 imports 或提交型恢复。仅本次明确要求实际同步才进入提交。
