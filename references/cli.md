# 批量 CLI 编排

本说明对应 `scripts/paperflow.py`、`paperflow.js` 与兼容 `paperflow_base.py`。实际 `workflow_mode=scan` 且已有可用浏览器执行后端时优先使用；没有 CLI 或不支持当前阶段时使用产品原生浏览器与真实接口/页面。默认终点为真实全批同步检查，不提交导入；已有导入与停止标记优先只读。办公产品的导入与能力边界见 [office-agents.md](office-agents.md)。

## 入口与输出

参数由智能体从当前环境获取，不交给老师配置。Python 全局参数放在子命令前；已有链接优先 `--batch-url <记录链接>`，支持经核实的 http(s) 业务路由，例如 `/exams/{id}/analysis?class_id=...`，自动提取 origin/batch id。也可用 `--base-url <origin> --batch-id <ID>`，base-url 默认 `https://piyue.yungu.org`；显式参数与链接冲突会拒绝。默认地址不证明生产，执行前核实身份、学校、权限与环境，页面必须同源，不跟随重定向。

按现有能力选一路，不擅装工具：

| 路径 | 适用条件与边界 |
| --- | --- |
| `--browser-backend playwright` | 已有 run-code/page.evaluate 适配器与真实已登录 `--browser-session`。`--wrapper` 默认 `~/.codex/skills/playwright/scripts/playwright_cli.sh`，可指向现有兼容入口；不是办公产品安装前提 |
| `--browser-backend agent-browser` | 已有可执行文件支持 `--session <会话> --json eval --stdin`，返回 `success:true`、data.result 为含布尔 ok 的对象。`--browser-executable` 默认 agent-browser；实际 session 须已连接授权页面，仅能点击/截图不证明兼容 |
| `--emit-script <PATH>` + 现有浏览器 evaluate | 不要求 browser-session 或兼容 CLI 后端。只生成自包含 JS 表达式，返回 `executed=false`，不执行。由当前产品实际提供的 evaluate 在目标授权页面原样执行，再按下文 collect；不重新拼 fetch |
| 原生页面 | 当前产品无 JavaScript evaluate 或命令执行能力时，按真实页面完成可用步骤并保留阻塞 |

真实后端仍要求实际已登录会话，不自动接管 Chrome、登录或导出 Cookie/令牌/storage state。emit 也不绕过登录、同源和权限校验；带 `--metadata` 的 `review` 离线渲染与 `collect` 不要求 browser-session，`review`/`collect` 均不支持 emit。不带 metadata 的 review 仍从浏览器读取 snapshot，需要真实会话。`paperflow.py` 与兼容 `paperflow_base.py` 的正常浏览器后端均支持 playwright/agent-browser；本节 batch-url、emit、collect 和新增目录确认以主入口 `paperflow.py` 为准。

可选全局参数：`--timeout`（1–180 秒，默认 45）、`--interval`（2–30 秒，默认 5）、`--checkpoint <本地JSON>`、`--output <完整结果JSON>`、`--verbose`。以下由智能体替换为实际值：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> --browser-backend agent-browser --browser-session <真实会话> --checkpoint <受控目录/cp.json> --output <受控目录/result.json> run --follow --max-seconds 600
```

没有兼容 CLI 后端但现有工具可 evaluate 时：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> --checkpoint <受控目录/cp.json> --emit-script <受控目录/step.js> run
```

读取生成文件，将整个 JS 表达式原样交给现有浏览器 evaluate。取 evaluate **业务表达式返回的完整 JSON envelope** 原样保存到受控 `browser-result.json`；工具外层包装、截图或 compact 摘要不能当业务结果。再离线回收：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> --checkpoint <受控目录/cp.json> --output <受控目录/result.json> collect --result <受控目录/browser-result.json>
```

collect 不访问浏览器、不重新执行或再次验证业务，校验布尔 ok 及 checkpoint.origin/batch_id 一致后回存 checkpoint、完整 output 并输出 compact。保留完整浏览器结果中的 checkpoint，下一轮生成脚本复用该文件。emit 即使带 `--follow` 也只运行一轮 timeout 预算，不会持续后台跟进；waiting 时先 collect 保存结果，再按当前状态生成下一轮，不重复启动任务。跨轮自动等待由智能体管理，每阶段沿用本轮墙钟累计预算（默认与普通 follow 一致为600秒，可按用户明确需要调整），不能每次单轮重置；这不是 CLI emit 已实现的全局预算。累计到限或持续同因无进展即结束本轮，报告“处理中/检查未完成”、进度、链接与原 checkpoint，下次仍接续原 batch，不无限轮询、重传或假报 ready；不按固定轮数机械判定失败。

emit 结果已 collect 且有本地原 PDF 时，可直接复用元数据生成校对包，无须再读浏览器：

```bash
python3 <技能目录>/scripts/paperflow.py --batch-url <本次记录链接> review --metadata <受控目录/result.json> --pdf <本次原PDF> --out <受控目录/review>
```

metadata 接受裸 snapshot、包含 result 的完整 envelope，或 run 的 result.review；必须匹配本次 batch_id，并严格核验原 PDF SHA。生成图仍标 reviewed=false，须实际审图。

默认 stdout 是紧凑 JSON，保留下一步摘要与路径，省去完整 checkpoint、调用明细和大块几何；`--output` 保存完整 envelope，只有诊断需要才 `--verbose`。`snapshot --output <JSON>` 位于子命令后，保存裸 snapshot；与全局 output 不同。完整文件留在受控目录，按需读取字段，不反复整份送入上下文。timeout 为单轮预算，正常后端 `run --follow --max-seconds` 为跨 waiting 的有界跟进预算，都不是服务端完成承诺。

`ok`/退出码只说明工具执行，业务完成看 outcome、ready、submitted 与真实全批覆盖。主入口没有 upload/session/watch；新上传、grading 和未支持阶段按原技能。新 PDF 用现有文件工具/页面上传后接 CLI。兼容 `paperflow_base.py` 的 session/upload/check 按自身 help；upload 仅 scan，agent-browser 后端返回 `upload_requires_native_browser_file_tool`，不假造成功。

| 命令 | 用途与边界 |
| --- | --- |
| `run [--plan <JSON>] [--review-pdf <PDF> --review-out <DIR>] [--follow --max-seconds 600]` | 按真实阶段推进；waiting 可有界等待，审图、目录校对、失败或终点返回。成对 review 参数复用当前读取生成校对包 |
| `snapshot [--output <裸snapshot JSON>]` | 读批次/catalog，给源 PDF SHA、版本、完整框与精简目录（正文、稳定选项 ID、blank_ids、answers/extras）；reviewed=false 不证明看过图 |
| `review [--metadata <JSON>] --pdf <原PDF> --out <受控目录>` | 带 metadata 则复用已保存元数据离线渲染，不访问浏览器、不需会话；省略则从浏览器取 snapshot。核验 batch_id 和 PDF SHA，生成全参考页、接触表与 review.json，需 pymupdf/Pillow；仍 reviewed=false |
| `frames --edits <JSON> [--confirm]` | 本地整包校验 set/shift/split/promote_children，最多一次 PATCH，再按需确认；预切正常、题框非空且实际已审无修改时可 operations=[]，零 PATCH；失败/空框不能批准。保存与确认不是跨请求事务 |
| `catalog --plan <JSON>` | 确认已审目录及本批处理范围，回读真实完整 questions，agent 不必复制富题对象；不修改目录，不提交课堂。run 根 plan.catalog 同效 |
| `associate --plan <JSON>` | 整批证据/版本校验后顺序关联、采用新 roster revision，末尾回读；最多50项，可能部分保存，不是原子事务 |
| `inspect` | 全批人数、叶题、作答、重复遗漏与未关联聚合；不是视觉验收 |
| `check` | 全批检查，按真实门槛准备媒体，不改配置或缩范围；只在媒体 pending、无 blocker/failure、结构/覆盖完整且全关联时可能 start，活跃准备任务复用等待 |
| `diagnose` | 读真实 preflight 与阻塞，不启动媒体；诊断成功不代表 ready |
| `retry-precut --page <0-based相对页> --frame-revision <当前值>` | 从返回 retryable_pages 取证后只重试具体页，不自动全页重试 |
| `evidence --paper-id <ID> [--question-id <QID> ...]` | 定点版本、PDF页码、目录与作答证据；不输出 review_token，reviewed=false |
| `responses --plan <JSON>` | 实际审卷后定点修复作答结构，仅 response_only、不改教师判定、不调模型；顺序保存，失败即停，可能部分保存 |
| `usage` | 缺失 usage 保持 null、tokens_complete=false，不以零补齐 |
| `collect --result <完整浏览器业务JSON>` | 离线校验并回存 emit 执行结果，不执行浏览器或改变业务 |

## 按返回边界推进

先运行 `run --follow`（emit 路径按单轮生成/执行/collect），复用已有校对包与计划。等待、标准JSON序列化和状态读取交给内置工具，不逐轮 snapshot、翻压缩源码、猜字段/路由或临时重写 fetch。工具返回不足时，按 [接口参考](api.md) 补最小必要读取。

| 返回边界 | 智能体下一步 |
| --- | --- |
| `needs_reference` | 按主文规则，依据真实清晰度、完整性与教师批注选本批参考卷；写 reference_student_id 后继续。返回前五份 id/index/pdf_pages/原图URL，供轻量取证；没有评分就不能编造高正确率，不把摘要当业务范围 |
| `needs_precut_recovery` | 先看 diagnosis 的 code、failed_pages、issues、frame_revision、retryable_pages；空框/失败页不能当 `needs_frame_review`。只使用 CLI 返回的 retryable_pages；空框时列表可能来自已核实的每份页数，不代表各页已确认失败。选定具体页、核实证据后只重试该页，不能自动全页重试。缺配置、不可恢复或同因持续失败时报告诊断并保留恢复点，不重复空跑 |
| `needs_frame_review` | 复用 run 生成的 review 包，实际核对全部参考页，一次整理必要框修改，再应用并确认。没有包且已有本地原 PDF 时才单独 review，已有元数据优先 --metadata 离线复用；已有链接无本地 PDF 时按原技能读取参考页，不索要或重传原卷 |
| `needs_catalog_review` | 一次读取精简目录正文、选项 ID 与逐空定义，对照已审参考图核对内容、答案和独立题结构；需要修改先按真实接口/页面保存并回读新版本，实际审完后用 catalog --plan 确认，再 run |
| `needs_targeted_recovery`、partial/failed 或检查阻塞 | 先读具体失败与 review_tasks，以 evidence 取受影响卷/题定位，实际核对必要原卷证据；仅作答结构问题可走 responses，其他按真实恢复接口。不默认重跑全批 |
| `needs_duplicate_review` | 本次范围存在重复学生卷；依据真实证据确定取舍，使用实际页面/接口处理，不自动任选、不提交确认 |
| `waiting` | 任务仍在进行；沿用原计划与 checkpoint 正常 follow，或按 emit/evaluate/collect 单轮接续。emit 各轮共用该阶段本轮累计墙钟预算，不重置；到限或持续同因无进展时交付处理中/未完成、进度、链接和原 checkpoint，不重复启动任务 |
| `source_stale` | 核实来源变化与版本，重新判断受影响范围，不重批已有人工结果 |
| `existing_import_readonly`、`stopped_readonly` | 只读报告已有同步或停止状态，不恢复会提交的任务 |
| `unsupported_workflow`、`unknown_stage`、`no_progress`、`iteration_limit` | 保留当前状态并按原技能查明或回退；不改 workflow_mode 求通过，不称全批完成 |

完成阶段的 `review_tasks` 按 paper_id/index/pdf_pages 聚合 blocker/failure、相关题目录与 identity_pending，用于一次组织必要证据与修复。没有真正看过图，不能把 `reference_reviewed`、`visual_review_performed` 或客户端回执当视觉完成证明。

## 一次判断、整包应用

**参考与范围。** run 计划根可传 `reference_student_id` 与 `scope`。scope 含实时 revision、semester_id、class_ids、scope 对象、`evidence_confirmed=true` 和非空 evidence_note，仅写已核实的课程/班级与本次授权范围。工具核对当前集合，相同可复用，不同才按当前 roster revision 更新；服务端仍负责权限校验。已有参考不为追求更高正确率重开全批，无证据不造百分比。

**题框。** 计划含 operation_id、当前 frame_revision/source_pdf_sha256/reference_student_id、`reference_reviewed=true`、`scope_reviewed=true`、reviewed_pages（覆盖全部 0-based 参考相对页）、operations，可含 expected_leaf_labels。只有实际审过页和范围才填写确认标记；少量留白或不影响归属的个人框偏移不修。

operations 支持：

- `set`：按 id 改 regions/label；`shift`：用 ids、归一化 dx/dy 移动。
- `split`：原目标无子框时，以至少两个 children（真实 id/label/regions）替换原框，子框 parent_id=null。
- `promote_children`：目标已有直接子框时，显式列全全部直接子框的 id/label/regions；保留子 ID、移除父框，将这些子框提升为独立根题。不能漏列子框，也不支持含孙题的嵌套结构。必须先实际审图，不能仅因已有父子结构自动执行。

`frames --confirm` 或 run 计划根的 frames 使用同一计划。run 根还可有 scope、associations、expected_leaf_labels、reference_reviewed。确认后仍可能停在目录待审，不代替目录保存或 merge-preflight/confirm-and-start。

**独立计算题。** N 个独立算式最终必须是 N 道可分别查看/订正的业务叶题，不是 N 框仍一题、N 个空或组合题。填写本次真实 expected_leaf_labels，CLI 会保存并续验粒度目标；核对叶题标签/数量、parent_id=null，排除 content.children、composite/virtual_parent、is_composite/isComposite、business_question.isComposite 及业务题型目录 isComposite 所代表的合题，且无额外父标题题。`expected_granularity_verified` 只是一项程序核对，不能替代实际目录和页面核验。

**关联。** 计划为 `{revision:实时roster版本,assignments:[{paper_id,student_id,evidence_confirmed:true,evidence_note:必要证据摘要}]}`。只放本次真实候选与清楚证据，脚本中的 true 不是证据。姓名看不清保持未关联，不反复 OCR、追问或凭剩余名单猜；继续不依赖该身份的允许步骤。run 在 completed 阶段才应用 associations，其他真实阶段按原技能处理，不能改 scope 求通过。

## 目录确认计划

`catalog --plan` 或 run 根 `catalog` 计划含：operation_id（8–100个字母、数字、下划线或连字符，匹配 `^[A-Za-z0-9_-]{8,100}$`）、当前 source_pdf_sha256/reference_student_id/frame_revision/catalog_revision、`reference_reviewed:true`、`scope_reviewed:true`、`catalog_reviewed:true`、覆盖全部相对页的 reviewed_pages，可含本次 expected_leaf_labels。这些标记只能在实际审图、审范围与审目录后填写，不能作为自动验收证明。

命令回读服务端完整真实 questions 用于确认；不负责目录内容修改/保存。需要修改时先用真实编辑接口/页面，回读新 revision、复核后再给新计划，不能复用旧已审标记。v2 仅当前记录 `source_ids=[]` 走 merge-preflight 和 confirm-and-start；有重复返回 needs_duplicate_review，不确认。旧 confirm 仅真实版本允许时使用。目录确认不是课堂 imports，`submitted=false`；accepted 仍须观察原任务完成。

checkpoint 保留目录确认中/已接受的有限回执。确认超时先只读查原操作与当前目录状态，不循环预检、换 operation_id/幂等键重发；版本/来源变化必须重新判断。未经用户修改却同因409持续发生时按下文有限恢复停止。

## 定点证据与作答结构修复

先用 `review_tasks` 确定卷、题，再调用 `evidence --paper-id <ID> --question-id <QID>`；多个题重复传 question-id，一次取齐。证据包包括 source_pdf_sha256/frame_revision/catalog_revision、paper_id/index/pdf_pages、精简 questions；observations 的真实字段为 question_id、verdict、answer_text、answer_state、response_conversion_status、blanks、response_regions、source_refs，其中 blanks 含 blank_id、answer_text、answer_state、verdict。按定位实际查看必要原卷或已有图证，包本身不证明已审；保留教师原批注与真实不确定状态。

`responses --plan` 根必须含当前 source_pdf_sha256、frame_revision、catalog_revision 和 1–100 个 assignments；每项含 paper_id、question_id、`evidence_confirmed:true`、非空 evidence_note，并按该题真实单一互动元素提供：

- 选择题：`selected_option_positions:[1-based位置]`。例如可见 C 对应位置 3；CLI 根据本次真实目录映射到稳定 option ID。不能把 C 当 ID，也不能凭记忆套旧目录。
- 逐空题：`blanks:[{blank_id,answer_text,answer_state:"answered"或"unanswered"}]`，必须覆盖真实 blank_ids 的全部空位；不能用合并全文或逗号切分猜逐空答案。
- 主观题：`answer_text`，仅填原卷证据支持的实际作答。

该命令仅支持单个互动元素；复杂或不支持的结构按真实页面/接口处理，不改题型绕过。它先校验整计划的源、版本、题目和证据字段，再顺序 PATCH `response_only:true`，保持教师判定；新的 review_token 仅在内存中随服务端响应传递，不写计划或日志。客户端确认标记不替代真实审卷。

失败后先用 evidence 回读实际已保存范围与当前版本，再拟剩余计划，不能原样重放全包。422 读取 detail 修正真实字段，不反复发送同一无效请求，不直接改库；该命令不提供事务或 exactly-once。修复后重新 run/check，以最新真实全批检查为准。

## 错误诊断与有限恢复

错误返回 status/method/path/message、可用的 server_code、next_action 与 retryable=false。先读原始 detail 和当前状态；retryable=false 表示不要自动重放写请求，不等于永久不可修复。

| 类别 | 下一步 |
| --- | --- |
| `invalid_json_body` | 422 原文“标准卷选择格式无效”；先核对JSON传输/序列化，使用内置脚本，不猜键名。该路由 JSON 解析失败或 body 非对象才触发，ID不存在是另一条错误，不能据此断言平台故障 |
| `validation_failed` | 按真实 detail 修正有证据的格式/字段，不盲试变体 |
| `version_conflict` | 回读当前版本、范围和实际保存内容，再判断剩余动作 |
| `login_required`、`permission_denied` | 用现有正常登录/权限流程处理；不绕过身份或改目标环境 |
| `browser_backend_unavailable` | 当前后端不可用；按 use_emit_script 提示，核实已有浏览器 evaluate 后改用脚本桥接，无此能力则用页面 |
| `invalid_api_response` | 返回不是有效业务响应；按 read_state_before_retry 先只读查当前状态，不重放写请求 |
| `contract_mismatch` | 核对真实部署响应与当前参考，必要时用页面，不猜路由或翻压缩源码 |
| `rate_limited` | 按服务端提示有界等待后只读核对，不紧循环重放写 |
| `transport_uncertain` | 请求可能已送达，先读状态与持久化结果，不能直接重发 |

## 恢复与终点

checkpoint 仅作恢复定位与有限回执，保存 origin/batch_id、题框版本/源/参考/签名/粒度目标和关联目标/版本，权限 0600。它不是服务端幂等、跨步骤事务或 exactly-once。Python/JS 拒绝不同 origin/batch；题框恢复还核对当前源 PDF、参考卷、revision、frames_signature，同 operation_id 的编辑内容变更不能复用旧回执。关联回执仅在目标列表和当前 roster 版本匹配时复用，并回读逐项实际目标。

超时、PATCH 成功但回执丢失、确认超时或顺序关联部分失败，先读取当前状态/版本与实际保存内容，再做剩余步骤；不能重发整个 shift 包。409 回读版本后重新判断，不强改 token/revision；范围确认无用户变化却再次同因 409，按主文保留证据并停止自动循环。partial/failed 只恢复失败范围，stale 先核来源，不删除用户数据重来。

最终检查必须保留整批总数、实际覆盖与未覆盖数。姓名未关联、结构不完整或媒体 pending 时保留真实 ready=false，不勾 subset 冒充全批 ready。保留教师原判与 `JUDGMENT_BINARY_MAPPING` 等真实警告，不为消警告改判。检查模式禁止 imports POST、确认同步与提交型 resume；最新全批 ready 且必要核验完成后，给真实批阅台链接、统计、warnings 和验证边界即停止，不自启全量深审。

计划、完整结果、校对图和证据只在本次受控目录使用，不写凭证或学生答案全文到交付报告。报告区分服务端并发任务时长与墙钟耗时；模型 usage 缺失就是未知，不能当零。隔离回放复用旧产物时明确“无新模型调用”，只证明该环境的编排表现，不推断新卷识别质量、真实线上全流程速度或 token 节省。
