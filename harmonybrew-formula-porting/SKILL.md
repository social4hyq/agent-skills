---
name: harmonybrew-formula-porting
description: Use when 需要把一个命令行工具/开发工具以 formula 形式加进自有 Harmonybrew tap（social4hyq/core）——源码构建、预编译二进制重打包、npm 应用包装三种形态的新增或修改；或需要打包 bottle、处理签名、revision、CI 发布链问题时使用。注意：把上游 formula 适配进 Harmonybrew 官方 core 不属于本 skill 范围。
compatibility: 本机 harmonybrew 可跑 style/audit/readall 与 bottle 安装（本机即真机，真机已禁 --build-from-source/--build-bottle，重型构建与 bottle 走 tap 仓 CI；openharmony 容器仅本地重型构建/调试可选）；CI 发布链需 tap 仓 GitHub 管理员权限。docs/ 三份参考随 skill 分发，无外部路径依赖。
metadata:
  source-repo: ../Skills/harmonybrew-formula-porting
  updated: "2026-09-02"
---

# harmonybrew-formula-porting

自有 tap（`social4hyq/core`）formula 全生命周期：新增/修改/打包/签名/发布/真机验证。相邻分工：npm 包移植判定与 port 制作 → `npm-porting` skill。

## 形态判定（先定形态，抄最近同类案例）

- **源码构建**（上游开源可编译）：zellij、herdr（Rust+zig，签名重试循环）、starship（cargo）、bun（Rust+LLVM）、vite-plus（最复杂）
- **预编译重打包**（上游官方二进制）：zig@0.15、qemu-aarch64、bun-bootstrap、claude-code
- **npm 应用包装**（本体是 npm/TS，formula 只做 wrapper）：sshport、claude-code、opencode@2

形态决定后续每一步；写之前先读 `docs/tap.md` 对应案例节。

## 硬约束

- tap 权威源 `~/.harmonybrew/Homebrew/Library/Taps/social4hyq/homebrew-core`；**改 tap 一律走独立 worktree**——主克隆 checkout 会被自动化/其他会话切走（文件半途消失发生过）
- 容器内 `brew --prefix` 是 `/storage/Users/currentUser/.harmonybrew`（非 `~/.harmonybrew`）；手动打包：gnu-tar 必装、相对符号链接保可重定位、cmake 裁剪用 post-install prune；搭建见 `docs/container.md`
- 单文件自包含（禁 tap 级共享 Ruby）；非必要不注释、不引本地文档；`cellar` 一律 `:any_skip_relocation`（内联写在 sha256 行）；wrapper 优先 `write_env_script`/`ohos-shim`
- 命名冲突：与官方 core 同名的引用写 `social4hyq/core/<name>` 全限定；裸名会被静默劫持成官方版，探测用 `ls Formula/*/*.rb`（`brew info` 不可信）
- 构建日志放对应工程的 `logs/`

## 签名

- 默认 `binary-sign-tool sign -selfSign 1 -inFile <in> -outFile <out> && chmod +x <out>`——静态 ELF 安全；**签坏仅限 bun 和 CGO_ENABLED=0 Go 纯静态产物**；异常再换 `ohos-bst-light` 的 `self-sign`
- `-outFile` 重写会破坏 `.bun` section trailer（官方 claude-code 二进制必须 ohos-bst-light）
- 两层缺一不可：LLD CodeSign patch（`.codesign` section）+ binary-sign-tool（执行权限）
- CI 双签致 exit 139：`UNSET_SIGN_FORMULAS` 名单（现 `claude-code qemu-aarch64`）+ install() odie 守卫；**产物最终形状决定免签与否，「源码构建」不是理由**（CGO=0 Go 同坑）
- npm 工程（含 `.so`/`.node`）：`ohos-signpost` devDependency + postinstall；bun 自带签名

## 本机校验（改 formula 必过）

```bash
brew style social4hyq/core/<formula>
brew audit social4hyq/core/<formula>
brew readall && brew audit --except=version social4hyq/core/   # tap 全量，按需
```

- 散文件 `brew style` 脱离 tap rubocop 配置会报 Sorbet 误报——放回 tap 路径再跑
- 只有影响已安装产物的改动才加 `revision`（+1 触发 bottle 重打，否则已装用户拿不到）；纯注释/caveat 不 bump

## 发布链（全自动）

pr-validate（audit + 源码构建 + brew test + bottle 合并前回写）→ `ci-passed` 标签 → 合并后双发布（atomgit 主、GitHub Releases 灾备）。PR 纪律：切分支前 `git fetch github main`（origin=atomgit 镜像，PR 开在 GitHub）；**禁 squash**；**PR 只许 1 个 commit**——因为禁 squash，这个约束靠自己维护：CI 反馈需要改动时用 `git commit --amend`（分支 tip 是自己的 commit，符合硬约束 12 的 amend 许可条件）再 `git push --force-with-lease`，不要每轮 `git commit` 堆一个新提交；merge 报 "base branch policy prohibits" 是已知假失败（bottle 回写 push 不触发 workflow），`gh pr merge --merge --admin`；workflow 改动等 `actionlint` 而非 ci-passed。本地预打包才用容器 `brew install --build-bottle`。机制与实测坑见 `docs/tap.md` CI 节。

## 修改已有 formula

- 改 patch **必须重新生成 hunk**（禁手改 `@@` 行号）——toybox patch 会静默 `exit=0` no-op，验证靠 grep marker 不靠退出码
- 下游重编顺序：`llvm@21 → bun-webkit → bun → opencode/opencode@2`
- 自有 formula 保持最小改动，官方原生收录后下线自有版本（reasonix/uv/codegraph/nvm/deepseek-harness 均已走完）

## 真机验证（上线依据）

容器结果不是部署证明——真机有独有坑（exec 签名强制、seccomp SIGSYS、内核屏蔽项，见 `docs/ohos-porting.md` §1.2；例证：zig 中间产物签名坑只在真机现身）。装完跑 `brew test` + 真实负载；`ohos-shim check` 逐拦截点实测设备是否还需 shim。一次性验证可真机手动工具链直建（产物不发布）。

## 深层参考（随 skill 分发）

- `docs/tap.md` — 现役 formula 逐案例教训、CI 发布链机制与实测坑、命令速查
- `docs/ohos-porting.md` — 平台事实、构建系统适配模式、方法论、32 条陷阱速查
- `docs/container.md` — openharmony 容器搭建、一次性配置、日常命令、故障排查
