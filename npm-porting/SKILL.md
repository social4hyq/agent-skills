---
name: npm-porting
description: Use when 一个 npm 包在 OpenHarmony/鸿蒙 PC 上安装或运行失败，需要判断上游支持、复用社区 port，或制作和维护 @ohos-npm-ports 移植包；也适用于原生 binding 和纯 JS 平台判断问题。已有前端工程整体适配使用 ohos-frontend-upgrade。
metadata:
  source-repo: ../Skills/npm-porting
  compatibility: 构建验证使用社区 ci-runner 容器；需要访问 GitHub 和 npm registry。
---

# npm-porting

## 判断路径

1. 检查上游最新版本的 loader、平台白名单及 npm 平台子包（`openharmony-arm64` 和 `linux-arm64-ohos` 都查）；已原生支持则优先升级。纯 JS 包也可能因 `process.platform` 白名单失败。检查是否已有上游适配 PR。
2. 查 npm 官方 registry 的 `@ohos-ports` 和 `@ohos-npm-ports`；确认版本、实际 require 的包及目标功能，实测后通过 alias/overrides 复用，不假定已有 port 一定可用。
3. 均不可用时再设计新 port。OpenHarmony 目标 native 产物须源码构建，不以其他平台预编译产物替代；其他平台产物按社区规范核验后可复用。保留其他平台行为和原作者、许可证信息；平台专用槽位可仅含对应 binding。

## 自建与维护

社区仓规范是权威源，操作前基于目标基底的同一 commit 阅读 [贡献指南](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/contributor/contributing.md)、[port 规范](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/contributor/port-spec.md)、[CLI](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/contributor/cli.md) 、[移植指南](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/contributor/porting-guide.md)、[构建框架](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/contributor/build-frameworks.md) 与 [验证标准](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/contributor/verification.md)。需要跨平台功能测试时读 [consumer 协议](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/.github/fixtures/consumer/README.md)，涉及 CI 或发布时读 [CI 流程](https://github.com/ohos-npm-ports/ohos-npm-ports/blob/main/docs/zh-CN/maintainer/ci-pipeline.md)。本地目标基底或网络均不可用时，不猜测现行规范，向用户说明。

- 配方在 `ports/<首字母>/<port>/NPMBUILD`，通常滚动维护；旧版本线和 dist-tag 按规范处理。可用 `npm-ports create` 创建，按需用 `bump --write` 或 `revision` 维护；升级后检查并重新生成必要补丁，真实构建。
- 管理器按 `prepare → build → package → check` 执行钩子；声明并使用 `source/sha256`、`resource`、`fetch_source` 和 `fetch_resource`。不要自行串联生命周期、编写 `publish.sh` 或在配方中签名。patch 重新生成，应用后验证 marker，不能只看 patch 退出码。
- 配方和槽位使用裸上游版本；revision 由管理器 `pack` 注入并同步槽位引用，统一签名和打包。槽位在同一 NPMBUILD 中声明，`packages` 按槽位先、主包后排列以控制发布顺序；不要因此假定槽位先于主包构建。
- 非 OHOS 平台保留上游解析及依赖行为；依据包实际 loader 设计，不要默认所有包都需要相同双包形态。避免无关改写，检查实际发布文件；深水区按需读 `reference/ohos-porting-notes.md`，并以当前工具链和仓库规范复核历史结论。

## 验证

在仓库根目录、当前社区 ci-runner 容器中执行；把示例中的 port 名换成实际值：

```sh
export PATH="$PWD/cli:$PATH"
npm-ports lint parcel-watcher
npm-ports check parcel-watcher
sh .github/scripts/validate-local-publish.sh ports/p/parcel-watcher
```

配方 `check()` 检查产物包名、裸上游版本、补丁命中和真实加载，尽可能调用实际功能。私仓验证负责打包、integrity 和安装；`test.js` 按协议补充跨平台 API/CLI/工程断言。通用安装矩阵不依赖 test.js，但安装通过不等于功能通过；其他平台比较上游 baseline 与 overrides。容器、stub 和 CI 均不能代替真机的签名、沙箱、系统服务与业务验证；注明未验证项。CI 可能复用已发布产物，确认实际运行路径后再声称重建成功。

## PR 与发布

- 遵守当前社区 commit 和 PR 模板。个人协作约定：独立分支、尽量单 commit，不顺手修改冲突热点 README；按路径精确暂存，不扫入日志。使用仓库配置的本人身份；仅在 tip 为自己提交时 amend。
- 用户要求先验证个人 fork 时，先向 `social4hyq/ohos-npm-ports:main` 提 PR 并等待 CI；正式社区 PR 应基于最新上游 main，必要时单独移植 commit，不携带 fork 独有历史。只要求 fork 验证就停在那里。
- 描述当前形态、原因、构建、验证和盲区，只勾实际完成的检查。正式发布交给社区工作流，不在配方或本地擅自发布。部分发布后按当前恢复流程核对 artifact integrity：相同内容的重试可跳过，内容不同须增加 revision。

## 消费侧接入

使用 `npm:@ohos-npm-ports/<pkg>@<version>` alias 或包管理器的 overrides，映射到上游实际解析的包名；pnpm catalog 和 minimumReleaseAge 按工程配置处理。社区管理器 pack 的 AArch64 ELF 已统一签名；工程仍可能引入其他未签名 `.node`，npm/pnpm 可用 ohos-signpost postinstall 处理，bun install 有内置签名。优先直连 npm 官方 registry 核对新包，镜像可能延迟；安装后在目标设备验证。
