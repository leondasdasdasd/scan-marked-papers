# 办公智能体接入

老师只需提供 PDF 或已有批阅台链接，地址、会话和工具参数由智能体获取。v1.7.1 从仓库 main 的 ZIP 分发，沿用内置脚本桥接并补齐会话恢复与全批状态。能导入技能或生成脚本不等于已访问授权浏览器、完成实卷验收。

## WorkBuddy 导入

从仓库 main 下载 v1.7.1 [scan-marked-papers.zip](https://github.com/leondasdasdasd/scan-marked-papers/blob/main/scan-marked-papers.zip)，按 [WorkBuddy 官方技能管理说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)，在“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”选择该 ZIP，下载后核对来源提交和包内 SKILL.md 版本，导入后回读实际版本为1.7.1。本轮不创建 GitHub Release，勿混用 Releases 中的旧包；更新核对以已核实官方 main 元信息为准，见 [技能更新流程](skill-update.md)。官方对话安装面向技能市场，不保证把 GitHub 链接贴入对话即可安装本包。

先使用产品现有文件/浏览器工具。[Agent Browser 官方说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/WorkBuddy-Zero-Cost-Skill-Top-10/Agent-Browser) 展示打开、滚动、点击与截图，不能单独证明支持本包 CLI 后端的 eval --stdin/--session、可 evaluate JavaScript，或已连接用户 Chrome。只使用当次实际开放并已授权的能力，不擅装 Agent Browser、插件或运行时。

## 按实际能力执行

1. 新 PDF 用原生文件工具/页面上传；已有链接沿用原记录。先核实身份、学校、环境和同源，不凭默认 `https://piyue.yungu.org` 称生产。复用实际连接的授权会话，不索取或导出 Cookie、令牌、storage state。
2. 已有 Python、兼容浏览器 CLI 后端与真实会话时，已支持步骤使用 [CLI](cli.md) 的 run --follow。
3. 无兼容 CLI 后端、但产品已有执行命令和浏览器 evaluate 时，用内置 `--batch-url <记录链接> --emit-script <PATH>` 生成标准序列化的自包含 JS，交现有目标页面原样执行；不手写 fetch/XHR、不猜字段/路由或翻压缩源码。生成本身不执行；完整业务结果保存后用 collect 回存 checkpoint，下一轮复用。emit 仅单轮预算，不持续后台 follow，也不绕过登录。
4. 只有工具实际不兼容、缺命令/evaluate 能力或步骤未覆盖的具体证据，才用真实页面/接口补缺口；必要文件、上传或浏览器能力确实缺失时，一次说明当前可完成的步骤、已核实的接入方法或阻塞与恢复点。不反复索要会话名/CLI参数，不要求安装 Codex、Docker 或云主机 wrapper。

| 产品 | 验证边界 |
| --- | --- |
| WorkBuddy | 有按官方入口上传 ZIP 的试用路径；本轮仅隔离适配/编排验证，未完成该产品实机实卷验收 |
| 豆包办公 | 未核实完整自定义技能包的导入/执行契约，未实机验收；按当次实际文件、网页和执行能力处理 |
| 千问办公 | 同样未核实完整包契约、未实机验收；Qwen Code 的终端/技能能力不能当作千问办公证据 |

CLI 仅支持 scan，grading 和未支持步骤按原技能真实页面/接口。内置工具不会替代选参考卷、实际审图、目录校对或用户必要业务判断。已授权检查流程中的框/目录确认、学生关联和既定媒体准备直接推进，不为步骤增加授权询问。

默认终点仍是全批真实同步检查：独立计算题、全批统计和标准题来源严审保留，个人图按异常修，姓名不清暂留未关联。覆盖不足不得称 ready 或改 subset 求通过；检查模式不调用 imports 或提交型恢复。仅本次明确要求实际同步才进入提交。
