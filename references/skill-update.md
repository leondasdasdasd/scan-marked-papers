# 技能更新与回滚

本流程只更新本地 `scan-marked-papers` 技能文件，不更新批阅台业务、不修改项目源码、不发布应用、不推送 Git。技能默认保持当前版本；用户没有明确“更新/安装/升级”时只读查看。

## 只查看

1. 读取本地技能目录的 YAML `name`、`description`、agents 元信息及支持文件，记录当前版本。若没有显式版本字段，使用已安装包的 release/tag、文件校验和或变更时间作为“版本未标注”，不要自行编造语义版本。
2. 取得 GitHub owner/repo：优先用户当次提供的仓库；其次使用已核实的官方项目元数据。当前工作区的 Git remote 是 GitLab，不能据此推导 GitHub 仓库。没有可信 owner/repo 时报告“无法核对 GitHub 最新版本”，不猜仓库。
3. 只读比较 GitHub releases/latest 或 tags 与本地版本，展示候选版本、变更文件、兼容性、是否需要迁移及验证结果。API 或页面不可读时如实说明；不能把搜索结果、fork 或非官方仓库当官方发布。

## 用户明确要求更新

先确认目标 owner/repo、目标 release/tag 和更新范围。用户只说“更新”而没有可信仓库或目标版本时，可读取该仓库最新 release/tag并展示计划；在下载或安装前仍不得替换本地文件。执行以下步骤时区分状态：

- **下载包**：官方 release zip 地址优先使用 release 返回的真实 asset URL；若发布约定明确且 asset 名称已核实，可用 `https://github.com/{owner}/{repo}/releases/download/{tag}/{asset}.zip`。源码 tag 归档地址为 `https://github.com/{owner}/{repo}/archive/refs/tags/{tag}.zip`；这只是构造规则，不能把不存在或未核实的 asset 当成功。下载到临时目录，保留来源 URL、tag/release、SHA-256 和包内顶层结构。下载不等于安装。
- **校验包**：确认包含 `SKILL.md`、合法 YAML frontmatter、需要的 `agents/openai.yaml` 与 references，目录名为 `scan-marked-papers`，没有凭证、Cookie、storage state、临时业务数据或不相干大文件。读取变更说明并检查兼容性；不要执行包内未知脚本来“安装”。
- **实际安装**：只有用户明确授权更新时，才备份当前本地技能目录到同级临时备份，再在 `$CODEX_HOME/skills/scan-marked-papers`（或当前技能管理器报告的实际安装目录）替换。保留用户本地已有的未提交技能修改：先比较差异；若上游会覆盖本地改动，列出冲突并停止替换，除非用户明确选择覆盖。不要用 `git add`、commit、push 或自动改业务仓库。
- **安装后验证**：运行 `python3 /home/yungu/.codex/skills/.system/skill-creator/scripts/quick_validate.py <安装目录>`，回读 `SKILL.md`、agents 元信息、版本/tag 和关键 references，确认新版本已生效。只报告真实验证结果，不把下载完成或文件存在当安装成功。
- **失败回滚**：下载、结构校验、兼容性检查、替换或验证任一步失败，保留错误日志和临时包，恢复安装前备份并重新运行 quick_validate；回滚失败时保留旧目录，不删除用户技能，报告具体阻塞。更新成功后清理本次临时包和备份；保留用户原有会话、服务与其他技能。

## 安全边界

不在技能、日志、截图或交付报告写入 GitHub token、账号密码、Cookie、授权链接或学生数据。私有仓库需使用用户已授权的 GitHub 工具/会话；不把凭证拼进 URL。更新仅影响本地技能文件，不能借更新请求顺便改应用、切换环境、上传试卷、同步课堂或发送通知。更新前后明确标注“只查看”“已下载包”“已安装并验证”三种状态。
