---
name: harmonybrew-formula-porting
description: Use when 涉及 Harmonybrew 官方 core 或自有 tap social4hyq/core 的 formula——录入/适配、修改、升级、修复、打 OHOS 补丁、排查构建/测试失败、revision，以及**为这些改动提 PR/MR**（这类任务必读，含提交身份、先自有 tap 构建验证、禁止直接向 Harmonybrew 提 PR 的硬性纪律）。覆盖搬运上游 formula、准入规则与 PR 自查纪律（PR 数量、冗余修改、用词禁令）。因不合准入规则（闭源、预编译二进制、fork 源）而落自有 tap 的 formula 也走这里。排除边界：npm 包移植制作走 npm-porting skill，前端工程适配走 ohos-frontend-upgrade skill。
---

# harmonybrew-formula-porting

## 必须遵循（违反会被维护者拉黑，动手前先读这段）

1. **提交身份只能署用户本人**：所有 commit 的 author 与 committer 一律是 `social4hyq <social4hyq@163.com>`（本机全局 `git config` 与仓库都已配好，直接用即可）。**禁止**用 `-c user.name=…`/`-c user.email=…` 或 `GIT_AUTHOR_*`/`GIT_COMMITTER_*` 把它覆盖成 `agent`、`bot`、工具名等任何非本人身份。Harmonybrew 维护者反感 agent 提交的 PR，再被发现会被拉黑。
2. **必须先自有 tap、后官方**：任何要上游的改动，**第一步永远是提 PR 到 `social4hyq/homebrew-core`**，走它的 GitHub CI 做构建 + `brew test` 验证；**自有 tap 的 CI 绿了之后**才谈官方 MR。**禁止直接向 Harmonybrew（AtomGit / gitcode）提 PR/MR。**
3. **官方 MR 由用户手工创建**：自有 tap 的 PR 可以由 agent 提；官方仓的 MR 只由用户在平台页面手工建。agent 至多做到「把分支推好 + 描述落成文件、交用户审阅」，禁用 `gh`、v5 API 或任何自动化工具在官方仓建 PR——agent 不代建。
4. **非自有仓不留任何 AI 痕迹**：官方 PR 模板里的「AI 人工审核」勾选与验证截图是用户本人的事实陈述，agent 留空；交付止于可核验的 CI 链接。

## 权威流程（每次现拉，不凭记忆）

```sh
for f in contribute-formula self-check-pr; do
  curl -s "https://atomgit.com/api/v5/repos/Harmonybrew/docs/contents/zh-CN/contributor/$f.md?ref=main" \
    | python3 -c "import json,base64,sys;print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
done
```

准入规则、搬运上游 formula（严禁手写）、英文注释、最小化修改、revision、commit message 格式、一 PR 一 commit 一 formula、ci-runner 容器、`diff -ruN`、`request-ci` 与替代 PR——在 `contribute-formula.md`；PR 自查清单（PR 数量上限、冗余修改黑名单、用词与版权禁令、限制措施）在其指向的 `self-check-pr.md`。任一份拉不到就停下问用户。

## 主线（关键命令与范围）

- 构建：`brew install -y -s -v --include-test {formula}`；测试：`brew test {formula}`。
- 改动范围：`Formula/{subdir}/{formula}.rb` + `Patches/{formula}/` + `Aliases/`，其余文件一律不动；每轮 `git status --porcelain` 查越界。
- **禁止在鸿蒙 PC 本机构建官方 core 的 formula**——包管理器已做限制，绕过做出来的产物合不进去；本机只服务自有 tap 试错。
- 提 PR 前 `brew style` + `brew audit` 全绿；每个 PR 只改一个 formula。

## 细节（按需读对应文件，别凭记忆）

| 文件 | 何时读 |
|---|---|
| `reference/scenario-1-new-formula.md` | 录入/适配一个新 formula（搬运、构建、打补丁、临时 tap 自检、越界检查等 9 条） |
| `reference/scenario-2-fix-build.md` | bump 后构建/测试挂：排查下发模板与注意事项 |
| `reference/scenario-3-minimal-diff.md` | 跟上游 Homebrew formula 做最小化 diff（10 条） |
| `reference/submission-discipline.md` | 官方 core 的提交纪律（来自 `self-check-pr`，agent 最易踩的 6 条） |
| `reference/own-tap.md` | 自有 tap `social4hyq/core`（GitHub 线）的增量规则 7 条 |
| `reference/upstreaming.md` | 把自有 tap 的 formula 送进官方 core（顺序、描述写法） |
| `reference/ohos-adaptation.md` | 报错对照定位 OHOS 适配问题 |
