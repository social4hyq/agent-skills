---
name: harmonybrew-formula-porting
description: Use when 要把命令行/开发工具以 formula 形式录入 Harmonybrew 官方 core，或修改、升级、修复其中的 formula——搬运上游 formula、做 OHOS 适配补丁、排查构建/测试失败、revision 与 PR 纪律。因不合准入规则（闭源、预编译二进制、fork 源）而落自有 tap social4hyq/core 的 formula 也走这里。排除边界：npm 包移植制作走 npm-porting skill，前端工程适配走 ohos-frontend-upgrade skill。
---

# harmonybrew-formula-porting

权威流程每次现拉，不凭记忆代劳：

```sh
curl -s "https://atomgit.com/api/v5/repos/Harmonybrew/docs/contents/zh-CN/contributor/contribute-formula.md?ref=main" \
  | python3 -c "import json,base64,sys;print(base64.b64decode(json.load(sys.stdin)['content']).decode())"
```

准入规则、搬运上游 formula（严禁手写）、英文注释、最小化修改、revision、commit message 格式、一 PR 一 commit 一 formula、ci-runner 容器、`diff -ruN`、`request-ci` 与替代 PR——全在里面。拉不到就停下问用户。

## 场景一：录入/适配一个 formula

构建命令：`brew install -y -s -v --include-test {formula}`
测试命令：`brew test {formula}`
改动范围：`Formula/{subdir}/{formula}.rb` + `Patches/{formula}/` + `Aliases/`，其余文件一律不动，每轮 `git status --porcelain` 查越界。

注意事项：

1. 上游 homebrew-core 有就搬运过来改适配；没有先录进上游再搬回来，直接往下游手写被拒概率高得多；闭源/预编译二进制/源码取自第三方 fork 的不合准入，落自有 tap。
2. 禁止在鸿蒙 PC 本机构建官方 core 的 formula——包管理器已做限制，绕过做出来的产物合不进去。本机只服务自有 tap 试错。
3. 长构建用 `docker exec -d` 分离、日志落容器内按内容轮询；附着执行会被 ssh 断连带崩、假完成、日志截断。
4. 报错对照 `reference/ohos-adaptation.md` 定位。三轮修不好说明根因诊断错了，停下重新诊断，不要继续补。
5. 要打补丁先抄现成的：`ls $(brew --repo harmonybrew/core)/Patches` 近百份已合入范例，挑同生态的（gcc、cmake、perl、coreutils、git、go）连写法带风格照搬；同一个 gnulib/musl 报错直接复用已有 patch。
6. 补丁机器生成，禁手改 `@@` 行号；toybox `patch` 遇错误 header 会静默 `exit 0`，验证靠 grep marker 不靠退出码。
7. 每行改动必须挂实测证据：少了它一定构建/测试失败，或一定让 OHOS 设备上功能出问题。两条都答不上就删。守卫、双路径开关、顺手修、拆多 PR 全是负债——先例、审阅意见、用户批示执行前都要过这条筛。
8. 提 PR 前 `brew style` + `brew audit` 全绿。门禁不强校验，但维护者手工查，不过就拒收。
9. 非自有仓禁一切 AI 痕迹。PR 模板的「AI 人工审核」框与验证截图是用户本人的事实陈述，agent 一律留空，交付止于可核验的 CI 链接。

## 场景二：bump 后构建/测试挂

占位符替换后整段下发，交付骨架与 status.json 门控不可裁剪：

```text
你现在在一个鸿蒙环境上，里面有个鸿蒙版的 Homebrew。我将 {formula} 这个 formula 升级后，它无法构建通过/测试通过，请帮我排查原因并修复。

构建命令：brew install -y -s -v {formula}
测试命令：brew test {formula}

修复完成后，把以下材料放到 {report_dir} 目录下：
1. 定位报告 report.md
2. 改过的 formula 文件
3. 所有补丁文件，包括原有的和新增的（如果存在）
4. 状态文件 status.json

最终输出的目录骨架应该是这样：
{report_dir}
  /report.md
  /status.json
  /Formula/{subdir}/{formula}
  /Patches/{formula}

status.json 的格式：
成功：{"status": "success"}
失败：{"status": "failure", "reason": "<一句话说明失败原因>"}
只有当你确认构建命令和测试命令都通过后，才允许写 success；否则必须写 failure 并说明原因。

注意事项：
1. 升级后对比上游版本formula，看看上游版本是不是引入了什么新改动需要同步进来：https://github.com/Homebrew/homebrew-core/raw/refs/heads/main/Formula/{subdir}/{formula}.rb。
2. 升级过程不要抛弃掉原有的鸿蒙适配补丁或者鸿蒙适配的构建参数（部分软件包可能有，不是每个软件包都一定有）。
3. 如果需要制作补丁或新增补丁，请参考 gcc、cmake、perl 这类 formula，看它们是怎么引入补丁文件的。
4. 这个报告用来展示在 PR 评论区，因此不宜过长。
5. report.md 会被嵌套在评论已有的一级标题之下，因此不要写总标题，也不要使用一级标题（#），正文直接从二级标题（##）开始分节，例如按 `## 现象`、`## 根因`、`## 修复`、`## 验证` 组织。
```

bump 窗口是免费复核期：继承来的守卫、caveat、shim 说不出当下失败证据的，这轮顺手删。

## 自有 tap（social4hyq/core，GitHub 线）

只放不合官方准入的 formula。相对场景一的增量：

1. 在独立 worktree 里改，主克隆分支会被别的会话切走；切分支前 `git fetch github main`（origin 是 atomgit 镜像，PR 开在 GitHub）。
2. 与官方同名的引用写全限定 `social4hyq/core/{formula}`，裸名会被静默劫持成官方版；查冲突用 `ls Formula/*/*.rb`，`brew info` 不可信。
3. formula 单文件自包含，禁 tap 级共享 Ruby。
4. 仍是单 commit，改动用 `git commit --amend` + `git push --force-with-lease`（官方那边用 `push -f` 压平）。merge 报 "base branch policy prohibits" 是 GITHUB_TOKEN 不触发 workflow 的已知假失败，用 `gh pr merge --merge --admin`。
5. bottle 内容变了要新 tag `-r<N>`，与 formula `revision` 是两套编号；bottle 回写会把 `bottle do` 落到文件顶部，同 PR 再改时归位到 `livecheck` 之后，否则 audit 必红 ComponentsOrder。
6. 本机试构建允许，但推 CI 前删两类本机痕迹：签名步骤（selfsign、binary-sign-tool、签名器 build dep），以及以 `uname -s`=HarmonyOS 为前提的分支。本机强制 ELF 签名才能 exec，CI 容器 `uname -s`=Linux 且构建期不验签——本机绿不等于 CI 绿。签名由流水线统一做，install() 不承载。
7. 真机装瓶后必跑 `brew test` + 真实负载；只断言文件存在会放过坏 bump。

## 上游化：把自有 tap 的 formula 送进官方 core

1. atomgit 是指南口径，gitcode 才是 v5 API 开 MR 的实测通路，`gh` 对两者都无效。
2. `POST https://gitcode.com/api/v5/repos/Harmonybrew/homebrew-core/pulls`，`head` 写 `"{fork_owner}:{branch}"`，分支必须先推 gitcode 上的 fork——atomgit fork 与 MR 体系不互通。token 传法变过（`private-token` header／`?access_token=` query），401 就换另一种。
3. 先去本机脚手架：签名步骤、指向本地文档的注释、tap 专属路径。cellar 一律 `:any_skip_relocation`，wrapper 用 `write_env_script`。
