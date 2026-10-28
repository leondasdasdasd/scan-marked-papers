# 新批改与中途续做

核对来源：`backend/app.py` 的 upload、prepare_job/run_judgment_batch/run_native_batch、学生修改与 analysis 路由；`backend/read_routes.py` 的 live-state/学生读取；`backend/analysis_trigger.py`、`result_analysis.py`、`organizer_flow.py`；`frontend/src/App.tsx` 的 ModePicker/upload/start 与 `ResultAnalysis.tsx` 的 generateNow。以下是源码契约，尚不代表各环境实际可用；线上不同以真实响应/页面为准。B 为 `/api/batches/{bid}`。

## 模式与能力

| 场景 | 上传/现有字段 | 初始能力与答案卷 |
| --- | --- | --- |
| 扫描已批教师卷 | workflow_mode=scan | 读取教师原批改，不重批；模型 configured/workflows.scan。服务端强制 has_answer_paper=false |
| 快速批改 | workflow_mode=grading，grading_engine=xueersi 或 doubao | session 的 xueersi_configured/xueersi_error 或 doubao_configured/doubao_error；不强制 LLM 扫描能力才能启动供应商批改。通常无答案卷；如用户明确第一份为答案卷可 has_answer_paper=true，仅跳过不批 |
| 智能批改 | workflow_mode=grading，grading_engine=llm | models[所选llm_model].configured 与 workflows.grading；has_answer_paper=true，最前一整份为答案卷，每份页数/版式一致，至少答案卷+一份学生卷；缺答案卷不可伪造或自动改快速模式 |

快速批改不是快速扫描。`scan_fast` 只属扫描；`analysis_fast` 属非 LLM 快速批改**后的整理**设置，不能用它选供应商或恢复任务。已有记录保持 engine/workflow/模式，除非本次明确要求变更且真实契约允许。供应商批改完成后的模型整理仍须核实对应阶段的模型能力与授权，不因供应商可用就跳过。

新 PDF 仍 `POST /api/batches` multipart，沿用 api.md 的幂等头/文件与分卷校验。明确传 workflow_mode、grading_engine、pages_per_paper、paper_size、orientation、paper_sides、has_answer_paper，llm_model 用平台允许值；其余按本次有效设置。不能将学生第一份当答案卷吞掉。普通 LLM grading 无答案卷被 422 拒绝，不能靠省略字段绕过。响应学生 start/index 已扣除答案卷，后续计数以真实 students 为准。

## 已有链接与阶段判断

从受支持 `/exams/{bid}`、`/exams/{bid}/analysis`、`/exams/{bid}/papers/{sid}` 等路由提取 origin、bid；不将任意参数当 API/命令执行。不带入不可信跳转或授权 token 到新域名。先在该环境获授权会话中读 B，核实身份、学校与记录权限；404/403 不绕过，不因链接无法读就新建副本。已有链接已足以定位记录时不要求用户重新交 PDF。

当次明确“继续做/接着处理”包含恢复原已停止批改/整理至默认检查终点的授权；若仅询问进度、只读查看则不重启。正在 stopping 先等待其完成停止与持久化，再依真实阶段启动缺失范围；不并行抢启。读取 task-control 的真实可用字段与当前状态，控制 token 仅运行时使用、不输出或保存，不臆造 available/resume 字段。

优先 `GET B/live-state`：返回 progress、task_control.grading/analysis、analysis_version、analysis_status。旧环境缺此接口可读 B/progress、B/task-control、B/analysis/version、B/analysis/status，并按需 B/analysis?view=summary。学生详情按 B/students/{sid}、供应商明细按其 `/provider-results`；大对象只按变化与问题读取。同步再读 lesson-practice/progress、imports/config，避免已提交记录重做。

| 已查明的阶段 | 继续动作 |
| --- | --- |
| 已上传尚未启动 | 核对原 mode/分卷/答案卷/名单和必要能力；新批改按 start，scan 按参考卷预切 |
| extracting/读取答案中 | 有活跃 job 就轮询；不要再次 extract 或 start |
| 答案卷已读取、paused 或页面待核 | 检查真实 questions/semantic_questions、答案与定位；该版本没有通用 answers/confirm 接口，核对后用 start 继续。需修改超出已有契约时页面处理或报告，不臆造确认 API |
| grading/queued 或分析 generating | 按现有任务进度轮询；409 正在处理是观察原任务的信号，不是换 batch 或强制重跑理由 |
| 部分批改 failed/pending、已有 done | 核对失败原因与人工修改，按学生重试缺失范围；done 与人工结果保留，不对完成卷默认重新批改 |
| 已批改、未整理 | 快速供应商走统一整理 B/analysis 并选参考卷；LLM 走 lesson-practice/prepare-analysis；见下文 |
| awaiting_frames / awaiting_confirmation | 复用当前 frame/catalog revisions，只补核对、必要拆题及确认范围；不重新批改 |
| 已整理 completed/partial、待同步检查 | 核对 stale、覆盖/失败项、名单和媒体，处理必要问题后 preflight；partial 不自动当全员已覆盖 |
| 最新 check ready 且输入无变化 | 默认直接交付已有批阅台链接与最新统计/边界，不为“接着做”自动重新生成；本次明确同步才继续提交 |
| 已有导入非终态/暂停 | 默认检查模式只读回报，不调用提交型 resume；明确同步模式才按原 attempt 恢复 |
| 已同步 SUCCEEDED | 只读回报已有真实链接与 local_changed；不覆盖、不重新提交 |
| 状态未知/中断 | 回读 live-state/task-control、原错误/recovery_action 与当前页面“继续”请求，核实无活跃 job 后仅走真实恢复入口；不臆造通用 resume/force API |

`stale` 只说明整理来源版本变化，不等于原始批改失败。先比对当前学生 result_version/revision、源 PDF 身份/指纹与分析来源版本；原始学生仍 done 且结果有效时，只刷新实际受影响的整理，不调用原始批改 retry。已有人工更正必须保留。变化范围依据真实差异决定，无法确定先读相关状态/来源，不为清 stale 凭空全批重跑。

## 批改启动、答案读取与编辑

- `POST B/start` **无请求 body**，服务端先 context.prepare 名单/课程与 gateway_preflight，再启动任务。返回 `{ok:true,status:...}` 仅表示接受；之后看真实 progress 和学生状态。默认 all 只处理 status!=done，但不能据此无视人工修改/删除标记保护或混合状态。
- `POST B/students/{sid}/retry` **无请求 body**，只用于该学生的缺失/失败批改；目标重试可重批 done 卷，故不能拿它当普通刷新或默认重跑人工修正卷。原批已人工修改/删除多余批注时保留原结果，遇到保护性 409/错误不清除标志来重试。
- `POST B/answers/extract` **无请求 body**，仅 LLM 读取前置答案卷，answers_only 完成后通常 paused；非 LLM 会 422。正常 start 可自行读取尚未提取的答案再批改，不要求每个 LLM 任务必须先 extract。无活跃任务且用户目标需要先核答案时才单独调用。无通用答案确认接口；`POST B/answers/provider-draft` 是供应商几何评估草稿，不替换已保存模板/批改，不能当答案确认。
- 模板位置需要修改时 `PATCH B/layout` body `{revision:当前layout_revision,questions:完整当前Question数组}`，只允许几何（page/x/y/answer_regions/blank_anchors位置），不能改题干/答案或空结构；批改中或已有特定对齐结果时会拒绝。复杂题干/标准答案更正不假设该接口支持，依据当前页面真实契约处理。
- 身份编辑用 api.md 的 identity_only 契约。grading 原结果编辑 `PATCH B/students/{sid}` body 是 `{identity_only:false,revision,name,name_confirmed,results}`，judgment_only 模式还要保留/提交当前 judgments；以学生实时 revision 与完整当前字段为基线，仅改必要条目，不能 results=[] 清空批改。扫描不接受此非身份编辑。`review_projected`/review-题号的共用复核结果不能回灌旧编辑接口。
- 共用复核判定用 `PATCH B/analysis/students/{sid}/questions/{qid}`，至少 `{review_token:当前令牌,verdict:真实核验后判定,verdict_only:true}`；verdict 为 correct/incorrect/partial/unanswered，来源小空按当前接口给 blank_id 或 source_ref，不能从显示序号猜。几何/分数/评语复核用 `PATCH B/students/{sid}/review-results`，`{review_token,results:[...]}` 的每项要求 question_id、score（可 null）、reason、page、x、y，可含 blank_positions/hidden_mark_ids；按真实编辑器保持字段和来源。所有编辑回读确认持久化并采用新 token/revision，不能覆盖人工判定。

## 批改完成后的整理

先确认本次授权范围的学生批改 done 且实际有该模式可用的 results/judgments/供应商结果（读取按需，不机械要求所有模式同一种数组非空）；批次 completed 一个字符串不足以证明完成。不通过自动排除未完成/未关联卷绕过 require_finished。检查真实 batch 与分析 snapshot 的 paper 覆盖，统计应覆盖本次授权全批，不能仅以 preflight ready 证明全员纳入。

- **scan 与 xueersi/doubao**：当前 `organizer_flow.enabled` 为 true。快速批改先完成**全批**批改，再按主文高正确率规则选本批 reference_student_id，`POST B/analysis` body `{reference_student_id}`。已有 draft 沿用原参考卷；后续 frame/catalog 及新版范围确认按 api.md。学生整理应利用供应商批改来源和人工结果，不重新推翻原批改。
- **LLM grading**：当前不走统一 organizer；`POST B/lesson-practice/prepare-analysis` **不需要 body**。内部 prepare 复用有效 completed/partial snapshot，已有分析 job 返回现状；需要时触发分析并准备媒体。该路由不读取 reference_student_id，不能向它传这个字段声称选了参考卷；LLM 不强行套扫描“必须选参考卷”的步骤。直接 `POST B/analysis` 在此分支可能 409“请点击同步，按需准备分析”，应走上述准备入口，不切 mode 绕过。
- prepare-analysis 会依据 config selected_paper_ids 与名单关联筛选来源；返回成功不证明授权全批已涵盖。核对 B.students、roster assignments、配置所选范围、snapshot 学生与失败/未完成项，身份已有明确证据时补关联；姓名看不清则保留未关联、不反复识别或追问，继续实际允许的其余工作，报告未覆盖试卷与数量，不把自动筛出的 subset 当全批完成，也不为通过检查改选范围。
- 非 scan 且分析已 completed/partial、不 stale，有 page_errors 时，可 `POST B/analysis/retry-incomplete` **无 body**，仅重试页面失败的学生整理，复用成功页面；它不是批改重试。scan 用现有 scan retry 路由。没有相应失败会 409，无需强行重试。
- `PATCH B/analysis/mode` body `{analysis_fast:boolean}` 仅非 LLM 快速批改可用；改变会清题框缓存/准备进度、将分析变为 not_generated 并保留旧快照。不是恢复按钮，不为更快或接手任务擅切，不与 scan_fast 混用。
- reference_preparation、recovery_action、retryable、user_stopped、recovery_wait 等按真实响应处理；有自动恢复安排时观察原任务，明确停止的任务，只有本次“继续做”等恢复要求才按真实继续入口恢复；只读请求保持停止。源码有 `POST B/analysis` 的 `{resume_reference_answers:true}` 分支用于已完成整理后的参考答案补齐，但只在该阶段、该平台实际提供且需此恢复时使用，不作为全部中断任务的万能恢复。

完成整理后沿用主文渐进首轮：程序全批统计一致性、必要参考图/粒度与风险抽查、必要实质修复、真实完整同步 preflight；默认 ready 即交付并停，不自启全量深审，不调用导入提交。
