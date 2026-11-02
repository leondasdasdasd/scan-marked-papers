# 批量 CLI 编排

本说明对应 `scripts/paperflow.py`、`paperflow.js` 与兼容 `paperflow_base.py`。实际 `workflow_mode=scan` 且具备可用浏览器 run-code 适配器时优先使用；不支持的阶段按原技能接口/页面回退。默认终点为真实全批同步检查，不提交导入；已有导入与停止标记优先只读。

## 入口与输出

Python 全局参数放在子命令前：`--base-url <已核实 origin>`、`--batch-id <本批 ID>`、`--browser-session <已登录会话>` 均必需。可选 `--wrapper`（默认 `~/.codex/skills/playwright/scripts/playwright_cli.sh`）、`--timeout`（1–180 秒，默认 45）、`--interval`（2–30 秒，默认 5）、`--checkpoint <本地 JSON>`、`--output <完整结果 JSON>` 和 `--verbose`。先核实真实身份、学校与环境；CLI 通过 wrapper 在浏览器同源 fetch，不导出凭证、不自行登录或关闭用户页面，禁止重定向。

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <真实origin> --batch-id <真实ID> --browser-session <已有会话> --checkpoint <本次检查点.json> --output <本次结果.json> run --follow --max-seconds 600
```

默认 stdout 为紧凑 JSON，省去完整 checkpoint、调用明细与大块校对几何，保留下一步所需的摘要和文件路径。全局 `--output` 保存完整结果 envelope，返回 output_file；只有诊断确实需要时用 `--verbose` 输出完整 JSON。兼容的 `snapshot --output <JSON>` 放在子命令后，只保存裸 snapshot 并返回 snapshot_file，与全局输出不同。完整结果保存在本次受控目录，按需读取字段，不整份回送模型。`--timeout` 是一次轮询预算，`run --follow --max-seconds` 是跨 waiting 的有界跟进预算，均不是服务端任务完成承诺。

所有命令的 `ok`/退出码只说明工具执行，业务完成看 `outcome`、`ready`、`submitted` 和真实覆盖。新入口没有 `upload/session/watch`；新上传、grading 与目录保存/确认仍按原技能。旧 `paperflow_base.py` 的 session/upload/check 按它自己的 help 使用，不能混用参数；旧 upload 也仅支持 scan。

| 命令 | 用途与边界 |
| --- | --- |
| `run [--plan <JSON>] [--review-pdf <PDF> --review-out <DIR>] [--follow --max-seconds 600]` | 按真实阶段推进预切、已审题框、学生处理、统计、媒体准备与预检。`--follow` 在 waiting 时继续轻量等待，到需判断、失败或终点返回，默认不持续追踪 blocked。成对提供 review 参数时，复用当前读取生成校对包，无须另做 snapshot |
| `snapshot [--output <裸snapshot JSON>]` | 读取批次与 catalog 视图，保存参考卷、源 PDF SHA、版本、完整题框和精简题目录。questions 提供正文 text、选项稳定 id/position/text、blank_ids、answers/extras，避免 html/json 重复；`reviewed=false` 不代表看过图 |
| `review --pdf <本次原PDF> --out <受控目录>` | 读取 snapshot 并严格核对 PDF SHA，生成带框全页图、contact-sheet.png 与 review.json。需 pymupdf/Pillow；生成不等于审核，缩略图不足时查看全页细节 |
| `frames --edits <JSON> [--confirm]` | 校验版本并在内存完成整包 set/shift/split/promote_children 与几何检查，最多一次 PATCH；`--confirm` 再确认题框。PATCH 与确认不是跨请求事务 |
| `associate --plan <JSON>` | 先校验整批证据与名单版本，再顺序关联、采用每次新 roster revision，末尾回读。最多 50 项；部分失败可能已保存部分，不是原子批量事务 |
| `inspect` | 聚合全批人数、叶题、作答、重复遗漏和未关联；不是视觉验收 |
| `check` | 全批检查并按真实门槛准备媒体，不修改配置或缩 scope；只在媒体 pending、无 blocker/failure、结构完整且全量覆盖、全关联时可能 start。先读 progress，真实 running 时复用等待；preparing 不一定已有活跃任务 |
| `diagnose` | 读取真实 preflight 及阻塞诊断，不启动媒体准备；不能把诊断成功当 ready |
| `retry-precut --page <0-based相对页码> --frame-revision <当前版本>` | 从 CLI 返回的 retryable_pages 中选定具体页、核实证据后只重试该页，不能自动全页重试或重传副本 |
| `evidence --paper-id <ID> [--question-id <QID> ...]` | 只读指定卷及可重复指定的题，返回版本、PDF 页码、精简目录与作答证据定位；reviewed=false，不代表已审图，不输出 review_token |
| `responses --plan <JSON>` | 对已实际审卷、有明确证据的作答结构作定点修复；整计划先本地校验，再顺序保存，仅 response_only，不改教师判定、不调用模型。失败即停，可能已保存前面部分 |
| `usage` | 读取真实模型用量；缺失 usage 保留 null，`tokens_complete=false`，不以零补齐或据此计算完整费用 |

## 按返回边界推进

先运行 `run --follow`，有已有校对包或计划时复用。确定的等待和状态读取交给 CLI，不逐轮 snapshot、截图、重读源码或临时写 fetch 脚本。只有返回包不足以作决定时，再按 [接口参考](api.md) 补最小必要读取。

| 返回边界 | 智能体下一步 |
| --- | --- |
| `needs_reference` | 按主文规则，依据真实清晰度、完整性与教师批注选本批参考卷；写 reference_student_id 后继续。工具前五份摘要仅是候选提示，不是业务范围或正确率证据 |
| `needs_precut_recovery` | 先看 diagnosis 的 code、failed_pages、issues、frame_revision、retryable_pages；空框/失败页不能当 `needs_frame_review`。只使用 CLI 返回的 retryable_pages；空框时列表可能来自已核实的每份页数，不代表各页已确认失败。选定具体页、核实证据后只重试该页，不能自动全页重试。缺配置、不可恢复或同因持续失败时报告诊断并保留恢复点，不重复空跑 |
| `needs_frame_review` | 复用 run 生成的 review 包，实际核对全部参考页，一次整理必要框修改，再应用并确认。没有包且已有本地原 PDF 时才单独 review；已有链接无本地 PDF 时按原技能读取参考页，不索要或重传原卷 |
| `needs_catalog_review` | 一次读取精简目录正文、选项 ID 与逐空定义，对照已审参考图核对内容、答案和独立题结构；按原技能真实目录保存/范围预检/确认流程推进，再 run |
| `needs_targeted_recovery`、partial/failed 或检查阻塞 | 先读具体失败与 review_tasks，以 evidence 取受影响卷/题定位，实际核对必要原卷证据；仅作答结构问题可走 responses，其他按真实恢复接口。不默认重跑全批 |
| `waiting` | 任务仍在进行；沿用原计划和 checkpoint 继续 `run --follow`，不重复启动任务 |
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

## 定点证据与作答结构修复

先用 `review_tasks` 确定卷、题，再调用 `evidence --paper-id <ID> --question-id <QID>`；多个题重复传 question-id，一次取齐。证据包包括 source_pdf_sha256/frame_revision/catalog_revision、paper_id/index/pdf_pages、精简 questions；observations 的真实字段为 question_id、verdict、answer_text、answer_state、response_conversion_status、blanks、response_regions、source_refs，其中 blanks 含 blank_id、answer_text、answer_state、verdict。按定位实际查看必要原卷或已有图证，包本身不证明已审；保留教师原批注与真实不确定状态。

`responses --plan` 根必须含当前 source_pdf_sha256、frame_revision、catalog_revision 和 1–100 个 assignments；每项含 paper_id、question_id、`evidence_confirmed:true`、非空 evidence_note，并按该题真实单一互动元素提供：

- 选择题：`selected_option_positions:[1-based位置]`。例如可见 C 对应位置 3；CLI 根据本次真实目录映射到稳定 option ID。不能把 C 当 ID，也不能凭记忆套旧目录。
- 逐空题：`blanks:[{blank_id,answer_text,answer_state:"answered"或"unanswered"}]`，必须覆盖真实 blank_ids 的全部空位；不能用合并全文或逗号切分猜逐空答案。
- 主观题：`answer_text`，仅填原卷证据支持的实际作答。

该命令仅支持单个互动元素；复杂或不支持的结构按真实页面/接口处理，不改题型绕过。它先校验整计划的源、版本、题目和证据字段，再顺序 PATCH `response_only:true`，保持教师判定；新的 review_token 仅在内存中随服务端响应传递，不写计划或日志。客户端确认标记不替代真实审卷。

失败后先用 evidence 回读实际已保存范围与当前版本，再拟剩余计划，不能原样重放全包。422 读取 detail 修正真实字段，不反复发送同一无效请求，不直接改库；该命令不提供事务或 exactly-once。修复后重新 run/check，以最新真实全批检查为准。

## 恢复与终点

checkpoint 仅作恢复定位与有限回执，保存 origin/batch_id、题框版本/源/参考/签名/粒度目标和关联目标/版本，权限 0600。它不是服务端幂等、跨步骤事务或 exactly-once。Python/JS 拒绝不同 origin/batch；题框恢复还核对当前源 PDF、参考卷、revision、frames_signature，同 operation_id 的编辑内容变更不能复用旧回执。关联回执仅在目标列表和当前 roster 版本匹配时复用，并回读逐项实际目标。

超时、PATCH 成功但回执丢失、确认超时或顺序关联部分失败，先读取当前状态/版本与实际保存内容，再做剩余步骤；不能重发整个 shift 包。409 回读版本后重新判断，不强改 token/revision；范围确认无用户变化却再次同因 409，按主文保留证据并停止自动循环。partial/failed 只恢复失败范围，stale 先核来源，不删除用户数据重来。

最终检查必须保留整批总数、实际覆盖与未覆盖数。姓名未关联、结构不完整或媒体 pending 时保留真实 ready=false，不勾 subset 冒充全批 ready。保留教师原判与 `JUDGMENT_BINARY_MAPPING` 等真实警告，不为消警告改判。检查模式禁止 imports POST、确认同步与提交型 resume；最新全批 ready 且必要核验完成后，给真实批阅台链接、统计、warnings 和验证边界即停止，不自启全量深审。

计划、完整结果、校对图和证据只在本次受控目录使用，不写凭证或学生答案全文到交付报告。报告区分服务端并发任务时长与墙钟耗时；模型 usage 缺失就是未知，不能当零。隔离回放复用旧产物时明确“无新模型调用”，只证明该环境的编排表现，不推断新卷识别质量、真实线上全流程速度或 token 节省。
