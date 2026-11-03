# 办公智能体接入

老师只需提供PDF或已有批阅台链接，地址、会话和工具参数由智能体获取。v1.8.0将上传、选班和grading纳入接口/CLI主流程。能导入技能或生成脚本不等于已访问授权浏览器、完成实卷验收。

## WorkBuddy 导入

从仓库main取得 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)，按 [WorkBuddy官方技能管理说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)，在“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”选择ZIP。可安装版本以已核实官方main元信息与对应提交为准；下载后核对包内SKILL.md版本，导入后回读实际版本与目标一致，不与Releases历史包混用。见 [技能更新流程](skill-update.md)。官方对话安装面向技能市场，不保证把GitHub链接贴入对话即可安装本包。

先使用产品现有文件/浏览器工具。[Agent Browser 官方说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/WorkBuddy-Zero-Cost-Skill-Top-10/Agent-Browser) 展示打开、滚动、点击与截图，不能单独证明支持本包 CLI 后端的 eval --stdin/--session、可 evaluate JavaScript，或已连接用户 Chrome。只使用当次实际开放并已授权的能力，不擅装 Agent Browser、插件或运行时。

## 按实际能力执行

1. 先access核实身份、学校、课堂会话和同源，不凭默认地址称生产。新PDF用upload经FormData接口创建，原生文件工具仅在需要时注入文件；已有链接沿用原记录。课程/班级用classes、class-students、scope，不索取或导出Cookie、令牌、storage state。
2. 已有Python、兼容浏览器CLI后端与真实会话时，scan与grading均用 [CLI](cli.md) 的run --follow；定点缺口先查api-list，再用受限api-call，不默认操作业务页面。
3. 无兼容CLI后端、但产品已有执行命令和浏览器evaluate时，用`--emit-script <PATH>`生成engine_file与小步骤script_file。首次或导航后先evaluate引擎取得engine_loaded，再执行小步骤；同页面后续只读/执行小步骤并collect，复用checkpoint，不反复展开完整引擎。engine_not_loaded时按evaluate_bootstrap_file补加载，尚未发业务请求；--standalone-script仅保留旧兼容形式。生成本身不执行，emit仅单轮预算、不绕过登录；不手写fetch/XHR、猜路由或翻压缩源码。
4. evaluate只是同源接口执行宿主，不要求逐步导航、点击或截图。正常登录、确需文件注入和必要图证以外，只有接口不支持/不兼容或工具缺能力的具体证据，才定点使用页面。确实缺能力时一次说明可完成步骤、已核实的接入方法或阻塞与恢复点；不反复索要会话名/CLI参数，不要求安装Codex、Docker或云主机wrapper。

| 产品 | 验证边界 |
| --- | --- |
| WorkBuddy | 有按官方入口上传 ZIP 的试用路径；本轮仅隔离适配/编排验证，未完成该产品实机实卷验收 |
| 豆包办公 | 未核实完整自定义技能包的导入/执行契约，未实机验收；按当次实际文件、网页和执行能力处理 |
| 千问办公 | 同样未核实完整包契约、未实机验收；Qwen Code 的终端/技能能力不能当作千问办公证据 |

CLI覆盖scan、供应商快速批改和答案卷智能批改；83项受限接口的功能、字段和门槛见 [API参考](api.md)。内置工具不替代选参考卷、实际审图、目录校对或用户必要业务判断。已授权检查流程中的框/目录确认、学生关联和既定媒体准备直接推进，不为步骤增加授权询问。

默认终点仍是全批真实同步检查：独立计算题、全批统计和标准题来源严审保留，个人图按异常修，姓名不清暂留未关联。覆盖不足不得称 ready 或改 subset 求通过；检查模式不调用 imports 或提交型恢复。仅本次明确要求实际同步才进入提交。
