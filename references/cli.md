# 批量 CLI 编排

本说明对应技能目录 scripts/paperflow.py、paperflow.js 与兼容 paperflow_base.py。实际 workflow_mode=scan 且具备可用浏览器 run-code 适配器时优先使用；适配器缺失或当前阶段不支持时直接按原技能接口/浏览器回退，无需额外询问工具选择授权。默认到真实同步检查，不提交导入；回放编排速度不代表线上端到端处理耗时。

## 入口与状态

Python入口全局参数在子命令前：`--base-url <已核实origin>`、`--batch-id <本批ID>`、`--browser-session <已登录会话>` 均必需；可选 `--wrapper`（默认 ~/.codex/skills/playwright/scripts/playwright_cli.sh）、`--timeout` 1–180默认45、`--interval` 2–30默认5、`--checkpoint <本地JSON>`。由wrapper run-code/page.evaluate同源fetch，不导出凭证，禁止重定向；先按原技能核对身份、学校与环境。timeout是轮询预算，并非每步网络请求的硬性总截止。

```bash
python3 <技能目录>/scripts/paperflow.py --base-url <真实origin> --batch-id <真实ID> --browser-session <已有会话> --checkpoint <本次检查点文件> run
```

将占位符替换为真实值。所有命令的ok/退出码只说明工具执行，业务结果看outcome、ready、submitted与覆盖。默认不包含imports提交/提交型resume/删除/重新批改。CLI不会自行登录，不关闭用户原有页面。

| 命令 | 当前行为 |
| --- | --- |
| `run [--plan <JSON>] [--review-pdf <PDF> --review-out <DIR>]` | 先读取imports与task-control；任何已有导入返回existing_import_readonly，stopping/stopped/paused返回stopped_readonly。只支持workflow_mode=scan，其他返回unsupported_workflow后按原技能回退，不改模式。按真实状态启动预切、应用已审题框、轮询、输出目录待审或统计/媒体准备/预检；同时给出review-pdf/review-out时，needs_frame_review或needs_catalog_review用同一次读取的review直接生成校对包，不再另读snapshot |
| `snapshot [--output <JSON>]` | 读取批次与analysis?view=catalog，输出参考卷、源PDF SHA、frame_revision、完整frames几何与精简questions；reviewed=false，不代表看过图 |
| `review --pdf <本次原PDF> --out <受控目录>` | 先snapshot，再核对本地PDF SHA与source_pdf_sha256，解码所有参考页一次，生成带框全页图、contact-sheet.png与review.json。需pymupdf/Pillow；文件含试卷内容仅本次受控使用。生成不等于审核，reviewed始终false，缩略接触表不足时看全页细节 |
| `frames --edits <JSON> [--confirm]` | 先查导入/停止保护，按版本校验整包shift/set/split，在内存完成全部编辑与几何检查后最多一次PATCH；--confirm再POST frames/confirm。不是跨PATCH和confirm的事务 |
| `associate --plan <JSON>` | 先校验整批证据/名单版本，再顺序PATCH每份关联、采用每次新roster revision，末尾回读确认；最多50项。中途失败可能已保存部分，不是原子批量事务；独立命令现已先查导入/停止保护；恢复可用同目标与当前版本匹配的有限关联回执，仍须核对当前授权 |
| `inspect` | 兼容实现读取批次、分析摘要、roster，聚合全批人数、叶题、作答、重复遗漏和未关联，非视觉验收 |
| `check` | 兼容check并开启prepare：先inspect/config/preflight；独立check先做导入/停止保护；仅真实媒体pending、无blocker/failure且结构完整、全量scope、全关联时才可能准备媒体。先读progress：仅status=running表示活跃准备，复用轮询不重启；status=preparing可能是preflight保存的待准备状态，媒体pending且其余门槛满足时正常调用start，再按真实状态重新检查。不修改配置、不缩scope，顶层ready需真实检查及全批计数一致 |

旧paperflow_base.py仍可按它的真实help执行session/upload/check兼容命令，参数与新入口不同。旧upload仅scan；grading上传与批改流程回原技能。不存在新入口upload/session/watch子命令，不照旧命令名套新脚本。

## 一次判断、整包应用

1. run读真实状态；needs_reference时按原技能前几份高正确率/快速批改现成最高规则选卷。当前输出仅前5份简要候选是工具提示，不是业务硬性候选范围，也不提供真实正确率；无证据不造比例。计划根可传reference_student_id及scope。scope计划含实时revision、semester_id、class_ids、scope对象、evidence_confirmed=true和非空evidence_note；仅把已核实课程/班级目录与本次授权写入。CLI核对当前学期、班级集合和计划scope字段，相同则复用；不同则要求实时roster revision一致再PUT，仍由服务端校验权限，不因CLI能PUT就擅换范围。未生成才启动；已有参考不为更高正确率重开。
2. needs_frame_review时优先让run成对提供--review-pdf/--review-out直接生成review包，已有包无需再发snapshot；也可单用review，实际严格核对全部参考页、题干/独立算式/必要上下文与教师批改归属。一次汇总必要修改，少量留白不修个人框。所有审过页和范围由智能体真实确认后写plan，不凭脚本生成结果填true。
3. 题框计划包含operation_id、snapshot当前frame_revision/source_pdf_sha256/reference_student_id、reference_reviewed=true、scope_reviewed=true、reviewed_pages（覆盖所有0-based参考相对页）、operations，可含expected_leaf_labels。operations支持：set按id改regions/label；shift用ids、归一化dx/dy；split用id与至少2个children，每项真实id/label/regions。split替换原无子框目标并强制新子框parent_id=null；已有子框的父框不能直接split，返回invalid_independent_split，按真实框结构另拟方案或回原接口，不猜删父/重排层级。
4. frames --confirm或run计划根的frames字段可用上述计划。run根还可有scope、associations、expected_leaf_labels与reference_reviewed。确认后遇awaiting_confirmation返回needs_catalog_review，不会代替目录编辑、merge-preflight/confirm-and-start；按原技能做该阶段后继续run。该目录任务包仅含精简题目元数据，内容/答案仍需按实际原接口/页面核查，不能把空白信息当已审。
5. 独立6算式必须最终6个可独立订正业务叶题，不是6框仍一题/6空/组合题。提供真实expected_leaf_labels，frame_receipt保存expected_leaf_labels与split所得independent_labels，run续做继承这些核对。完成时检查叶标签集合/数量，并检查拆出标签对应叶题parent_id为空，结合实际content.children、composite/virtual_parent、is_composite/isComposite、business_question.isComposite及业务题型目录isComposite排除合题；仍不能替代实际题目结构复核，需原技能核对不挂业务合题且无第7个标题题。expected_granularity_verified不等于完整业务验收。
6. 已有清楚证据的关联计划是`{revision:实时roster版本,assignments:[{paper_id,student_id,evidence_confirmed:true,evidence_note:必要证据摘要}]}`。只用本次真实候选/证据，脚本的true不是证据；姓名看不清保持未关联，不放进计划、不反复OCR或追问。不能凭剩余名单猜。run在completed阶段才应用associations；无法执行时回原真实阶段，不改scope求通过。

## 恢复与停止

run的outcome还可能source_stale、needs_catalog_review、needs_targeted_recovery、unknown_stage、waiting、no_progress、iteration_limit；等待与错误不是全批完成。partial/failed不自动重跑，按原技能只恢复失败范围；stale先核源变化，不重批已有人工结果。run最多25轮阶段转换，等待预算到即返回当前状态。

checkpoint保存origin/batch_id、frame_receipt（operation_id、源/参考、after_revision、frames_signature、edit_signature、expected_leaf_labels、independent_labels）和association_receipt（有序paper/student目标对、after_revision），写入本地权限0600。Python与JS都拒绝不同origin/batch的checkpoint。题框恢复要求当前源PDF、参考卷、frame_revision与frames_signature匹配；同operation_id的operations改变会operation_changed，不能用旧回执跳过新编辑。completed续做也核验当前源/参考/版本/框签名后才复用审图回执；关联恢复只在目标列表与当前roster版本等于回执时允许使用原计划版本，逐项读实际已关联目标后跳过已成功项。捕获到的部分失败可将内存回执写入checkpoint，但进程崩溃/传输失败可能仍丢回执；不提供服务端幂等、跨步骤事务或exactly-once。PATCH成功但回执未保存、确认超时、关联中途失败时，先snapshot/roster回读，比较实际已保存内容再决定剩余操作；不重发整个shift包。版本冲突回读并重新判断，不能强改token/revision绕过。计划/校对图/证据摘要仅保存在本次受控工作目录，不写凭证或学生答案全文到报告。

检查结果覆盖不足、姓名未关联、媒体pending时保留真实ready=false与未覆盖数量，不静默勾subset。程序返回visual_review_performed可能仅依据客户端receipt/plan标记，不能自动作为已审证明；只有智能体真的看过才报告视觉完成。首轮默认真实ready且必要核验已完成即给链接/统计/未定/warnings与验证边界并停，不自启深审或提交。

## 隔离回放

仅在已授权隔离环境用真实旧产物回放编排，明确“无新模型调用、复用既有产物”，核对来源和人工修改保留。不能为测量反复重批或把回放写进生产数据。记录实际命令/请求数、编排阶段耗时与覆盖，区分回放和真实线上；模型质量、冷卷识别耗时、线上认证/存储条件与端到端提速均不能由该回放推断。实测结果单独报告并区分合成回归、隔离回放与真实业务运行；未完成数据不作结论，不引用旧5API片段数据作为本版全流程提速。
