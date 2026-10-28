# 扫描主流程接口参考

本参考核对于 2026-10-26 项目源码；不是线上版本保证。路径均相对当前批阅台 origin，包含 `/api`；前端 `api()` 源码常省略该前缀。下文 `B=/api/batches/{bid}`，`L=B/lesson-practice`。请求使用当前获授权会话，不将认证内容写入文件或输出。字段、ID 和版本从真实读取结果获得，不使用本文占位值发请求。

## 入口与读取

| 方法与路径 | 用途与关键点 |
| --- | --- |
| `GET /api/session` | 当前身份与能力（保留默认 `include_models=true`）；核对学校/教师，按实际阶段检查模型 workflows.scan/grading 或供应商 xueersi_configured/doubao_configured，详见批改参考 |
| `GET /api/classroom/login-check` | 课堂会话状态；有批阅台会话不表示课堂认证有效 |
| `GET /api/batches` 或 `/api/batch-summaries` | 发现已有本次记录；相似文件名不足以认定同一上传 |
| `GET B`、`GET B/progress` | 批次、分卷、学生与处理状态 |
| `GET B/analysis` | 完整扫描/题框/目录快照，必要时再读；轻轮询用 `?view=summary`、`/analysis/status` 或 `/analysis/version` |
| `GET B/analysis/students/{sid}` | 按学生回读分析，不每次拉取整批答案 |
| `GET B/pages/{absolute_page}?student_id={sid}` | 原卷对照；原文件绝对页号从学生 `start + 相对page` 获得 |

业务详情路由为当前 origin 的 `/exams/{bid}/analysis`，只在确认本次 bid 存在且有权访问后提供。同步后平台链接必须从同步响应取，不用此路由冒充错题本链接。

仅在需要该模型的阶段检查模型能力，非 LLM 供应商批改不套用扫描模型要求。模型检查失败先处理环境：`model_configured` 是聚合值，不能据此认定所选扫描模型可用。出现“当前模型尚未完成学校网关能力验收”等 configured=false 错误时，核查当前登录、学校及真实配置；不反复启动扫描、不伪造能力清单、不修改共享服务。已授权的本地联调可在确认缺部署配置后，复用项目已有能力验收文件（本项目已有 `backend/school_llm_capabilities.json`），按项目真实配置入口在独立端口启动隔离服务，再读 session 验证；不要复制凭证或把临时隔离服务当正式发布。

## 上传与幂等

本节 workflow_mode=scan 与参考卷启动规则针对已批教师卷。新快速/智能批改及已有 grading 记录按 [批改与续做](grading.md) 分流，不能对所有上传强制 scan，也不能把后续整理与重新批改混同。

`POST /api/batches` 使用 multipart/form-data，文件字段 `file` 为 PDF；设置固定 `Idempotency-Key` 请求头。

| 字段 | 要求 |
| --- | --- |
| `workflow_mode` | `scan`；默认是 `grading`，必须显式传入 |
| `pages_per_paper` | 实际每份 PDF 页数，整数 1–12 |
| `paper_size`、`orientation` | 按原卷传 `A4`/`A3`、`portrait`/`landscape` |
| `paper_sides` | `single`/`double`，double 要求每份 PDF 页数为偶数；不是自动补空白页 |
| `scan_fast` | 布尔，当前默认 true；按当前产品设置使用，不将快速模式解释为免验收 |
| `llm_model` | 用当前允许的配置；源码默认 `qwen3.8-max`，不强行覆盖线上有效配置 |

扫描模式服务端将 grading_engine 设为 llm、has_answer_paper 设为 false，不要求最前面放答案卷。PDF 上限 100 MB、600 页，总页数须能按每份页数整除。不同每份页数应先分离成明确的输入，不静默删页或补齐。

上传响应回读 `id`、`workflow_mode`、`pages_per_paper`、`total_pages` 和 `students` 确认分卷。上传发生超时：先 `GET /api/uploads/{key}`，其状态为 `completed`（含 batch_id）、`not_found` 或 `deleted`。已有 batch 直接继续；not_found 时先排查尚在途请求，再用同一文件、设置和原 key 恢复重传。deleted 不自动重建。相同 key 携带改变的文件或分卷会 409；不能为避冲突自动换 key。幂等指纹包含 PDF hash、分卷、纸张、方向、引擎、答案卷、模型、workflow 及适用的单双面/快速模式设置。

## 课程、名单与启动

1. 读取 `/api/classroom/classes`、`/api/classroom/classes/{class_id}/students` 或 `/api/classroom/general-options`；具体查询条件以当前页面请求或接口 schema 发现，不能编造学期/班级 ID。
2. `GET B/roster` 得到当前 revision。`PUT B/roster` body：`revision`、`semester_id`、`class_ids`（1–50 个真实 ID）、`scope`。scope 为 `{source:'teaching'|'general', grade, subject_id, course_id}`；general 来源需要年级、学科和课程，teaching 可用当前合法教学目录。服务端验证学期与权限。
3. `PATCH B/roster/{paper_id}` body：`{revision,student_id}`，解除关联为 null；每次读取返回的新 roster revision。扫描学生 ID/试卷 ID 与课堂学生 ID 不能混用。
只有姓名/身份已取得明确证据且需要修复时使用以下接口；姓名模糊或未识别默认暂留，不为填齐名单反复 OCR、追问或猜人。身份姓名与关联一起修复时，先 `GET B` 取对应 `students[].revision`，再 `GET B/roster` 取实时 roster revision；`analysis.students` 不提供身份编辑所需 revision。`PATCH B/students/{sid}?include_roster=true` body 使用 `{identity_only:true,revision:试卷当前revision,name:经核验的姓名,name_confirmed:true,results:[],roster_revision:实时名单revision,roster_student_id:精确课堂学生id}`。roster_revision 与 roster_student_id 必须同时提供；扫描模式不能使用该接口改批改结果。成功响应含保存后的 student 与 roster，后续操作采用新的版本并回读确认真实 student_id 关联；多份顺序保存，不能并发复用同一个名单版本。422 必须读取 detail 并修正必填字段或格式，409 回读版本；HTTP 返回、显示名变化或本地表单更新本身不证明关联持久化成功。身份修复须有明确卷面与真实名单证据；模糊姓名不继续追加识别，保留未确认/未关联，集中报告份号、原 PDF 页码区间、实际可见特征与业务定位，疑似局部文字只标疑似，不凭剩余名单猜测。

4. 初次参考卷按主文规则，从本批前几份 `students` 的少量同卷候选中优先选正确率较高的合格卷；快速批改已有全批真实可靠正确率时，直接选现成结果中的合格最高者；无全批现成正确率时，仅在前几份候选中轻量比较选最高，不为选卷另行识别全批。并列以清晰完整或靠前优先。先预览确认清晰、完整、题序版式一致；最高者不合格则用合格最高者并说明。可靠既有正确率可直接用，无则仅粗比可辨教师批注并标明估计，不把未批当正确，不为比较先识别/重批全批。不能把课堂 student_id 当试卷 id；用户快速批改术语与 `scan_fast` 是否同义，先核实当前平台实际模式，不据此改成普通 grading。`POST B/analysis` 必须发送 JSON body `{reference_student_id: 所选本批真实学生卷id}` 触发预切，之后轮询；未有 draft 且未保存参考卷时空 body 会 409“请先选择标准卷，再开始预切”。已有任务先读状态并沿用当前 reference_student_id，不重复启动或仅因发现更高正确率而换参考卷、重开全批；用户明确要求更换时，通过当前参考卷入口按真实契约与影响处理。`status`、`stage`、`scan_phase` 来自真实响应；常见 `awaiting_frames` → `frames_confirmed`/整理中 → `awaiting_confirmation` → `catalog_confirmed`/学生处理中 → `completed` 或 `partial`，自动流程可能跳过部分等待阶段。部分完成不等于全员完成，结合学生状态、issues 和 stale 验证。

## 题框与标准目录

题框保存：`PATCH B/analysis/frames`：

```json
{
  "frame_revision": "读取的当前值",
  "frames": [
    {"id":"q3_1","label":"三(1)","parent_id":null,"regions":[{"page":0,"bbox":[0.1,0.2,0.4,0.35]}],"source":"manual"}
  ],
  "checked_pages": [],
  "current_page": 0
}
```

这是结构示意，坐标必须来自本次原卷，`frames` 是完整替换集合，不能只发送一项而误删其余框。`page` 是每份卷内 0-based 页码，bbox 是 0–1 归一化坐标。内部 id 仅字母、数字、下划线、连字符；显示题号放 label。父框 ID 放 parent_id；独立计算题不得因此生成业务组合题，详见拆题参考。

改框会换 `frame_revision` 并可能清除受影响页的 checked 标记；使用保存响应的新版本。`POST B/analysis/frames/confirm` body `{frame_revision}` 确认并启动整理。只在 `awaiting_frames` 可直接改框；冻结后用页面“返回修改题框”或 `POST .../frames/reopen` 并传当前 frame_revision。其他已核查 action 有 relocate、cancel、reference、retry、retry-precut、retry-catalog；不同 action 所需参数不同，不作为通用重试接口盲用。`retry-precut` 需要当前 frame_revision 和失败相对 page。冲突可能带 `X-Error-Code: frame_version_conflict`，必须回读再编辑。

待确认标准目录：`PATCH B/analysis/catalog` body `{frame_revision,catalog_revision,questions}`。questions 保留真实完整对象与稳定 id、来源、内容 schema、媒体及几何，不凭题干文本重造整套字段；编辑器结构复杂时用当前页面“拆开组合题”“编辑内容”完成。每次保存都会产生新的 catalog_revision。

**新版确认范围**：若批次 `analysis_confirmation_version == 2`，`POST B/analysis/confirm` 被拒绝；按真实页面使用：

1. `POST B/merge-preflight`，body `{source_ids:[],frame_revision,catalog_revision}`。默认只当前记录，不添加其他历史记录。返回 operation_id、preflight_token、versions、duplicates 等。
2. 核对当前范围；若返回重复学生必须依据真实卷确认采用哪份，不能默认任选。
3. `POST B/analysis/confirm-and-start`，body 包含最新 `{frame_revision,catalog_revision,questions,preflight_token,source_versions,duplicate_choices,same_paper_confirmed,name,name_revision,idempotency_key}`。`source_versions` 使用预检返回 versions；默认不合并其他记录时 source_ids 空，duplicate_choices 按真实结果填写（无重复为空对象），same_paper_confirmed 不是绕过多记录审查的开关；name/name_revision 来自本次批次。固定 idempotency_key 属于这一次范围确认。
4. 返回 accepted 后读取 `/api/merge-operations/{operation_id}` 与批次分析状态，不能把 accepted 当学生处理已完成。超时回读原操作与批次，避免另建确认操作。 若 confirm-and-start 返回来源/题目/学生关联变化的 409，先回读当前批次、目录、roster 和预检版本，正常重新预检一次；无用户修改仍连续同因失败时，对比确认请求前后版本，判断是否由请求自身触发变化。记录当前环境、batch、阶段、版本差异与未提交状态后报告服务阻断，停止自动预检循环；不能篡改 source_versions/preflight_token 或服务端记录、回退旧 confirm、删数据重建以求通过。该判断依赖当次证据，不预设任何环境永久存在某个缺陷。

旧流程仅在真实版本允许时使用 `POST B/analysis/confirm`，body 含 `{frame_revision,catalog_revision,questions}`；不据此替代新版范围流程。已完成分析的目录编辑还可能要求 `review_token`，使用当前页面或运行时契约，不拿初次待确认目录接口强改历史结果。

## 学生结果与复核

`POST B/scan/students/{sid}/retry` 重试单份，`POST B/scan/retry-failed` 重试失败范围；请求字段按当前响应/页面核实。`PATCH B/scan/students/{sid}/questions/{qid}` 与其 `/regions` 路径存在，但参数需从当前前端请求/schema 读取，尤其版本与定位字段，不能假设只传 verdict 即可。必要时浏览器逐项修正。不要通过删除学生规避同步阻塞。

## 首轮检查交付与增量复核

优先统计准确、再题目准确、最后图片位置。首轮全批程序聚合核验结果覆盖、人数/份数/叶题数、重复遗漏、学生关联、各 verdict 与 uncertain 数量；严格核对实际标准题来源的题干算式/上下文/批改归属：统一 organizer 对照代表卷参考图，LLM legacy 对照现有标准题来源/答案卷，不强造参考卷参数。学生个人图以证据风险抽查为主，实际影响判定或统计的截断/串题须修；无影响的留白和轻微边界偏移不默认修复。

必要核验与已知实质错误处理后跑真实完整 preflight；有新实质修复则重新检查，默认检查模式最新 ready=true 后立即交付首轮批阅台链接并停止；显式同步模式继续已授权同步并交付真实链接，两种模式都不继续自动逐人逐题看图、全量重识别或微调 region。给出统计、未定、warnings、已做/未做的验证，区分统计完整一致与判定全量准确，并可选询问是否继续全量准确性检查与修复；首轮不等待该选择才交付。

后续仅按用户选择的范围深审统计/题目，个人图精修末优先。先读 progress/status/version，只有变化和具体问题才拉对应学生/题目；同一 batch 只更新受影响范围，重新准备所需媒体与检查。无新变化不重复验证，避免完整 payload 循环读取与无依据全量重跑。不承诺固定处理时长，只报告真实阶段进度。

## 同步准备、检查与提交

默认执行至最新同步检查 `ready=true` 并返回批阅台链接；普通“上传/传一下/处理一下”不授权提交，也不需再次询问终点。只有本次明确要求同步课堂、导入错题本或同步好才进入下述提交步骤；历史上传约定不能覆盖此默认。

配置与检查、提交分开：`progress/start` 和 `preflight` **不**等同于平台导入；检查模式可用它们完成检查，但禁止 imports 的 POST 和可能继续提交的 resume。

1. `GET L/config` 返回包裹对象：`{config,source_version,questions,selection_context,...}`，先取 `cfg=response.config`，当前 revision 在 `cfg.revision`，不是响应顶层。完整响应含 questions 等题目内容，只提取必要配置、版本与聚合计数，避免原样打印学生题目/答案。`GET /api/lesson-practice/options?grade_id=...&subject_id=...&batch_id=...` 获取可选真实目录；课程可用 `/api/lesson-practice/courses?grade_id=...&subject_id=...`。未选 ID 则按当前页面逐级选择，不硬编码目录。
2. `PUT L/config` 的严格 body：`revision`、`grade_id`、`subject_id`、`semester_id`、`course_id`（可空串）、`type_mapping`、`class_mapping`、`selected_paper_ids`（可 null，具体默认范围由服务端核验）。ID 为真实正整数字符串；字段不接收随意 extras。type_mapping 键是标准卷真实 question id，class_mapping 键是本批 paper id，值来自允许目录。PUT 的成功响应直接是配置对象 cfg，采用 `cfg.revision`；它与 GET 的包裹结构不同。不能漏传已有映射而清空它。同步范围应覆盖本次已授权卷，不能为检查通过静默排除失败项。
3. 可 `POST L/progress/start` body `{revision}` 启动异步准备，然后 `GET L/progress`；返回 preparation、attempt、reusable、current。preparation 的 running/preparing/paused/blocked/awaiting_confirmation 是准备状态，不是同步成功。媒体单独需要时用 `POST L/prepare-media`、`GET L/media-preparation`；不要绕过媒体检查。 返回 `MEDIA_STORAGE_NOT_CONFIGURED` 且 `retryable=false`、`recovery_action=configure_storage` 时是环境配置阻塞，不是适合不断重试的临时失败；核实当前真实部署的存储要求和现有配置，不能把“已有配置文件”当成存储已启用或媒体已验证。当前平台已配置、既定流程中的媒体准备和上传也属于本次已授权上传/检查目标的必要步骤，默认检查模式直接执行，不需另有实际同步授权，不因媒体涉及外部存储就一律再问；这不包含新增外部公开范围。正常已授权的同步流程不新增逐步确认；只有修复会改变外部公开范围、超出现有授权或自动审批明确拒绝时，保留当前检查与恢复点，报告具体未接通项和审批拒绝原因，停止被拒绝的操作，不改公开权限、不转用其他公开上传通道规避，也不伪造 ready。
4. `POST L/preflight` body `{revision,allow_pending_formula_protocol:false}`，返回 `ready,status,issues,counts,check_token,source_version` 等。姓名未关联时也执行实际检查并记录返回结果；若为 blocker，报告检查未通过及未关联份数，不虚报 ready、不静默排除范围。只有 ready=true 且 status=awaiting_confirmation 说明本次检查可提交；pending/failure/blocker 都不是通过。路由会 `remember_check` 保存本次教师、revision、check_token 和 awaiting_confirmation 记录，因此不必为了生成该记录额外重复 progress/start。准备异步后重新 preflight 取得最新检查。
5. **仅同步模式**：检查授权内警告，回读 `GET L/progress` 核对 `response.preparation.teacher_id` 是本次授权教师、`response.preparation.status=awaiting_confirmation`、`response.preparation.check_token` 与最新 preflight 相符，且 `response.preparation.revision` 与最新 `cfg.revision` 一致，配置与源内容未改变。若线上版本不返回这些内部字段，不自行补造，依赖实际 preflight 的当前身份绑定与提交端权威校验，必要时用页面补核。`POST L/imports` 严格 body：

```json
{
  "revision": 0,
  "allow_pending_formula_protocol": false,
  "check_token": "最新preflight返回值",
  "confirmed_check_token": "同一最新preflight返回值",
  "accepted_warning_ids": []
}
```

示例 revision=0 不能硬编码。accepted_warning_ids 必须正好匹配最新 issues 中 `severity=warning` 的 id 集合，并经过目标内审查；无 warning 才空数组。`JUDGMENT_BINARY_MAPPING` 是半对/未作答同步为错误的兼容映射警告，本地原始判定仍保留；向用户解释映射与影响，按任务授权审查接受；若只是已知兼容映射且无新增范围/判定风险，简短告知影响后直接确认，不逐项再问。不能为了消警告把本地 partial/unanswered 改成 incorrect 或伪造其他结果。`JUDGMENT_PROVISIONAL` 则涉及 uncertain 等真正未知的判定按未确认正确入错，不能与上述 partial/unanswered 兼容映射混同；平台 ready=true/warning 不代表用户已授权这一业务处置。检查模式报告影响即可，实际同步若缺该偏好先集中询问整批待复核或允许按平台规则入错，已有明确偏好沿用，不逐题问、不静默排除范围。核心校验是 confirmed_check_token 和服务端保存的教师检查状态；仅给 check_token 不够。服务端会重新 preflight 并冻结请求，内容/媒体/配置变化会 409 `CHECK_CONFIRMATION_REQUIRED`；回读返回检查，处理变化，重新检查再决定，不能忽略 token。

特殊 `allow_pending_formula_protocol=true` 不能为“快速通过”默认启用；遇到协议未就绪先报告事实。超出平台限额会 413，不能静默拆批改变范围。

## 同步异步状态、恢复与链接

- 提交响应是 attempt，不是成功。轮询 `GET L/imports`（可 `?check_source=false` 只读原任务避免重新计算源）和 `GET L/progress`，保留 attempt id 与 import_id。常见 state：PENDING、QUEUED、VALIDATING、PREPARING_ASSETS、READY、IMPORTING、RETRY_WAIT、UNKNOWN；终态为 SUCCEEDED、REJECTED、FAILED。以 `state=SUCCEEDED` 为成功依据，prepared/READY/HTTP 200 都不算。
- 超时先读 imports，优先恢复原 attempt；同步模式需要时 `POST L/imports/{aid}/resume`。UNKNOWN、paused、unconfirmed_failures 可能表示远端已收到但尚不确定，不能改 key 或新建 batch 重投。响应存在 `next_poll_at` 时据此查询，否则约 5 秒起步并适度退避，避免忙轮询。认证失效按原任务重新授权后恢复，不扩展目标环境。
- 已 SUCCEEDED 不覆盖。REJECTED/FAILED 也不意味着可安全换新任务；先查看 errors、batch_released 及平台释放证据，说明修复和重试影响。`local_changed=true` 表示本地已变化，不代表远端已更新。
- 失败明细：`GET L/imports/{aid}/errors`（需要 import_id）；读取错误用途仅限本次处理，不将原始学生答案和认证材料导出到报告。
- 成功后 `GET L/imports/{aid}/links` 补取平台真实链接。public 响应可含 `report_url`、`mistake_book_links`（列表，各项 url）、单项时的 `mistake_book_url`。链接元数据或配置未就绪时可能无链接/失败，报告未取得，不拼接 reportId 或猜路径。优先给本次班级/学生相应错题本链接；多人多班时保留正确对应关系。
- 浏览器打开真实响应链接核对。跨平台会话不能假设自动通用；登录或权限不足应准确标“链接访问未验证”，不篡改域名使链接看似生产。
