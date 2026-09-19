---
name: ohos-frontend-upgrade
description: Use when 一个在 Windows/Linux 等平台正常构建运行的前端或 Node.js 工程，在鸿蒙 HarmonyOS/OpenHarmony 上 npm install / build / run 受阻（缺平台二进制、.node 未签名 dlopen 拒载、install 脚本硬失败、tsgo/lightningcss/esbuild 类报错）——通过升级依赖到原生支持的新版本、或 overrides 到 @ohos-npm-ports 社区 port，让工程在多个 OS 平台同时可构建运行。移植单个包并发布 @ohos-npm-ports 走 npm-porting，不在本 skill 范围。
compatibility: 目标为多平台不回归（Windows/Linux/macOS 原平台 + HarmonyOS PC 真机）；配方为 vite 系（6 工程 2026-09 实测全绿），webpack 系未实测；需 registry.npmjs.org 网络。
metadata:
  source-repo: ../Skills/ohos-frontend-upgrade
  updated: "2026-09-17"
---

# ohos-frontend-upgrade

分工：npm-porting 是「移植单个包 → 发布 `@ohos-npm-ports`」的生产侧；本 skill 是**消费侧**——输入一个在 Windows/Linux 等平台正常构建运行的前端或 Node.js 工程，通过升级依赖新版本或 overrides 到社区 port，消除其在 HarmonyOS 上的构建/运行障碍。**验收标准不是「OHOS 单平台能跑」，而是「升级后的工程在包括 HarmonyOS 在内的多个 OS 平台同时可构建运行」**——其他平台行为不回归由 @ohos-npm-ports 包的移植质量保证（port 发布走容器构建 + 真机冒烟 + 签名门禁），本 skill 负责选对版本与接线方式。不产出新 port。

## 判定树（命中即停）

1. 查上游最新版是否原生支持 openharmony → 直接升上去用。napi-rs 系（rolldown/oxc 等）平台子包命名不统一，`openharmony-arm64` 与 `linux-arm64-ohos` 两套都试；vite 8 起 rolldown 内核原生支持，vite 5/6 的 esbuild 障碍已被上游消灭。此路线一份依赖全平台通用，无回归面，永远首选
2. 上游没有 → 查 `@ohos-ports` 与 `@ohos-npm-ports` 两个 scope 的社区 port → overrides / `npm:` alias 复用；复用前 `npm view @ohos-npm-ports/<pkg> versions` 确认 port 版本满足工程要求，并核对 port 的 manifest delta（上游 manifest 只应改 name/version/repository）与其跨平台产物（原生 binding 类 port 应带全平台二进制或平台门控补丁）
3. 工程 node_modules 含 `.node` 原生二进制 → 装 ohos-signpost 为 devDependency 并在 postinstall 执行；bun install 的工程不需要，bun 内置签名

## 多平台不回归原则

- **overrides 对所有安装生效，不分平台**——override 到一个只剩 OHOS 产物的键会让 win/linux 一起坏。安全形态有两种：① port 包是上游完整重打包（其余文件与原包逐字一致，delta 仅 name/version/repository），原生 binding 类还带全平台 `.node` 或补丁按 `process.platform === "openharmony"` 门控——win/linux 走原代码路径，行为不变；② 平台槽位包（名字带 `-openharmony-arm64`）走 optionalDependencies + os 过滤，非 OHOS 平台安装失败仅降级、不报错
- **升级版本选「全平台都支持的最低新版本」**：只修复 OHOS 障碍的最小升级优先于顺手大版本跳跃；跳大版本（如 vite 5→8）要把工程原本平台加入回归验证，不能只在 OHOS 上验
- **bun 工程同样适用**：bun 支持 overrides（catalog 工程注意 override 键必须裸名，版本限定键匹配不上）；bun 内置 `.node` 签名，免 ohos-signpost
- 接入后工程应只剩一份依赖树——不要在 OHOS 侧维护单独的 lockfile/依赖分支

## 已验证配方（vite 系 6 工程全绿）

react18+antd6 / react18+arco / react18+mui / vue3.5+element-plus / vue3.5+tinyvue / vue3.5+naive-ui 全部按以下组合 npm install + build 绿：

- vite `^8.2.2` + `@vitejs/plugin-react` `^6.1.1`（vue 工程换 `@vitejs/plugin-vue` `^6.0.8`）
- 顶层 overrides：`{"lightningcss": "npm:@ohos-ports/lightningcss@1.33.0-1"}`——lightningcss 上游 1.33.0 无 openharmony 子包，必须走社区 port（已预签）
- `ohos-signpost` `^1.1.1` 进 devDependencies + `"postinstall": "ohos-signpost"`；rolldown binding 实测需签名，lightningcss port 已预签
- typescript 用 5.9（type-check 进 build：react `tsc --noEmit` / vue `vue-tsc --noEmit`）
- 已确认原生可用的平台包：`@rolldown/binding-openharmony-arm64`、`@oxc-transform-react/binding-openharmony-arm64`（@vitejs/plugin-react@6 依赖）、`@esbuild/openharmony-arm64`（esbuild 0.28.x）

以上组合的跨平台性由构造保证：vite/plugin/typescript 全部是上游官方版本（win/linux 本就走这些版本），唯一 override 的 lightningcss 是上游完整重打包 port（其余文件与官方包逐字一致，仅新增 openharmony 产物）——overrides 全局生效也不回归原平台

## OHOS 工程坑位

- typescript@7（tsgo）缺 `@typescript/typescript-openharmony-arm64` → 用 typescript 5.9
- Biome 无 OHOS 预编译 → 风格校验用 ESLint 或人工
- systeminformation 的 os 白名单不含 openharmony → `npm install` 需 `--force`
- 某些包 install 脚本在 OHOS 硬失败 → `npm install --ignore-scripts`；注意这会把 ohos-signpost 的 postinstall 一并跳过，装完手动补 `npx ohos-signpost`
- `/tmp` 只读 → 临时文件落工程目录
- 华为系统浏览器（ArkWeb）file:// 拒载 → 冒烟用 `vite preview` + curl，或海泰浏览器

## 验收清单（不绿不算完成）

1. `npm install` 零报错
2. `npm run build` 绿（含 tsc / vue-tsc）
3. `vite preview` 起服后 curl HTTP 200
4. node_modules 内 `.node` 文件均已签名（ohos-signpost 输出确认，或 readelf 查 `.codesign` 段）
5. **多平台回归**：升级/overrides 后原平台（Windows/Linux）`npm install` + build 仍绿——工程有 CI 就加/跑 OS matrix；没有 CI 至少在原平台重跑一遍 install + build，确认 overrides 没把原平台依赖树改坏

```sh
npm install                 # ① 零报错
npm run build               # ② 全绿
npm run preview &           # ③ 起服
curl -sI http://localhost:4173 | head -1    #   期待 HTTP/1.1 200（vite preview 默认端口）
find node_modules -name '*.node' \
  | xargs -n1 sh -c 'readelf -S "$0" | grep -q ".codesign" || echo "未签名: $0"'   # ④ 无输出 = 全部已签
```

## 边界

- 配方基于 vite 系；webpack 系未实测（terser 纯 JS 无碍，但需自行核查其原生依赖链）
- 遇到配方外报错：先按判定树走，再把新结论回填本 skill
