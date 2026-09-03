---
name: npm-porting
description: Use when 一个 npm 包在 OpenHarmony/鸿蒙 PC 上装不上或跑不起来（缺平台二进制、dlopen 失败、process.platform 不认 openharmony、postinstall 报 Unsupported platform 等），需要判定移植路径或制作 @ohos-npm-ports 移植包时使用。也适用于「项目依赖了某原生 binding 包，如何接入鸿蒙可用版本」的接入问题。
compatibility: 构建验证用 CI 同款容器 ghcr.io/hqzing/dockerharmony；需 GitHub 与 registry.npmjs.org 网络；发布需社区仓权限。
metadata:
  source-repo: ../Skills/npm-porting
  updated: "2026-09-02"
---

# npm-porting

移植 npm 包到 OHOS，发布为 `@ohos-npm-ports/<name>`。native 产物一律源码构建；禁止搬运 musl prebuilt 只 patch loader（只许本地预验）。

## 判定树（命中即停）

1. 上游已认 openharmony（loader 分支 / 平台子包，`openharmony-arm64` 与 `linux-arm64-ohos` 两套名都试）→ 直接升版本
2. 社区已有 port（`registry.npmjs.org/-/v1/search?text=%40ohos-npm-ports`）→ overrides 复用。判定适配面前先 grep 包实际 require 什么，别信 dependencies（@playwright/mcp 只 require playwright-core）
3. 都没有 → 自建 port ↓

## 硬性要求：overrides 后其他平台照常工作

port 是团队共享 overrides 的 drop-in（Windows / Linux CI / 鸿蒙同分支）。禁止 binding-only + `os: ["openharmony"]` 当替代包（其他平台装上即坏）；正确形态 = fork/重打包整个上游包，全平台 optionalDependencies 原样保留（os/cpu 不动）；删 install 脚本前确认其他平台安装与加载不受影响；build.sh 模拟 `process.platform` 为 linux/darwin/win32 断言 loader 仍走上游解析。**例外**：平台槽位包（填 loader 动态拼出的、仅 openharmony 会解析的名字，如 `@parcel/watcher-openharmony-arm64`）不受此限——binding-only + `os: ["openharmony"]` 正是它的正确形态，父包 override 仍走完整包。

## port 规范

- `ports/<name>/<裸版本>/{build.sh, publish.sh, patchs/}`；版本 = 上游 base + `-N`；命名 `@scope/name` → `scope-name`；多版本一 PR 多目录，自修 bump `-N`；配套平台槽位包（父包+槽位双包，如 parcel-watcher）→ 同一 PR 同 commit、版本同号、组合修订同步 bump
- 发布不带 provenance：upstream 的 `publishConfig.provenance` 在 0001 删掉；`npm publish --tag latest --access public`
- 构建模型按包选：cargo 原生（rustc host 即 ohos，最常见）/ zig 交叉 musl（ohos target 不可用）/ node-gyp（llvm@21 + CC/CXX）/ Go 静态 / 零编译重打包（纯 JS）/ 双树。上游 loader 已认 openharmony → 产物放第一候选路径零 patch；`@napi-rs/cli` 2.x 不认 ohos → cargo build + 改名；懒加载/可选依赖让 CI 裁决，红了再补。bun `--compile` 消费（loader 动态拼名 require 平台包）时：bundler 只内嵌静态引用过的模块、运行时按 specifier 查表——槽位包 main 须 JS shim（`module.exports = require('./xx.node')`；`.node` 直出被当 asset，拼名 MISS），消费方会打包的入口加 `try { require('<槽位名>') } catch {}` 即命中，父包 optionalDependencies alias（os 过滤，失败仅降级）覆盖普通安装
- **非必要不注释**：默认零注释，要写就单句只解释「现在为什么不显然」；禁止历史叙事、先例指针、决策过程（那些属于 PR 描述）

## build.sh 必做

1. tag tarball + `patch -p1`（toybox patch 静默 no-op，打完 grep marker）
2. `npm install --ignore-scripts`（postinstall 常硬失败）；`export PATH="$(pwd)/node_modules/.bin:$PATH"`
3. `llvm-strip --strip-all` → `binary-sign-tool sign -selfSign 1`（报 already has .codesign 先 strip，patchelf 前同理）。dlopen 库（.node/.so）**不需要** `chmod +x`，仅 CLI 二进制要
4. 验证全进 build.sh：包名 / `node --check` / openharmony marker / readelf AArch64 + `.codesign` / optionalDependencies / 真函数调用冒烟（只验 ELF 头不算）
5. 消费侧冒烟先 `npm pack` 成 tarball 再 `file:` 装（`file:` 目录 = symlink，不装依赖）
6. 跨平台模拟回归进 build.sh（见硬性要求）

## PR 纪律

- fork 分支 `port/<name>-<version>` → PR 到 [ohos-npm-ports/ohos-npm-ports](https://github.com/ohos-npm-ports/ohos-npm-ports)；标题 `<name>: add port <version>`；不碰 `.github/workflows/`；合并后 CI 自动发布，README「已收录的包」补一行
- **恰好一个 commit**（amend + force-push，基底取最新 main）；amend 也要带 `-c user.name/email`，身份不齐用 `--reset-author`；不得有 Agent 痕迹（无 Co-Authored-By、无 Generated-with）
- 正文——新增：`## 包信息`（表）/ `## 为什么` / `## 构建方式`（补丁逐条）/ `## 验证` / `## 使用方式`（json）；修订：`## 包信息`（版本 `N→M`）/ `## 改动` / `## 验证`
- 推送前自检（不绿不推）：
  ```sh
  git fetch origin
  test "$(git merge-base origin/main HEAD)" = "$(git rev-parse origin/main)"  # 基底=最新 main
  test "$(git rev-list --count origin/main..HEAD)" -le 1                      # 单 commit；0=已并入
  git log --format='%an|%ae|%cn|%ce' origin/main..HEAD \
    | awk -F'|' 'NF&&($1!=$3||$2!=$4){bad=1} END{exit bad}'                   # author=committer
  git log --format='%(trailers:key=Co-Authored-By,valueonly)%B' origin/main..HEAD \
    | grep -iqE '^.|generated with|🤖' && echo Agent痕迹                       # 必须无输出
  ```

## 用户侧接入

- `"<pkg>": "npm:@ohos-npm-ports/<pkg>"`；overrides 映射进**上游裸名槽位**（自引用包旁装必挂：nx/biome/esbuild）；pnpm `catalog:` 键用裸名、选择器用父包名；minimumReleaseAge 门加 `minimumReleaseAgeExclude`
- npm/pnpm 工程接 `.node` 需 ohos-signpost postinstall 签名；bun install 已内置
- npmjs 直连（npmmirror 有新包同步延迟）；容器下载超时先原样重试；port 不自动跟上游版本；旧 `@ohos-ports` scope 已停发，lockfile 迁移全量换名；package.json patch 重生成以「已发布包内容 + 必要变更」为目标态 diff，别顺手改仍为真的文案（description 类）

深水区（缺符号 weak 方案 / SIGSYS / dlopen 命名空间 / 工具链行为）→ `reference/ohos-porting-notes.md`；实物模板 → 社区仓 `ports/`（lightningcss 最小完整 / nx 复杂例 / playwright-mcp 零编译例）
