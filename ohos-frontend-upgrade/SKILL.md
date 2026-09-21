---
name: ohos-frontend-upgrade
description: Use when 一个在 Windows/Linux 等平台正常构建运行的前端或 Node.js 工程，在鸿蒙 HarmonyOS/OpenHarmony 上 npm install / build / run 受阻（缺平台二进制、.node 未签名 dlopen 拒载、install 脚本硬失败、tsgo/lightningcss/esbuild 类报错）——通过升级依赖到原生支持的新版本、或 overrides 到 @ohos-npm-ports 社区 port，让工程在多个 OS 平台同时可构建运行。移植单个包并发布 @ohos-npm-ports 走 npm-porting，不在本 skill 范围。
compatibility: 目标为多平台不回归（Windows/Linux/macOS 原平台 + HarmonyOS PC 真机）；配方为 vite 系（6 工程 2026-09 实测全绿），webpack 系未实测；需 registry.npmjs.org 网络。
metadata:
  source-repo: ../Skills/ohos-frontend-upgrade
---

# ohos-frontend-upgrade

消费侧：把一个在 Windows/Linux 上正常构建的前端或 Node.js 工程，改到 HarmonyOS 上也能 install/build/run。生产侧（移植单个包并发布 `@ohos-npm-ports`）走 npm-porting，本 skill 不产出新 port。

验收标准不是「OHOS 单平台能跑」，而是**升级后的工程在包括 HarmonyOS 在内的多个 OS 平台同时可构建运行**。

## 判定（命中即停）

1. 上游最新版已原生支持 openharmony → 升上去。napi-rs 系平台子包命名不统一，`openharmony-arm64` 与 `linux-arm64-ohos` 两套都试；vite 8 起 rolldown 内核原生支持，vite 5/6 的 esbuild 障碍上游已消灭。一份依赖全平台通用、无回归面，永远首选。
2. 上游没有 → 查 `@ohos-npm-ports` scope 复用（overrides 或 `npm:` alias）。复用前 `npm view @ohos-npm-ports/<pkg> versions` 确认版本够用，并核对它的 manifest delta（只应改 name/version/repository）与跨平台产物。
3. node_modules 里有 `.node` → `ohos-signpost` 进 devDependencies + `"postinstall": "ohos-signpost"`；bun install 的工程免，bun 内置签名。

## 不回归其他平台

1. **overrides 对所有安装生效，不分平台**——override 到一个只剩 OHOS 产物的键会让 win/linux 一起坏。安全形态只有两种：① 上游完整重打包的 port（delta 仅 name/version/repository，原生 binding 类还带全平台 `.node` 或按 `process.platform === "openharmony"` 门控，其他平台走原代码路径）；② 平台槽位包（名字带 `-openharmony-arm64`）走 optionalDependencies + os 过滤，非 OHOS 平台安装失败仅降级、不报错。
2. 升级选「全平台都支持的最低新版本」：只修 OHOS 障碍的最小升级，优先于顺手跳大版本；真要跳（如 vite 5→8）就把工程原本平台一并加进回归验证。
3. bun 工程同样适用；catalog 工程的 override 键必须裸名，版本限定键匹配不上。
4. 工程只留一份依赖树，不在 OHOS 侧维护单独的 lockfile 或依赖分支。

## 已验证配方（vite 系 6 工程全绿）

react18+antd6 / react18+arco / react18+mui / vue3.5+element-plus / vue3.5+tinyvue / vue3.5+naive-ui，均按以下组合 install + build 绿：

- vite `^8.2.2` + `@vitejs/plugin-react` `^6.1.1`（vue 工程换 `@vitejs/plugin-vue` `^6.0.8`）
- 顶层 overrides `{"lightningcss": "npm:@ohos-npm-ports/lightningcss@1.33.0-1"}`——上游 1.33.0 无 openharmony 子包，port 已预签
- `ohos-signpost` `^1.1.1` + `"postinstall": "ohos-signpost"`（rolldown binding 实测需签名）
- typescript 5.9，type-check 进 build（react `tsc --noEmit` / vue `vue-tsc --noEmit`）
- 已确认原生可用：`@rolldown/binding-openharmony-arm64`、`@oxc-transform-react/binding-openharmony-arm64`、`@esbuild/openharmony-arm64`（esbuild 0.28.x）

跨平台性由构造保证：vite/plugin/typescript 全是上游官方版本，唯一 override 的 lightningcss 是上游完整重打包。

## 坑位

- typescript@7（tsgo）缺 openharmony binding → 用 5.9
- Biome 无 OHOS 预编译 → 风格校验走 ESLint 或人工
- systeminformation 的 os 白名单不含 openharmony → `npm install` 需 `--force`
- install 脚本在 OHOS 硬失败 → `--ignore-scripts`，但这会一并跳过 ohos-signpost 的 postinstall，装完补 `npx ohos-signpost`
- `/tmp` 只读 → 临时文件落工程目录
- 华为系统浏览器（ArkWeb）拒载 `file://` → 冒烟用 `vite preview` + curl，或海泰浏览器

## 验收（不绿不算完成）

```sh
npm install                 # ① 零报错
npm run build               # ② 全绿（含 tsc / vue-tsc）
npm run preview &           # ③ 起服
curl -sI http://localhost:4173 | head -1    #    期待 HTTP/1.1 200
find node_modules -name '*.node' \
  | xargs -n1 sh -c 'readelf -S "$0" | grep -q ".codesign" || echo "未签名: $0"'   # ④ 无输出=全签
```

⑤ **多平台回归**：原平台（Windows/Linux）`npm install` + build 仍绿。工程有 CI 就加 OS matrix，没有 CI 至少在原平台重跑一遍，确认 overrides 没把原平台依赖树改坏。

配方基于 vite 系，webpack 系未实测（terser 纯 JS 无碍，其原生依赖链需自行核查）。
