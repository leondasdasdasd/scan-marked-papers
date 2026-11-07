# 全流程接口功能与契约

本接口契约对照实际 `backend/app.py`、`read_routes.py`、`roster_routes.py`、`analysis_trigger.py`、`batch_merge_routes.py`、`lesson_practice_routes.py` 及前端真实调用，核对 `scripts/api_contracts.json` 的83项受限操作。源码/registry不是线上可用性保证；执行以当前部署真实响应为准，不为适配去猜字段或改业务模式。

B 表示 `/api/batches/{bid}`，L 表示 `B/lesson-practice`。正常流程用 [CLI](cli.md) 专用命令与run编排；本参考供 `api-list --operation <名称>` 后查具体功能，用 `api-call --operation <名称> --plan <受控JSON>` 补已登记步骤。operation只允许registry路径，不是任意HTTP客户端。页面仅用于登录、确需文件注入、必要图证及有明确不兼容证据的缺口。

路径中的bid默认取本次批次，其余params均来自真实读取。查询字段放plan.query，JSON字段放plan.body；下表“必填”是CLI登记的最低字段，不能据此删掉服务端当前对象的其他必要内容。所有写计划须有本次真实 `evidence_confirmed:true`、非空evidence_note和适用的expected版本；GET不要求证据标记。标记本身不证明审图。review_token、任务控制token、范围预检token和检查token仅运行时内存使用，不放计划、日志、checkpoint或交付。special=upload/catalog/sync走对应专用命令，普通api-call不绕过。

artifact项是文件/图片入口，按真实工具取必要图证或下载；不把文件当JSON、不把取得URL当实际看过图。普通请求保持当前授权同源会话，不导出Cookie、令牌或storage state；独立会话接入仅走 [CLI](cli.md) 的受控内存迁移，不在API计划、聊天或文件中传凭证。以下逐项列明功能、字段和前置条件；完整版本和恢复约束在后文。


## 身份、课程与名单目录

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `session` | `GET /api/session` | 读取当前批阅台身份、学校、供应商配置及按需模型能力。 | query：`refresh_profile`, `include_models`。 常规access用refresh_profile=false、include_models=false；仅所需模型阶段读取完整能力。 |
| `login-check` | `GET /api/classroom/login-check` | 核验批阅台、云谷与课堂会话及账号一致性，不返回凭证。 | HTTP200也要读业务状态码/错误类型；不得导出会话。 |
| `classes` | `GET /api/classroom/classes` | 读取当前教师可用的教学课程、学期与班级目录。 | 仅教学目录；不是当前批次选班保存。 |
| `general-options` | `GET /api/classroom/general-options` | 按年级、学科、课程逐级读取通用教学目录与允许班级。 | query：`grade`, `subject_id`, `course_id`。 按grade→subject_id→course_id逐级选择，不硬编码ID。 |
| `class-students` | `GET /api/classroom/classes/{class_id}/students` | 只读预览指定允许班级的当前学生名单，不写批次关联。 | query：`source`, `grade`, `subject_id`, `course_id`。 class_id必须来自当前允许目录，scope查询须与选课一致。 |
| `recent-selection` | `GET /api/classroom/recent-selection` | 读取并重新验证最近一次课程班级选择，返回有效选择或失效原因。 | 仅valid且当前权限仍通过可复用；多候选不擅选。 |
| `recent-classes` | `GET /api/classroom/recent-classes` | 读取最近使用的课程班级记录及选择上下文，不代替当前权限校验。 | 只作历史定位，不能当身份证据或当前权限。 |

## 上传、记录与任务状态

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `batch-list` | `GET /api/batch-summaries` | 按权限、时间、模式和课程班级筛选分页查找已有批改记录。 | query：`limit`, `cursor`, `scope`, `page`, `mode`, `semester_id`, `class_id`, `period`, `date_start`, `date_end`, `grade`, `subject_id`, `course_id`。 semester_id/class_id须同时给；page与cursor互斥；自定义时间才给date_start/date_end。 |
| `upload-status` | `GET /api/uploads/{key}` | 按原幂等键查上传是否已形成批次，用于超时恢复。 | 沿用本次固定key；completed续原batch，deleted不自动重建。 |
| `upload` | `POST /api/batches` | 以FormData上传PDF并按指定模式和每份页数创建批次。 | 专用upload；file+pages_per_paper，模式/答案卷/纸张参数见下文，Idempotency-Key固定。 |
| `batch` | `GET B` | 读取本次批次、学生卷、原模式、分卷与版本等元数据。 | 确认真实workflow/engine、source PDF和学生总数，不能从analysis.students反推分卷。 |
| `live-state` | `GET B/live-state` | 合并读取批改进度、任务控制、分析版本与分析状态。 | 首选合并轻读；403/404不绕过，活跃任务不另启。 |
| `progress` | `GET B/progress` | 轻量读取本次批改与学生进度，供有界等待。 | 只读已有进度，不把HTTP200当完成。 |
| `task-control` | `GET B/task-control` | 读取批改和分析任务状态、停止能力与运行时控制令牌。 | token仅运行时用；停止/恢复服从用户本次目标。 |
| `diagnostics` | `GET B/diagnostics` | 读取批次的诊断与异常定位信息，不重跑任务。 | query：`before`、`limit`；仅限本批，报告提取必要诊断，不输出完整敏感payload。 |
| `model-usage` | `GET B/model-usage` | 读取已有模型调用与用量记录，缺失用量保持未知。 | 缺usage为null/未知，不补零或推算线上性能。 |
| `roster` | `GET B/roster` | 读取批次课程班级、当前名单、卷与学生关联及revision。 | assignment与卷面姓名分开核对；一次对账足够时不重复读。 |
| `scope-save` | `PUT B/roster` | 按当前revision保存本次课程、班级和名单范围。 | body必填：`revision`, `semester_id`, `class_ids`, `scope`。 仅空闲批次；general须grade/subject_id/course_id；已录入班级不能擅换。 |
| `associate` | `PATCH B/roster/{paper_id}` | 将一份试卷关联到已核实学生，或显式解除关联。 | body必填：`revision`, `student_id`。 清楚卷面+真实名单证据；student_id可null，逐次采用新revision。 |
| `student` | `GET B/students/{sid}` | 读取一份原批改学生卷与结果，不拉全部供应商明细。 | 读取学生当前revision；保留人工结果，不默认重试。 |
| `provider-results` | `GET B/students/{sid}/provider-results` | 读取一份供应商批改原始明细，供定点复核。 | 只在具体问题需要时读取，保留供应商原批改来源。 |

## 原始批改与答案模板

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `grading-start` | `POST B/start` | 校验名单与能力后启动或接续缺失的原始批改。 | 无body；先有课程/名单及所选引擎能力；accepted后仍观察原任务。 |
| `answers-extract` | `POST B/answers/extract` | 仅智能批改读取前置答案卷，完成后供核对模板。 | 无body；仅LLM+前置答案卷，无活跃任务，完成不等于学生批改完成。 |
| `grading-retry` | `POST B/students/{sid}/retry` | 重试指定学生的原始批改，可能覆盖其已有批改。 | 无body；仅失败/缺失范围；done卷可能被重批，不清人工保护绕过。 |
| `task-stop` | `POST B/stop` | 请求停止指定批改或分析任务并持久化当前结果。 | body必填：`kind`。 kind=grading或analysis；控制token运行时取得，不写计划。 |
| `layout-save` | `PATCH B/layout` | 按layout revision仅调整答案模板几何位置，保留题干与空结构。 | body必填：`revision`, `questions`。 仅几何page/x/y/answer_regions/blank_anchors；questions为完整当前数组，不能改题干/答案/空结构。 |
| `student-save` | `PATCH B/students/{sid}` | 按学生revision修正身份，或在允许的grading模式保存原始结果。 | body必填：`revision`, `identity_only`, `name`, `name_confirmed`。 query：`include_roster`。 身份修复用identity_only=true、results=[]；原结果编辑仅grading且保留完整results/judgments；关联须同时给roster_revision/roster_student_id。 |

## 整理、题框与目录

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `analysis` | `GET B/analysis` | 按视图读取标准目录、题框、学生整理与分析版本。 | query：`view`, `include_student`, `include_first_student`。 优先summary/catalog等必要视图；只按变化拉全量，review_token不保存输出。 |
| `analysis-version` | `GET B/analysis/version` | 轻量读取分析版本，判断是否需要刷新内容。 | 版本未变不反复读取完整snapshot。 |
| `analysis-status` | `GET B/analysis/status` | 轻量读取分析阶段、任务和学生处理状态。 | 正常running进度暂不变按预算等，不据此判失败。 |
| `analysis-student` | `GET B/analysis/students/{sid}` | 按学生读取整理结果与作答，不拉全批答案。 | sid为本批学生卷ID，不是课堂学生ID。 |
| `analysis-start` | `POST B/analysis` | 对scan或供应商批改选择参考卷并启动统一整理。 | body必填：`reference_student_id`。 仅organizer：scan或已完成全批供应商批改；沿用既有参考卷，LLM不走此入口。 |
| `reference-answers-resume` | `POST B/analysis` | 按真实恢复阶段接续已整理记录的参考答案补齐。 | body必填：`resume_reference_answers`。 resume_reference_answers=true；仅真实参考答案恢复阶段，不是通用resume。 |
| `prepare-analysis` | `POST L/prepare-analysis` | 按当前配置准备LLM批改后的分析，并复用有效快照。 | 无body；LLM整理入口，不传reference_student_id；会按关联/配置筛选，须另验全批覆盖。 |
| `analysis-retry-incomplete` | `POST B/analysis/retry-incomplete` | 仅重试非scan整理中页面失败的学生，保留成功页面。 | 无body；非scan、completed/partial且非stale，须有page_errors；不是原始批改重试。 |
| `analysis-mode` | `PATCH B/analysis/mode` | 切换供应商批改后的整理快慢设置并使旧整理失效。 | body必填：`analysis_fast`。 仅供应商grading；会清准备缓存并使分析失效，不是恢复按钮，不擅切。 |
| `catalog-save-draft` | `PATCH B/analysis/catalog` | 按题框和目录revision保存待确认标准题完整目录。 | body必填：`frame_revision`, `catalog_revision`, `questions`。 query：`view`。 仅待确认目录；questions保留完整真实对象、稳定ID、媒体及几何。 |
| `catalog-save-review` | `PATCH B/analysis/catalog` | 按运行时review token保存已整理标准题完整目录。 | body必填：`questions`。 query：`view`。 仅completed/partial且非stale；review_token运行时注入，questions为完整当前目录。 |
| `question-types` | `POST B/analysis/question-types` | 将已有标准题目录升级到当前业务题型契约。 | 现有目录升级业务题型；不是新建题干/答案或自动重识别。 |
| `frames-save` | `PATCH B/analysis/frames` | 在题框待核阶段按revision完整保存题框集合和已核页。 | body必填：`frame_revision`, `frames`, `checked_pages`, `current_page`。 仅awaiting_frames；frames为完整替换集合，不能只传一框删其他。 |
| `frames-crop` | `POST B/analysis/frames/crop` | 调整已有参考题裁图位置，保留题目身份与教师判定。 | body必填：`frame_revision`, `catalog_revision`, `revision`, `frames`。 已有题裁图；最新预切还核对分析revision，不得新增/删题/合题或改判。 |
| `frames-relocate` | `POST B/analysis/frames/relocate` | 重新定位参考卷题框，保留上次结果供恢复。 | body必填：`frame_revision`。 仅可改框阶段；涉及重新定位/模型，须有本次必要性证据。 |
| `frames-confirm` | `POST B/analysis/frames/confirm` | 确认已审题框并启动后续目录整理，不提交课堂。 | body必填：`frame_revision`。 实际审完全部参考页；失败/空框不可确认，无改动可零PATCH。 |
| `frames-cancel` | `POST B/analysis/frames/cancel` | 取消可选的返回改框，恢复此前已保存整理结果。 | body必填：`frame_revision`。 必须有可恢复的已保存结果；保留用户当前修改意图。 |
| `frames-reopen` | `POST B/analysis/frames/reopen` | 返回题框调整并保留原结果，产生新题框版本。 | body必填：`frame_revision`。 只为必要改框；读取新frame_revision，旧审查标记不得沿用。 |
| `frames-reference` | `POST B/analysis/frames/reference` | 明确更换参考学生卷并重新定位题框。 | body必填：`frame_revision`, `reference_student_id`。 仅用户本次明确要求换卷且已知影响；不为追更高正确率重开。 |
| `frames-retry` | `POST B/analysis/frames/retry` | 按当前题框与目录版本重识别指定单题区域。 | body必填：`frame_revision`, `catalog_revision`, `question_id`, `regions`。 仅已核实的一题；使用当前regions和catalog_revision，保留其他题。 |
| `frames-retry-precut` | `POST B/analysis/frames/retry-precut` | 仅重试已定位的一个相对页预切。 | body必填：`frame_revision`, `page`。 page为0-based相对页；只按retryable_pages证据定点重试。 |
| `frames-retry-catalog` | `POST B/analysis/frames/retry-catalog` | 按当前题框重新整理参考目录，可能重新调用模型。 | body必填：`frame_revision`。 仅具体目录失败需重建时用；不为补姓名或无变化反复重识别。 |
| `catalog-confirm` | `POST B/analysis/confirm` | 旧版目录确认入口，仅在真实记录允许时使用。 | body必填：`frame_revision`, `catalog_revision`, `questions`。 special=catalog，用catalog编排；analysis_confirmation_version=2禁止旧确认。 |
| `scope-preflight` | `POST B/merge-preflight` | 预检当前记录的目录、来源版本与重复学生卷范围。 | body必填：`source_ids`, `frame_revision`, `catalog_revision`。 special=catalog，用catalog编排；默认source_ids=[]，不擅合历史记录。 |
| `catalog-confirm-and-start` | `POST B/analysis/confirm-and-start` | 用最新范围预检确认已审目录并启动学生整理，不提交课堂。 | special=catalog，用catalog编排；预检token/source_versions运行时持有，重复卷未决定不确认。 |
| `merge-operation` | `GET /api/merge-operations/{operation_id}` | 读取原范围确认操作的受理、持久化与学生处理状态。 | 确认超时先读原operation_id，不换operation_id/幂等键重发。 |

## 学生复核与定点恢复

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `question-review` | `PATCH B/analysis/students/{sid}/questions/{qid}` | 按运行时review token定点修正判定或学生作答结构。 | review_token运行时注入；判定verdict_only或作答response_only按真实目标选，逐空用真实blank_id/source_ref。 |
| `review-results` | `PATCH B/students/{sid}/review-results` | 按运行时review token保存已复核结果的分数、评语与批注位置。 | body必填：`results`。 results项含question_id、score(可null)、reason、page/x/y及必要blank_positions/hidden_mark_ids；不回灌旧编辑器。 |
| `analysis-reconcile` | `POST B/analysis/reconcile` | 按运行时review token检查并恢复分析投影一致性。 | review_token运行时注入；retry仅明确诊断需要时给true，不作为全批重跑。 |
| `scan-retry` | `POST B/scan/students/{sid}/retry` | 仅重试统一整理中指定学生卷，保留其他学生结果。 | organizer适用（含供应商整理），无body；仅具体失败卷，不重批原始供应商结果。 |
| `scan-retry-failed` | `POST B/scan/retry-failed` | 仅重试统一整理中失败的学生范围。 | organizer适用，无body；仅失败范围，不重跑全批或已人工修正项。 |
| `scan-result-save` | `PATCH B/scan/students/{sid}/questions/{qid}` | 按扫描结果revision保存已核实的单题教师判定。 | body必填：`revision`, `verdict`。 仅scan已完成非stale结果；verdict须有教师原批注证据，可给note，不为消警告改判。 |
| `response-regions-save` | `PATCH B/scan/students/{sid}/questions/{qid}/regions` | 按分析revision调整一名学生的一道题作答裁图区域。 | body必填：`revision`, `regions`。 organizer适用；revision为当前分析revision，regions为真实归一化题区，改后媒体/检查失效。 |

## 同步配置、校对与检查

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `sync-options` | `GET /api/lesson-practice/options` | 读取当前课程班级范围允许的同步目录和业务题型。 | query：`grade_id`, `subject_id`, `course_id`, `batch_id`。 只用允许的目录；subject_id须先有grade_id，batch_id限定本批范围。 |
| `sync-courses` | `GET /api/lesson-practice/courses` | 按真实年级与学科读取可用同步课程。 | query：`grade_id`, `subject_id`。 grade_id、subject_id为必需查询，真实正整数ID。 |
| `sync-config` | `GET L/config` | 读取同步配置、来源版本、标准题与选择上下文。 | query：`view`。 view=full或scope；配置在response.config，revision不在顶层。 |
| `sync-config-save` | `PUT L/config` | 按revision保存真实目录映射与本批全量同步范围。 | body必填：`revision`, `grade_id`, `subject_id`, `course_id`, `semester_id`, `type_mapping`, `class_mapping`, `selected_paper_ids`。 保留原映射与全批selected_paper_ids；PUT直接返回cfg及新revision，不排除未关联求通过。 |
| `correction-item` | `GET L/corrections/item` | 读取指定卷题的同步校对详情、来源与当前版本。 | query：`paper_id`, `question_id`。 paper_id、question_id为必需查询；先读最新source_version/revision。 |
| `correction-save` | `PATCH L/corrections/item` | 按配置revision与source version保存单题同步校对内容。 | body必填：`revision`, `source_version`, `question_id`。 校对真实content/element_answers/answer_text/blanks/verdict/use_image；只改有证据字段，保存后回读。 |
| `correction-bulk-verdict` | `PATCH L/corrections/bulk-verdict` | 按版本与明确目标批量保存已核实判定，不自动消除未知。 | body必填：`revision`, `source_version`, `targets`, `verdict`, `confirmed`。 targets明确paper_id/question_id；confirmed=true只是客户端标记，仍须真实逐项证据。 |
| `preflight` | `POST L/preflight` | 执行真实同步检查并保存当前教师检查状态，不提交课堂。 | body必填：`revision`。 allow_pending_formula_protocol默认false；记录真实check但raw ready可能是subset，整体看CLI completion/remaining。 |
| `prepare-media` | `POST L/prepare-media` | 启动或复用本批既定同步媒体准备，不提交课堂。 | 无body；按CLI全量/关联/无hardblock门槛启动，已running复用等待。 |
| `media-status` | `GET L/media-preparation` | 读取当前媒体准备进度、错误与可恢复状态。 | pending不是完成；不可恢复配置错误不循环重试。 |
| `sync-progress` | `GET L/progress` | 读取当前准备任务与已有导入任务，不提交或恢复导入。 | 准备状态与attempt分开；awaiting_confirmation仍未导入。 |
| `sync-prepare` | `POST L/progress/start` | 启动或复用同步前异步准备，最终仍需真实检查。 | body必填：`revision`。 revision为当前cfg版本；准备不是提交，不额外重复生成已有检查记录。 |

## 已授权导入与结果

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `imports` | `GET L/imports` | 读取已有课堂导入任务及可选的来源变化状态。 | query：`check_source`。 check_source=false只读原任务以减少重复源计算，UNKNOWN先读原attempt。 |
| `import-submit` | `POST L/imports` | 仅在本次明确授权同步后用最新检查提交课堂导入。 | special=sync，仅sync --plan --authorize-sync；最新检查与真实warning集合、教师确认和范围仍由服务端权威校验。 |
| `import-resume` | `POST L/imports/{aid}/resume` | 仅在本次明确授权同步后接续原导入任务，不新建重投。 | special=sync，仅专用sync且明确本次授权；无body，接续原aid，不新建任务。 |
| `import-errors` | `GET L/imports/{aid}/errors` | 读取原导入任务的真实失败明细。 | 按本批原aid读取；只交付必要错误，不导出学生答案和认证材料。 |
| `import-links` | `GET L/imports/{aid}/links` | 从成功导入任务取得真实报告与错题本链接。 | 从原成功attempt取report_url/mistake_book_links；无链接就报告未取得，不猜路径。 |

## 必要图证与导出

| 操作名 | 方法与路径 | 功能 | 关键字段与前置条件 |
| --- | --- | --- | --- |
| `original` | `GET B/original` | 取得本批原始PDF文件地址供受控下载或必要审图。 | artifact入口；只在本次受控范围查看/下载，不把文件响应当JSON。 |
| `page-image` | `GET B/pages/{page}` | 取得指定原PDF绝对页的原图或供应商矫正卷图。 | query：`thumbnail`, `student_id`, `source_revision`, `original`。 page为原PDF绝对0-based页；student_id与页归属一致，doubao按source_revision核对，original=true取原卷。 |
| `question-image` | `GET B/analysis/question-images/{asset}` | 取得服务端已生成的标准题图片。 | asset取本次真实snapshot，不能猜哈希或题图路径。 |
| `answer-image` | `GET L/answer-images/{paper_id}/{qid}/{index}` | 取得指定学生卷题的已准备作答裁图。 | paper_id/qid/index取真实校对结果，只查看必要图证。 |
| `analysis-export` | `GET B/analysis/export` | 导出当前有效整理结果JSON，不提交课堂。 | 需completed/partial且非stale；仅受控导出，不把JSON导出当视觉验收。 |
| `scan-export` | `GET B/scan/export.xlsx` | 导出当前有效扫描结果工作簿，可按真实班级筛选。 | query：`class_id`。 仅scan，completed/partial且非stale；class_id仅筛已有授权班级，不改变检查范围。 |

## 执行细节与恢复

## 入口与读取

| 方法与路径 | 用途与关键点 |
| --- | --- |
| `GET /api/session` | 常规access取最小身份，不读取模型能力；所需阶段再取include_models=true核实workflows.scan/grading或供应商配置，详见批改参考 |
| `GET /api/classroom/login-check` | 课堂会话状态；有批阅台会话不表示课堂认证有效 |
| `GET /api/batches` 或 `/api/batch-summaries` | 发现已有本次记录；相似文件名不足以认定同一上传 |
| `GET B`、`GET B/progress` | 批次、分卷、学生与处理状态 |
| `GET B/analysis` | 完整扫描/题框/目录快照，必要时再读；轻轮询用 `?view=summary`、`/analysis/status` 或 `/analysis/version` |
| `GET B/analysis/students/{sid}` | 按学生回读分析，不每次拉取整批答案 |
| `GET B/pages/{absolute_page}?student_id={sid}` | 原卷对照；原文件绝对页号从学生 `start + 相对page` 获得 |

批阅台会话存在不表示课堂会话有效。课堂428失效用 CLI `access`/`relogin` 固定恢复：access 读取不含模型能力的最小 session 与 login-check；relogin 使用既有强制登录入口，授权链接只在浏览器内存导航。HTTP200中已知业务428也须按诊断处理，其他428不猜为登录失效。导航已启动不是恢复成功；回原 origin 后 access 核验同一教师/学校和有效课堂会话，再读当前业务状态继续，不自动重放写请求。一次恢复仍无效或身份变化就保留阻塞，细节见 [CLI](cli.md)，不查前端源码寻找刷新入口。

选参考卷使用批次 `batch.students` 中真实学生卷，不是尚未生成的 `analysis.students` 结果列表。页面某个 analysis students 为空不能证明没有可选卷或平台故障；以批次、当前阶段和真实响应查明。

业务详情路由为当前 origin 的 `/exams/{bid}/analysis`，只在确认本次 bid 存在且有权访问后提供。同步后平台链接必须从同步响应取，不用此路由冒充错题本链接。

仅在需要该模型的阶段检查模型能力，非 LLM 供应商批改不套用扫描模型要求。模型检查失败先处理环境：`model_configured` 是聚合值，不能据此认定所选扫描模型可用。出现“当前模型尚未完成学校网关能力验收”等 configured=false 错误时，核查当前登录、学校及真实配置；不反复启动扫描、不伪造能力清单、不修改共享服务。已授权的本地联调可在确认缺部署配置后，复用项目已有能力验收文件（本项目已有 `backend/school_llm_capabilities.json`），按项目真实配置入口在独立端口启动隔离服务，再读 session 验证；不要复制凭证或把临时隔离服务当正式发布。

## 上传与幂等

三种业务模式共用upload接口：已批扫描用workflow_mode=scan；供应商快速批改用grading+xueersi/doubao；答案卷智能批改用grading+llm。后续整理差异见 [批改与续做](grading.md)，不能对所有上传强制scan，也不能把后续整理与重新批改混同。

`POST /api/batches` 使用 multipart/form-data，文件字段 `file` 为 PDF；设置固定 `Idempotency-Key` 请求头。

| 字段 | 要求 |
| --- | --- |
| `workflow_mode` | 显式传scan或grading，不依赖默认值 |
| `grading_engine` | grading按本次选择传llm、xueersi或doubao；scan由服务端设为llm |
| `has_answer_paper` | scan为false；LLM grading必须true，最前完整一份是答案卷；供应商仅用户明确有答案卷时true |
| `pages_per_paper` | 实际每份 PDF 页数，整数 1–12 |
| `paper_size`、`orientation` | 按原卷传 `A4`/`A3`、`portrait`/`landscape` |
| `paper_sides` | `single`/`double`，double 要求每份 PDF 页数为偶数；不是自动补空白页 |
| `scan_fast` | 布尔，当前默认 true；按当前产品设置使用，不将快速模式解释为免验收 |
| `analysis_fast` | 仅供应商批改后的整理设置，不能用来选择供应商或恢复任务 |
| `llm_model` | 用当前允许的配置；源码默认 `qwen3.8-max`，不强行覆盖线上有效配置 |

扫描模式服务端将 grading_engine 设为 llm、has_answer_paper 设为 false，不要求最前面放答案卷。PDF 上限 100 MB、600 页，总页数须能按每份页数整除。不同每份页数应先分离成明确的输入，不静默删页或补齐。

上传响应回读 `id`、`workflow_mode`、`pages_per_paper`、`total_pages` 和 `students` 确认分卷。上传发生超时：先 `GET /api/uploads/{key}`，其状态为 `completed`（含 batch_id）、`not_found` 或 `deleted`。已有 batch 直接继续；not_found 时先排查尚在途请求，再用同一文件、设置和原 key 恢复重传。deleted 不自动重建。相同 key 携带改变的文件或分卷会 409；不能为避冲突自动换 key。幂等指纹包含 PDF hash、分卷、纸张、方向、引擎、答案卷、模型、workflow 及适用的单双面/快速模式设置。

## 课程、名单与启动

1. 用classes读取教学目录，或按grade/subject_id/course_id逐级读取general-options；class-students的source/grade/subject_id/course_id须与本次目录一致。ID全部来自当前允许响应，不点页面选班或编造学期/班级ID。
2. `GET B/roster` 得到当前 revision。`PUT B/roster` body：`revision`、`semester_id`、`class_ids`（1–50 个真实 ID）、`scope`。scope 为 `{source:'teaching'|'general', grade, subject_id, course_id}`；general 来源需要年级、学科和课程，teaching 可用当前合法教学目录。服务端验证学期与权限。
3. `PATCH B/roster/{paper_id}` body：`{revision,student_id}`，解除关联为 null；每次读取返回的新 roster revision。扫描学生 ID/试卷 ID 与课堂学生 ID 不能混用。
已支持的批量关联使用 CLI `associate`；`roster` 一次对账提供未关联卷定位，其同名候选不是身份证据。首次常规查看姓名清楚且有真实卷面与名单证据者可整包关联；仅教师本次明确同意时可按SKILL.md的首轮清楚班级/班内number唯一精确匹配且无冲突例外核验，仍保留逐项证据、版本与回读；未授权或不满足时，第一次查看已模糊或未识别者直接暂留，不放大、新增 OCR、换识别方式或用剩余名单试探。用户提供新证据或本次明确要求重新识别时，按其范围重新判断，仍不猜人。只有身份已取得明确证据、且需同时修复身份姓名与关联时使用以下接口：先 `GET B` 取对应 `students[].revision`，再 `GET B/roster` 取实时 roster revision；`analysis.students` 不提供身份编辑所需 revision。`PATCH B/students/{sid}?include_roster=true` body 使用 `{identity_only:true,revision:试卷当前revision,name:经核验的姓名,name_confirmed:true,results:[],roster_revision:实时名单revision,roster_student_id:精确课堂学生id}`。roster_revision 与 roster_student_id 必须同时提供；扫描模式不能使用该接口改批改结果。成功响应含保存后的 student 与 roster，后续操作采用新的版本并回读确认真实 student_id 关联；多份顺序保存，不能并发复用同一个名单版本。422 必须读取 detail 并修正必填字段或格式，409 回读版本；HTTP 返回、显示名变化或本地表单更新本身不证明关联持久化成功。未识别卷仅报告已有份号、原 PDF 页码区间、实际可见特征与业务定位，疑似局部文字只标疑似，不为交付补做身份识别。

4. 初次参考卷按主文规则，从本批前几份 `students` 的少量同卷候选中优先选正确率较高的合格卷；快速批改已有全批真实可靠正确率时，直接选现成结果中的合格最高者；无全批现成正确率时，仅在前几份候选中轻量比较选最高，不为选卷另行识别全批。并列以清晰完整或靠前优先。先预览确认清晰、完整、题序版式一致；最高者不合格则用合格最高者并说明。可靠既有正确率可直接用，无则仅粗比可辨教师批注并标明估计，不把未批当正确，不为比较先识别/重批全批。不能把课堂 student_id 当试卷 id；用户快速批改术语与 `scan_fast` 是否同义，先核实当前平台实际模式，不据此改成普通 grading。`POST B/analysis` 必须发送经标准 JSON 序列化的对象 body `{reference_student_id: 所选本批真实学生卷id}` 触发预切，之后轮询；未有 draft 且未保存参考卷时空 body 会 409“请先选择标准卷，再开始预切”。已有任务先读状态并沿用当前 reference_student_id，不重复启动或仅因发现更高正确率而换参考卷、重开全批；用户明确要求更换时，通过当前参考卷入口按真实契约与影响处理。`status`、`stage`、`scan_phase` 来自真实响应；常见 `awaiting_frames` → `frames_confirmed`/整理中 → `awaiting_confirmation` → `catalog_confirmed`/学生处理中 → `completed` 或 `partial`，自动流程可能跳过部分等待阶段。部分完成不等于全员完成，结合学生状态、issues 和 stale 验证。

## 标准卷选择错误的精确诊断

2026-11-03 核对的本地 backend/app.py 源码中（未经线上验证），422 原文“标准卷选择格式无效”仅在 JSON 解析失败或解析后的 body 非对象时触发；参考卷 ID 不存在会走另一条错误。先核对请求序列化/传输和原始 detail，不猜 reference_student_id 的替代键名，不据此推定平台故障。使用内置CLI/emit标准序列化，保留真实method/path/status/message；线上契约不同时先核实实际响应与registry，确有不兼容才定点回退或报告。

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

改框会换 `frame_revision` 并可能清除受影响页的 checked 标记；使用保存响应的新版本。`POST B/analysis/frames/confirm` body `{frame_revision}` 确认并启动整理。只在 `awaiting_frames` 可直接改框；冻结后用frames-reopen并传当前frame_revision。其他action的功能与字段见上表，不作为通用重试接口盲用。retry-precut需要当前frame_revision和已定位失败相对page。冲突可能带 `X-Error-Code: frame_version_conflict`，必须回读再编辑。

待确认目录用catalog-save-draft：body为`{frame_revision,catalog_revision,questions}`；已整理目录用catalog-save-review，由工具运行时注入review_token。questions保留真实完整对象、稳定ID、来源、content schema、媒体及几何；独立题按真实业务结构拆开，不凭题干文本重造字段。保存后实际复核并回读新版本，再用catalog --plan确认已审目录；该确认命令不编辑内容、不提交课堂，不能沿用编辑前的审查标记。

**新版确认范围**：若批次 `analysis_confirmation_version == 2`，旧confirm被拒绝；由CLI catalog编排以下接口，不点击确认按钮或手存预检token：

1. `POST B/merge-preflight`，body `{source_ids:[],frame_revision,catalog_revision}`。默认只当前记录，不添加其他历史记录。返回 operation_id、preflight_token、versions、duplicates 等。
2. 核对当前范围；若返回重复学生必须依据真实卷确认采用哪份，不能默认任选。
3. `POST B/analysis/confirm-and-start`，body 包含最新 `{frame_revision,catalog_revision,questions,preflight_token,source_versions,duplicate_choices,same_paper_confirmed,name,name_revision,idempotency_key}`。`source_versions` 使用预检返回 versions；默认不合并其他记录时 source_ids 空，duplicate_choices 按真实结果填写（无重复为空对象），same_paper_confirmed 不是绕过多记录审查的开关；name/name_revision 来自本次批次。固定 idempotency_key 属于这一次范围确认。
4. 返回 accepted 后读取 `/api/merge-operations/{operation_id}` 与批次分析状态，不能把 accepted 当学生处理已完成。超时回读原操作与批次，避免另建确认操作。 若 confirm-and-start 返回来源/题目/学生关联变化的 409，先回读当前批次、目录、roster 和预检版本，正常重新预检一次；无用户修改仍连续同因失败时，对比确认请求前后版本，判断是否由请求自身触发变化。记录当前环境、batch、阶段、版本差异与未提交状态后报告服务阻断，停止自动预检循环；不能篡改 source_versions/preflight_token 或服务端记录、回退旧 confirm、删数据重建以求通过。该判断依赖当次证据，不预设任何环境永久存在某个缺陷。

旧流程仅在真实版本允许时使用catalog-confirm，body含`{frame_revision,catalog_revision,questions}`；不据此替代新版范围流程。已完成分析的目录编辑要求运行时review_token，使用catalog-save-review，不拿初次待确认接口强改历史结果。

## 学生结果与复核

scan-retry与scan-retry-failed均无body，仅重试统一整理的指定卷/失败范围，供应商整理也适用，不重批原供应商结果。scan-result-save仅scan使用，body含当前分析revision、真实verdict及必要note；response-regions-save适用organizer，body含当前分析revision与真实regions。regions使用0-based相对页和0–1归一化bbox；保存后回读新revision并重做必要媒体/检查。共用判定和作答结构优先question-review/responses，保留教师原判；不要通过删除学生规避同步阻塞。

## 首轮检查交付与增量复核

本节仅适用于老师已选择整理或同步的路径；只批改路径核对全批原始done和基础结果计数后停止，不进入目录、题框或preflight。整理优先统计准确、再题目准确、最后图片位置。首轮全批程序聚合核验结果覆盖、人数/份数/叶题数、重复遗漏、学生关联、各 verdict 与 uncertain 数量；严格核对实际标准题来源的题干算式/上下文/批改归属：统一 organizer 对照代表卷参考图，LLM legacy 对照现有标准题来源/答案卷，不强造参考卷参数。学生个人图以证据风险抽查为主，实际影响判定或统计的截断/串题须修；无影响的留白和轻微边界偏移不默认修复。

必要核验与已知实质错误处理后跑真实完整 preflight；有新实质修复则重新检查，检查终点最新ready=true后立即交付首轮批阅台链接并停止；已选同步终点继续已授权同步并交付真实链接，两种模式都不继续自动逐人逐题看图、全量重识别或微调 region。给出统计、未定、warnings、已做/未做的验证，区分统计完整一致与判定全量准确，并可选询问是否继续全量准确性检查与修复；首轮不等待该选择才交付。

后续仅按用户选择的范围深审统计/题目，个人图精修末优先。先读 progress/status/version，只有变化和具体问题才拉对应学生/题目；同一 batch 只更新受影响范围，重新准备所需媒体与检查。无新变化不重复验证，避免完整 payload 循环读取与无依据全量重跑。不承诺固定处理时长，只报告真实阶段进度。

## 同步准备、检查与提交

先落实SKILL.md中的教师选择：扫描本身包含整理，批改可选批完停止或继续整理，整理后可选只检查或同步课堂。普通“上传/传一下/处理一下”缺少业务终点时先补齐选择，不能自动展开整理；已明确项不重复问。只批改不进入本节；检查终点执行至最新全批检查并交付，明确同步终点才进入下述提交步骤。历史上传约定、其他材料和CLI兼容默认值不替代本次教师选择。

配置与检查、提交分开：`progress/start` 和 `preflight` **不**等同于平台导入；检查模式可用它们完成检查，但禁止 imports 的 POST 和可能继续提交的 resume。

1. sync-config返回`{config,source_version,questions,selection_context,...}`，先取`cfg=response.config`，revision在cfg内，不在顶层。只提取必要配置、版本与聚合计数，不原样打印题目/答案。sync-options按grade_id/subject_id/batch_id读取允许目录，sync-courses按真实grade_id/subject_id读课程；未选ID按目录接口逐级读取，不默认点页面或硬编码。
2. `PUT L/config` 的严格 body：`revision`、`grade_id`、`subject_id`、`semester_id`、`course_id`（可空串）、`type_mapping`、`class_mapping`、`selected_paper_ids`（可 null，具体默认范围由服务端核验）。ID 为真实正整数字符串；字段不接收随意 extras。type_mapping 键是标准卷真实 question id，class_mapping 键是本批 paper id，值来自允许目录。PUT 的成功响应直接是配置对象 cfg，采用 `cfg.revision`；它与 GET 的包裹结构不同。不能漏传已有映射而清空它。同步范围应覆盖本次已授权卷，不能为检查通过静默排除失败项。
3. 可 `POST L/progress/start` body `{revision}` 启动异步准备，然后 `GET L/progress`；返回 preparation、attempt、reusable、current。preparation 的 running/preparing/paused/blocked/awaiting_confirmation 是准备状态，不是同步成功。媒体单独需要时用 `POST L/prepare-media`、`GET L/media-preparation`；不要绕过媒体检查。 返回 `MEDIA_STORAGE_NOT_CONFIGURED` 且 `retryable=false`、`recovery_action=configure_storage` 时是环境配置阻塞，不是适合不断重试的临时失败；核实当前真实部署的存储要求和现有配置，不能把“已有配置文件”当成存储已启用或媒体已验证。当前平台已配置、既定流程中的媒体准备和上传也属于本次已授权上传/检查目标的必要步骤，已选整理检查路径直接执行，不需另有实际同步授权，不因媒体涉及外部存储就一律再问；这不包含新增外部公开范围。正常已授权的同步流程不新增逐步确认；只有修复会改变外部公开范围、超出现有授权或自动审批明确拒绝时，保留当前检查与恢复点，报告具体未接通项和审批拒绝原因，停止被拒绝的操作，不改公开权限、不转用其他公开上传通道规避，也不伪造 ready。
4. `POST L/preflight` body `{revision,allow_pending_formula_protocol:false}`，返回 `ready,status,issues,counts,check_token,source_version` 等。原始 ready 仅针对平台本次选择范围，已关联 subset 的 ready 不能代表全批；使用 CLI 的 completion、remaining 与总数/覆盖/未覆盖数判断全批终点。姓名未关联时也执行实际检查并记录返回结果，报告“已执行检查，未通过/未完成”，同时列出媒体等其他剩余项，不能推断补姓名即可全量 ready。全批覆盖完整、ready=true 且 status=awaiting_confirmation 才说明本次全批检查可提交；pending/failure/blocker 都不是通过。路由会 `remember_check` 保存本次教师、revision、check_token 和 awaiting_confirmation 记录，因此不必为了生成该记录额外重复 progress/start。媒体仅按 CLI 门槛启动，运行中可用 run --follow 等待；准备完成后重新 preflight 取得最新检查。
5. **仅同步模式**：sync运行时核对授权内警告、当前教师、最新preflight与cfg版本，依赖提交端权威校验；真实部署未返回内部确认字段时不自行补造，有明确接口缺口才定点补核。以下是sync在浏览器内存构造的`POST L/imports`发送契约，不能把token复制为本地计划：

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
