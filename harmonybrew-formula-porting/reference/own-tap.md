## 自有 tap（social4hyq/core，GitHub 线）

只放不合官方准入的 formula。相对场景一的增量：

1. 在独立 worktree 里改，主克隆分支会被别的会话切走；切分支前 `git fetch github main`（origin 是 atomgit 镜像，PR 开在 GitHub）。
2. 与官方同名的引用写全限定 `social4hyq/core/{formula}`，裸名会被静默劫持成官方版；查冲突用 `ls Formula/*/*.rb`，`brew info` 不可信。
3. formula 单文件自包含，禁 tap 级共享 Ruby。
4. 仍是单 commit，改动用 `git commit --amend` + `git push --force-with-lease`（官方那边用 `push -f` 压平）。merge 报 "base branch policy prohibits" 是 GITHUB_TOKEN 不触发 workflow 的已知假失败，用 `gh pr merge --merge --admin`。
5. bottle 内容变了要新 tag `-r<N>`，与 formula `revision` 是两套编号；bottle 回写会把 `bottle do` 落到文件顶部，同 PR 再改时归位到 `livecheck` 之后，否则 audit 必红 ComponentsOrder。
6. 本机试构建允许，但推 CI 前删两类本机痕迹：签名步骤（selfsign、binary-sign-tool、签名器 build dep），以及以 `uname -s`=HarmonyOS 为前提的分支。本机强制 ELF 签名才能 exec，CI 容器 `uname -s`=Linux 且构建期不验签——本机绿不等于 CI 绿。签名由流水线统一做，install() 不承载。
7. 真机装瓶后必跑 `brew test` + 真实负载；只断言文件存在会放过坏 bump。

