## 自有 tap（social4hyq/core，GitHub 线）

只放不合官方准入的 formula。相对场景一的增量：

1. 在独立 worktree 里改，主克隆分支会被别的会话切走；切分支前 `git fetch github main`（origin 是 atomgit 镜像，PR 开在 GitHub）。
2. 与官方同名的引用写全限定 `social4hyq/core/{formula}`，裸名会被静默劫持成官方版；查冲突用 `ls Formula/*/*.rb`，`brew info` 不可信。
3. formula 单文件自包含，禁 tap 级共享 Ruby。
4. 仍是单 commit，改动用 `git commit --amend` + `git push --force-with-lease`（官方那边用 `push -f` 压平）。merge 报 "base branch policy prohibits" 是 GITHUB_TOKEN 不触发 workflow 的已知假失败，用 `gh pr merge --merge --admin`。
5. bottle 内容变了要新 tag `-r<N>`，与 formula `revision` 是两套编号；bottle 回写会把 `bottle do` 落到文件顶部，同 PR 再改时归位到 `livecheck` 之后，否则 audit 必红 ComponentsOrder。
6. 本机试构建允许，但推 CI 前删两类本机痕迹：签名步骤（selfsign、binary-sign-tool、签名器 build dep），以及以 `uname -s`=HarmonyOS 为前提的分支。本机强制 ELF 签名才能 exec，CI 容器 `uname -s`=Linux 且构建期不验签——本机绿不等于 CI 绿。签名由流水线统一做，install() 不承载。
7. 真机装瓶后必跑 `brew test` + 真实负载；只断言文件存在会放过坏 bump。

### 补丁和发布验收补充

- **替换补丁时从 formula 指向的精确上游版本生成完整 diff**，不要拿已打旧补丁的临时源码做基线。对干净源码按 formula 的实际补丁顺序做 `patch --dry-run --fuzz=0`（多补丁时逐个检查并应用，再检查下一份）；在临时源码里跑定向测试，不必为一次移植把临时测试改动塞进发布补丁。audit 需明确指向修改后的 formula，不能用已安装或未修改的同名公式代替。
- **构建产物改变且上游版本不变，必须递增 formula 顶层的 `revision`**。Bottling 的 `rebuild` 和发布 URL 的 `-rN` 都不影响已安装 keg 的升级判定；不要以它们代替 `revision`。源 URL、SHA 和原 bottle 块留给 CI 按流程更新。
- 验证 CI 时按 **当前 PR head SHA → workflow run → job** 核对；旧 run 或 bot 回写后的跳过检查不能证明本次源码构建成功。对仍在跑的 run 用 watch 或间隔等待，不要频繁重复查询或因无新日志就重启。CI 绿、合并、实机验收分开报告；如果本地 tap 提供的 revision 落后，先核对远端和本地状态，无本地改动时可对正确分支做 fast-forward，再指定全限定 formula 安装。
