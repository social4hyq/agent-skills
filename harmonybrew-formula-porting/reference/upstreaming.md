## 上游化：把自有 tap 的 formula 送进官方 core

1. atomgit 是指南口径，gitcode 才是实际开 MR 的通路，`gh` 对两者都无效。**建 MR 由用户在平台网页手工完成（AtomGit 会带 PR 模板），agent 不代建。**
2. 若用户需要，agent 可协助把分支推好：分支必须先推 gitcode 上的 fork，`head` 写 `"{fork_owner}:{branch}"`——atomgit fork 与 MR 体系不互通。API 通路 `POST https://gitcode.com/api/v5/repos/Harmonybrew/homebrew-core/pulls`（token 传法变过：`private-token` header／`?access_token=` query，401 就换）**仅作参考，不用于代替用户建 MR**。
3. 先去本机脚手架：签名步骤、指向本地文档的注释、tap 专属路径。cellar 一律 `:any_skip_relocation`，wrapper 用 `write_env_script`。
4. 顺序固定：自有 tap 的 GitHub CI 构建先绿，再准备官方 MR。agent 止于「描述落文件」——交用户审阅，MR 由用户在 AtomGit 手工创建（禁用 API/自动化建 PR，见「提交纪律」#1）。
5. 描述写法（用户逐条纠正过）：一句话说明 + 与上游 formula 的差异 + 验证结果表格（核心，不许精简掉）+ 失败用例按原因分类成表。不提旧 PR 与迭代历史，不报补丁个数，不写"测的是旧构建"这类过程性备注，读起来像人写的。
