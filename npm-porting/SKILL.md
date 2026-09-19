---
name: npm-porting
description: Use when 一个 npm 包在 OpenHarmony/鸿蒙 PC 上装不上或跑不起来（缺平台二进制、dlopen 失败、process.platform 不认 openharmony、postinstall 报 Unsupported platform 等），需要判定移植路径或制作 @ohos-npm-ports 移植包时使用。也适用于「项目依赖了某原生 binding 包，如何接入鸿蒙可用版本」的接入问题。
compatibility: 构建验证用 CI 同款容器 ghcr.io/ohos-npm-ports/ci-runner:latest（OHOS rootfs，无 bun）；需 GitHub 与 registry.npmjs.org 网络（GHCR 不通换 ghcr.nju.edu.cn 镜像）；发布需社区仓权限。
metadata:
  source-repo: ../Skills/npm-porting
  updated: "2026-09-17"
---

# npm-porting

移植 npm 包到 OHOS，发布为 `@ohos-npm-ports/<name>`。native 产物一律源码构建；禁止搬运 musl prebuilt 只 patch loader（只许本地预验）。

## 判定树（命中即停）

1. 上游已认 openharmony（loader 分支 / 平台子包，`openharmony-arm64` 与 `linux-arm64-ohos` 两套名都试）→ 直接升版本
2. 社区已有 port（`registry.npmjs.org/-/v1/search?text=%40ohos-npm-ports`）→ overrides 复用。判定适配面前先 grep 包实际 require 什么，别信 dependencies（@playwright/mcp 只 require playwright-core）；已有 port 别默认能用——先真机/容器实测（prisma-engines 5.1.1-2 连踩 3 个 bug：compat 常量值错、版本串错、npm pack 静默丢符号链接）
3. 都没有 → 自建 port ↓

## 硬性要求：overrides 后其他平台照常工作

port 是团队共享 overrides 的 drop-in（Windows / Linux CI / 鸿蒙同分支）。禁止 binding-only + `os: ["openharmony"]` 当替代包（其他平台装上即坏）；正确形态 = fork/重打包整个上游包，全平台 optionalDependencies 原样保留（os/cpu 不动）；删 install 脚本前确认其他平台安装与加载不受影响；build.sh 模拟 `process.platform` 为 linux/darwin/win32 断言 loader 仍走上游解析。**例外**：平台槽位包（填 loader 动态拼出的、仅 openharmony 会解析的名字，如 `@parcel/watcher-openharmony-arm64`）不受此限——binding-only + `os: ["openharmony"]` 正是它的正确形态，父包 override 仍走完整包。

## 社区仓 contributor 规范速查

权威细节在 ohos-npm-ports 仓库 `docs/zh-CN/contributor/`（contributing / port-spec / porting-guide / build-frameworks / verification）+ `docs/zh-CN/maintainer/ci-pipeline.md`。硬规则：

- **环境**：构建/调试一律在 CI 同款容器 `ghcr.io/ohos-npm-ports/ci-runner:latest` 做，不在宿主机直接跑 build.sh。镜像 = OHOS rootfs + brew(node/python/devel-base/git/rust/bash)，**没有 bun**——build.sh 冒烟对 bun 等真机专属工具 `command -v` 门控跳过、真机补验。容器通过 ≠ 真机可部署（HarmonyOS 签名/沙箱比容器严格），两端都要验。硬件须 arm64 原生
- **目录**：`ports/<port>/<裸上游版本>/{build.sh,publish.sh,patchs/}`；scoped 包目录名展开（`@prisma/client`→`prisma-client`）；多版本并存时只有最新线的 publish.sh 打 `--tag latest`，旧线修订必须换 tag（如 `--tag legacy-0.4`——latest 谁发得晚是谁，跟 semver 无关）；平台槽位开独立 `ports/<port>-openharmony-arm64/<version>/`
- **build.sh**：`#!/bin/sh` + `set -e`，纯 POSIX（禁 bash/zsh 扩展；变量名禁 `status`——zsh 只读）；**结构参照 `ports/typescript/7.0.2/build.sh`**：顶部常量（PKG_NAME/PKG_VERSION/PORTS_VERSION/WORK_DIR/BUILD_DIR）→ 函数拆分 `do_deps` / `do_fetch` / `do_build` / `do_package` / `do_test`（按 port 实际阶段取舍细分，职责单一）→ 末尾顺序调用；阶段横幅 `echo "=== fetch: …"`；全部工作在 BUILD_DIR 下、发布目录为其子目录；跨函数切目录用绝对路径。顺序 = 下载(**带 sha256 校验值**，新增/升级 port 硬性要求) → patch(打完 grep marker) → 编译/重打包 → 组装发布目录 + 写 package.json + 原生文件签名 → 自验证；build.sh 不跑 npm publish
- **publish.sh**：固定模式，单行直写 `cd <产物目录>`（字面相对路径，如 `cd build/pkg`）后跟 `npm publish --tag latest --access public`。CI（`ci.yml`）publish 步骤先 `cd "${{ matrix.dir }}"` 再 `./publish.sh`，cwd 保证是 port 目录，**单包一律用字面相对路径，不要 `$(dirname "$0")`**——自包含定位只留给下方双包槽位的第一条 cd；仓库已合并 port 绝大多数也是字面相对。CI（port-lint）对 publish.sh 只查存在性、`sh -n` 语法、scope 字符串，不解析 cd 目标，但保持简单两行结构方便人读。无 provenance
- **package.json**：name→`@ohos-npm-ports/<port>`、version→`<上游版本>-<修订号>`（修订号只在补丁本身改进时 +1；升上游版本新开 version 目录、修订号从 -1 起）、repository.url→本仓库；**有上游 manifest 可改时一律 patch 载体**（`000N-update-package-json.patch`）——delta 自证（理想形态仅 name/version/repository 三字段），reviewer 一眼可见改动面，也防止顺手改 description 等仍为真的文案（skill 用户侧接入同理：以「已发布包内容 + 必要变更」为目标态）；静态 cp / heredoc 生成只用于无上游 manifest 的场景（平台槽位包、commit-pin 原生构建如 prisma-engines）；不改原作者与许可证；上游 `packageManager` 字段指定的包管理器若 OHOS 无发布必须删
- **ports 目录只存手写脚本与补丁，生成物不落库**：完整性/来源核对清单（如 upstream-files.sha256）禁止提交——它从已钉死 sha256 的来源可推导，属噪音；自验证在 build.sh 内现场完成：解包后打补丁前记录全文件哈希、组装产物后 diff（剔除被补丁允许改写的文件），等效且更强——把「补丁只允许碰指定文件」变成硬不变量
- **patch**：`NNNN-短横线描述.patch`；**每个 patch 必须被 build.sh 实际应用**（逐条 `patch -p1 <` 或 `for p in ../patchs/*.patch` glob）——孤立 patch 被 port-lint 阻断；改已有 patch 重生成 diff，禁手改 `@@`（打完 grep 标记，退出码不可信）
- **port-lint 阻断项**：build.sh/publish.sh 存在且 `sh -n` 过；build.sh 无 `npm publish`（注释行除外）；patchs/*.patch 全被 build.sh 按名引用；port 文件任一处 grep 得到 `@ohos-npm-ports/`。警告项：版本号字符串应出现在 build.sh；build.sh 应有自验证痕迹（grep -q / node -e / node --check / readelf）
- **自验证四要素**（verification.md，非选做）：包名/版本断言；readelf AArch64 + `.codesign`；入口**真实 require 加载**（node --check 只验语法不算）；补丁加的 openharmony loader 分支 grep 命中产物文件
- **commit 规范**（CI lint-commit-messages 查 ports/** commit 首行）：新增 `<port>: add port <version>`；修订号 `<port>: bump port revision to <version>`；升级 `<port>: bump to <version> ...`；其余 `<port>: <action>`。README/CI 改动不受限
- **PR 正文按仓库 PULL_REQUEST_TEMPLATE**：勾选清单（commit 规范 / **已在 ci-runner 容器内跑通 build.sh** / name+version / .codesign 签名 / patch 无孤立 / 未改作者与许可证 / 不破坏其他平台）+ 类型多选 + 简述（新增/升级附上游 changelog 链接）；**不勾没做过的项**。模板后可再附「为什么/构建方式/验证/使用方式」小节
- **流程**：fork → 自己仓 Actions 跑通 ci.yml（publish 无 NPM_TOKEN 报错是预期）→ 提 PR → 合并后 CI 构建发包
- **分发方式**（build-frameworks.md，按 loader 定）：主包内嵌固定路径 / `prebuilds/`+node-gyp-build / 平台子包 optionalDependencies；**禁止保留安装时远程下载**（改为构建阶段取得随包分发）；独立可执行文件不经过 require，重点验架构/运行路径/权限/签名

## port 规范

- `ports/<name>/<裸版本>/{build.sh, publish.sh, patchs/}`；版本 = 上游 base + `-N`；命名 `@scope/name` → `scope-name`；多版本一 PR 多目录，自修 bump `-N`；配套平台槽位包（父包+槽位双包，如 parcel-watcher）→ 同一 PR 同 commit、版本同号、组合修订同步 bump
- 发布不带 provenance：upstream 的 `publishConfig.provenance` 在 0001 删掉；`npm publish --tag latest --access public`
- 构建模型按包选：cargo 原生（rustc host 即 ohos，最常见）/ zig 交叉 musl（ohos target 不可用）/ node-gyp（llvm@21 + CC/CXX）/ Go 静态 / 零编译重打包（纯 JS）/ 双树。上游 loader 已认 openharmony → 产物放第一候选路径零 patch；`@napi-rs/cli` 2.x 不认 ohos → cargo build + 改名；懒加载/可选依赖让 CI 裁决，红了再补。bun `--compile` 消费（loader 动态拼名 require 平台包）时：bundler 只内嵌静态引用过的模块、运行时按 specifier 查表——槽位包 main 须 JS shim（`module.exports = require('./xx.node')`；`.node` 直出被当 asset，拼名 MISS），消费方会打包的入口加 `try { require('<槽位名>') } catch {}` 即命中，父包 optionalDependencies alias（os 过滤，失败仅降级）覆盖普通安装
- 双包 `publish.sh` 两条直发、先槽位后主包（主包 optionalDependencies 指向槽位包）。第一条 cd（槽位目录）用 `$(dirname "$0")/…` 前缀自包含定位，禁止引用前文变量（CI 从 port 目录 `./publish.sh` 调用，但自包含写法让人从任意 cwd 手动跑也不迷路）；第二条 cd（主包）用 `cd ../<主包目录>`——不能再走 `$(dirname "$0")` 相对形式（第一条 cd 已改 cwd，会解析进槽位目录）。改完用假 `npm` shim 验证发布顺序与目录都要对（typescript port 先例）
- 发布失败的 run 若已发出某个包，修复 PR 必须把两包版本 bump 一档再合并——同版本重发会 409 中断 `set -e` 链，主包永远发不出
- **非必要不注释**：默认零注释，要写就单句只解释「现在为什么不显然」；禁止历史叙事、先例指针、决策过程（那些属于 PR 描述）；措辞按事实——.node 的 dlopen 依赖写「HarmonyOS 系统库」，不写 glibc/Ubuntu 容器框架，不展开 CI 镜像里的 NDK stub 机制（「不测就不测」）

## build.sh 必做

1. 下载固定来源 + **sha256 校验值**（新增/升级 port 硬性）；tag tarball + `patch -p1`（toybox patch 静默 no-op，打完 grep marker）
2. `npm install --ignore-scripts`（postinstall 常硬失败）；`export PATH="$(pwd)/node_modules/.bin:$PATH"`
3. `llvm-strip --strip-all` → `binary-sign-tool sign -selfSign 1`（报 already has .codesign 先 strip，patchelf 前同理）。dlopen 库（.node/.so）**不需要** `chmod +x`，仅 CLI 二进制要
4. 验证全进 build.sh：包名 / `node --check` / openharmony marker / readelf AArch64 + `.codesign` / optionalDependencies / 真函数调用冒烟（只验 ELF 头不算）
5. 消费侧冒烟先 `npm pack` 成 tarball 再 `file:` 装（`file:` 目录 = symlink，不装依赖）。双包形态：两包各自 pack 成 tgz、`--force` 同装干净工程（槽位包 os/cpu 限定，容器直装必 EBADPLATFORM），从主包 loader 的解析上下文 `require.resolve` 槽位包、断言 `.node` 在位——`.node` 的 dlopen 加载不在容器验证（真机范围）；ELF/接线/loader marker 断言归 build.sh do_test，smoke 不重复
6. 跨平台模拟回归进 build.sh（见硬性要求）

## PR 纪律

- fork 分支 `port/<name>-<version>` → PR 到 [ohos-npm-ports/ohos-npm-ports](https://github.com/ohos-npm-ports/ohos-npm-ports)；标题 `<name>: add port <version>`；不碰 `.github/workflows/`；合并后 CI 自动发布。**不要顺手改 README.md**——「已收录的包」表是所有 port PR 的冲突热点（同位加行，串行合并时每个先合的 PR 都让其余 open PR 立即变 DIRTY，#46–#49 实测连环冲突三轮 rebase）；收录行留给维护者合入后补，或单独开 docs PR 一次补多行
- **恰好一个 commit**（amend + force-push，基底取最新 main）；amend 也要带 `-c user.name/email`，身份不齐用 `--reset-author`；邮箱必须是 GitHub 账号注册过的（163.com / users.noreply.github.com ✅；gitcode noreply ❌ 未注册，会显示「未认领提交者」）；不得有 Agent 痕迹（无 Co-Authored-By、无 Generated-with）
- 分支上别 `git add -A` 扫入本地工作目录（#41 实例：31 个 `logs/` 文件进了 PR）；误加用 `git rm -r --cached <dir>` 摘除，并以 `.git/info/exclude` 防再犯
- 正文只写当前状态的事实（形态/原因/构建/验证/盲区/用法）；版本变迁用「版本 `N→M`」一行带过，不写内嵌/拆分历史叙事、fork 验证历程、先例与 PR 交叉引用
- 推送前自检（不绿不推）：
  ```sh
  git fetch origin
  test "$(git merge-base origin/main HEAD)" = "$(git rev-parse origin/main)"  # 基底=最新 main
  test "$(git rev-list --count origin/main..HEAD)" -le 1                      # 单 commit；0=已并入
  git log --format='%an|%ae|%cn|%ce' origin/main..HEAD \
    | awk -F'|' 'NF&&($1!=$3||$2!=$4){bad=1} END{exit bad}'                   # author=committer
  git log --format='%(trailers:key=Co-Authored-By,valueonly)' origin/main..HEAD \
    | grep -q . && echo Agent痕迹                                  # 必须无输出
  git log --format='%B' origin/main..HEAD \
    | grep -iqE 'generated with|🤖' && echo Agent痕迹              # 必须无输出
  ```

## 用户侧接入

- `"<pkg>": "npm:@ohos-npm-ports/<pkg>"`；overrides 映射进**上游裸名槽位**（自引用包旁装必挂：nx/biome/esbuild）；pnpm `catalog:` 键用裸名、选择器用父包名；minimumReleaseAge 门加 `minimumReleaseAgeExclude`
- npm/pnpm 工程接 `.node` 需 ohos-signpost postinstall 签名；bun install 已内置
- npmjs 直连（npmmirror 有新包同步延迟）；容器下载超时先原样重试；port 不自动跟上游版本；旧 `@ohos-ports` scope 已停发，lockfile 迁移全量换名；package.json patch 重生成以「已发布包内容 + 必要变更」为目标态 diff，别顺手改仍为真的文案（description 类）

深水区（缺符号 weak 方案 / SIGSYS / dlopen 命名空间 / 工具链行为）→ `reference/ohos-porting-notes.md`；实物模板 → 社区仓 `ports/`（lightningcss 最小完整 / nx 复杂例 / playwright-mcp 零编译例）
