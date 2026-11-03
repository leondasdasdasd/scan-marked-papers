# 办公智能体接入

本版提供可导入技能包、工具选择规则和可选浏览器 CLI 适配；导入成功不等于已能访问教师浏览器或完成实卷。老师只需提供 PDF 或已有批阅台链接，技术地址与参数由智能体获取。

## WorkBuddy 试用

按 [WorkBuddy 官方技能管理说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/Function-Description/Skills-Market)，下载本仓库 main 的 `scan-marked-papers.zip`，在 WorkBuddy 打开“专家·技能·连接器 → 技能 → 添加技能 → 上传技能”，选择该 ZIP。导入后核对技能名称与包内 `SKILL.md` 的版本为 1.6.0。官方对话安装指向技能市场，不保证把 GitHub 链接贴进对话即可安装本包。

先使用 WorkBuddy 当前已有的文件和浏览器工具。官方 [Agent Browser 说明](https://www.codebuddy.cn/docs/workbuddy/From-Beginner-to-Expert-Guide/WorkBuddy-Zero-Cost-Skill-Top-10/Agent-Browser) 展示打开网页、滚动、点击和截图；这些能力不能单独证明已支持本包 CLI 所需的 `eval --stdin`、`--session` 或已连接用户 Chrome。实际缺少 CLI 契约时直接走原生浏览器，不擅自安装 Agent Browser、插件或运行时。

## 按实际能力选择路径

| 产品 | 本版接入边界 |
| --- | --- |
| WorkBuddy | 提供按官方入口上传 ZIP 的试用路径；核实当次可用文件、浏览器和执行工具后选择页面或 CLI。本版适配与合成验证不等于 WorkBuddy 实机实卷验收 |
| 豆包办公 | 尚未核实自定义完整技能包的导入与执行契约，也未实测；仅使用当前产品实际开放且已授权的文件/网页能力，不宣称已支持完整包或 CLI |
| 千问办公 | 同样按当前产品实际工具接入，尚未核实完整包契约、未实测；Qwen Code 是其他产品，其终端、技能或浏览器能力不能作为千问办公的证据 |

智能体先检查已有工具和连接，再选择当前能执行的路径：

1. 从已有链接提取受支持业务路由的 origin/batch id；新 PDF 未指定地址时用 `https://piyue.yungu.org`。先读当前页面和身份，核实学校及目标环境，不凭默认域名称生产。
2. 复用实际可操作的已授权登录会话。不能因为用户 Chrome 已打开就声称接管成功，不自动读取或导出 Cookie、令牌、storage state，也不要求老师发送这些材料。未登录时用产品现有登录流程；连接授权由产品工具完成。
3. 新 PDF 通过产品原生文件工具与页面上传；已有批次可优先走会话内同源接口。只有已经具备 Python、兼容浏览器后端和真实会话时才使用 [CLI](cli.md)，否则继续原生页面。CLI 仅支持 scan，不扩展到 grading；无 JavaScript 执行能力也可按实际页面完成可用步骤。
4. 缺少必要工具时，一次说明当前能做到哪一步，以及该产品已有的具体可执行接入方式；没有已核实方式就如实报告能力阻塞和恢复点。不反复追问地址、会话名或 CLI 参数，不要求安装 Codex、Docker、云主机 wrapper，不擅自安装扩展能力。

业务终点仍是最新真实全批同步检查：保留独立计算题、全批统计和参考图严审要求，姓名不清暂留未关联；覆盖不足保持 ready=false，不以 subset 冒充完成，不调用 imports 或提交型恢复。只有本次明确要求同步时，才按原技能同步流程处理。
