---
name: npm-porting
description: Use when 一个 npm 包在 OpenHarmony/鸿蒙 PC 上装不上或跑不起来（缺平台二进制、dlopen 失败、process.platform 不认 openharmony、postinstall 报 Unsupported platform 等），需要判定移植路径或制作 @ohos-npm-ports 移植包时使用。也适用于「项目依赖了某原生 binding 包，如何接入鸿蒙可用版本」的接入问题。
compatibility: 构建验证用 CI 同款容器 ghcr.io/ohos-npm-ports/ci-runner:latest（OHOS rootfs，无 bun）；需 GitHub 与 registry.npmjs.org 网络（GHCR 不通换 ghcr.nju.edu.cn 镜像）；发布需社区仓权限。
metadata:
  source-repo: ../Skills/npm-porting
---

# npm-porting

权威规范每次现拉，不凭记忆代劳：

```sh
B=https://raw.githubusercontent.com/ohos-npm-ports/ohos-npm-ports/main/docs/zh-CN
for f in contributor/contributing contributor/port-spec contributor/porting-guide \
         contributor/build-frameworks contributor/verification maintainer/ci-pipeline; do
  echo "########## $f"; curl -s "$B/$f.md"; done
```

准入规则、ci-runner 容器环境、目录/命名/版本、build.sh 五步顺序、publish.sh 模式与 `--tag latest` 归属、patch 编号与纪律、自验证四要素、commit 规范、fork/PR 流程、二进制分发四方式与构建工具选型——全在里面。拉不到就停下问用户。

以下只写它没写的。

## 判定（命中即停）

1. 上游已认 openharmony（loader 分支或平台子包，`openharmony-arm64` 与 `linux-arm64-ohos` 两套名都试）→ 升版本，收工。
2. 社区已有 port（`registry.npmjs.org/-/v1/search?text=%40ohos-npm-ports`）→ overrides 复用。判定适配面前先 grep 包**实际 require 什么**，别信 dependencies（@playwright/mcp 只 require playwright-core）；已有 port 别默认能用，先实测（prisma-engines 5.1.1-2 连踩 3 个 bug：compat 常量值错、版本串错、npm pack 静默丢符号链接）。
3. 都没有 → 自建 port。

## 自建 port 的注意事项

1. native 产物一律源码构建；禁止搬运 musl prebuilt 只 patch loader（只许本地预验，不许发布）。
2. overrides 后其他平台必须照常工作——port 是团队共享 overrides 的 drop-in（Windows／Linux CI／鸿蒙同分支）。形态 = fork/重打包**整个**上游包，全平台 optionalDependencies 原样保留（os/cpu 不动）；build.sh 里模拟 `process.platform` 为 linux/darwin/win32，断言 loader 仍走上游解析。例外：平台槽位包（填 loader 动态拼出的、仅 openharmony 会解析的名字，如 `@parcel/watcher-openharmony-arm64`）本来就该 binding-only + `os: ["openharmony"]`，父包 override 仍走完整包。
3. 双包（主包 + 槽位包）publish.sh 两条 `cd` + 两条 publish，先槽位后主包（主包 optionalDependencies 才装上即解析）。第一条 cd（槽位产物目录）用 `$(dirname "$0")` 前缀自包含定位，第二条写 `cd ../<主包目录>`——第一条已改 cwd，再用 dirname 会解析进槽位目录。单包一律字面相对路径，`$(dirname "$0")` 只留给这一处。改完用假 `npm` shim 验证发布顺序与目录都对。
4. 发布失败的 run 若已发出某个包，修复 PR 必须把两包版本各 bump 一档再合并——同版本重发会 409 中断 `set -e` 链，主包永远发不出。
5. 生成物不落库：来源核对清单（`upstream-files.sha256` 之类）禁止提交，它从已钉死 sha256 的来源可推导。自验证在 build.sh 内现场做——解包后打补丁前记录全文件哈希、组装产物后 diff（剔除补丁允许改写的文件），把「补丁只允许碰指定文件」变成硬不变量。
6. 消费侧冒烟先 `npm pack` 成 tarball 再 `file:` 装（`file:` 目录 = symlink，不装依赖）。双包形态：两包各自 pack、`--force` 同装干净工程（槽位包 os/cpu 限定，容器直装必 EBADPLATFORM），从主包 loader 的解析上下文 `require.resolve` 槽位包并断言 `.node` 在位；`.node` 的 dlopen 加载归真机，ELF/接线/loader marker 断言归 build.sh，smoke 不重复。
7. 非必要不注释：默认零注释，要写就单句只解释「现在为什么不显然」；禁止历史叙事、先例指针、决策过程——那些属于 PR 描述。措辞按事实，`.node` 的 dlopen 依赖写「HarmonyOS 系统库」，不展开 CI 镜像里的 NDK stub 机制。
8. 深水区（缺符号 weak 方案／SIGSYS／dlopen 命名空间／工具链行为）查 `reference/ohos-porting-notes.md`；实物模板看社区仓 `ports/`（lightningcss 最小完整、nx 复杂例、playwright-mcp 零编译例）。

## PR 注意事项

1. fork 分支 `port/<name>-<version>`，不碰 `.github/workflows/`。
2. 不要顺手改 README.md——「已收录的包」表是所有 port PR 的冲突热点（同位加行，串行合并时每个先合的 PR 都让其余 open PR 立即变 DIRTY，#46–#49 实测连环冲突三轮 rebase）；收录行留给维护者合入后补，或单独开 docs PR 一次补多行。
3. 别在分支上 `git add -A` 扫入本地工作目录（#41：31 个 `logs/` 文件进了 PR）；误加用 `git rm -r --cached <dir>` 摘除，并写 `.git/info/exclude` 防再犯。
4. 恰好一个 commit（amend + force-push，基底取最新 main）；amend 也要带 `-c user.name/email`，身份不齐用 `--reset-author`；邮箱必须是 GitHub 账号注册过的（163.com、users.noreply.github.com 可以，gitcode noreply 未注册会显示「未认领提交者」）；不得有任何 Agent 痕迹。
5. 正文只写当前状态的事实（形态／原因／构建／验证／盲区／用法），版本变迁用「版本 `N→M`」一行带过，不写内嵌拆分历史、fork 验证历程、PR 交叉引用；模板勾选清单不勾没做过的项。
6. 推送前自检，不绿不推：

```sh
git fetch origin
test "$(git merge-base origin/main HEAD)" = "$(git rev-parse origin/main)"  # 基底=最新 main
test "$(git rev-list --count origin/main..HEAD)" -le 1                      # 单 commit；0=已并入
git log --format='%an|%ae|%cn|%ce' origin/main..HEAD \
  | awk -F'|' 'NF&&($1!=$3||$2!=$4){bad=1} END{exit bad}'                   # author=committer
git log --format='%(trailers:key=Co-Authored-By,valueonly)%B' origin/main..HEAD \
  | grep -iE 'co-authored-by|generated with|🤖'                             # 必须无输出
```

## 用户侧接入

1. `"<pkg>": "npm:@ohos-npm-ports/<pkg>"`；overrides 映射进**上游裸名槽位**（自引用包旁装必挂：nx、biome、esbuild）；pnpm `catalog:` 键用裸名、选择器用父包名；工程有 minimumReleaseAge 门时加 `minimumReleaseAgeExclude`。
2. npm/pnpm 工程接 `.node` 需 ohos-signpost postinstall 签名；bun install 已内置。
3. npmjs 直连（npmmirror 有新包同步延迟）；容器下载超时先原样重试；port 不自动跟上游版本。
4. package.json 的 patch 以「已发布包内容 + 必要变更」为目标态 diff，理想形态仅 name/version/repository 三字段——别顺手改仍为真的文案（description 类）。
