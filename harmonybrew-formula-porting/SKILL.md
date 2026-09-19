---
name: harmonybrew-formula-porting
description: Use when 需要把一个命令行工具/开发工具以 formula 形式加进自有 Harmonybrew tap（social4hyq/core）——源码构建、预编译二进制重打包、npm 应用包装三种形态的新增或修改；或需要打包 bottle、处理签名、revision、CI 发布链问题时使用。也覆盖把自有 tap 已验证的 formula「上游化」提交 PR 到官方 Harmonybrew/homebrew-core（gitcode，非 GitHub，另一套 PR 机制，见 `docs/tap.md`「上游化到 Harmonybrew 官方 core」节）。
compatibility: 本机 harmonybrew 可跑 style/audit/readall 与 bottle 安装（本机即真机，真机已禁 --build-from-source/--build-bottle，重型构建与 bottle 走 tap 仓 CI；openharmony 容器仅本地重型构建/调试可选）；CI 发布链需 tap 仓 GitHub 管理员权限。docs/ 三份参考随 skill 分发，无外部路径依赖。
metadata:
  source-repo: ../Skills/harmonybrew-formula-porting
  updated: "2026-09-19"
---

# harmonybrew-formula-porting

自有 tap（`social4hyq/core`）formula 全生命周期：新增/修改/打包/签名/发布/真机验证。相邻分工：npm 包移植判定与 port 制作 → `npm-porting` skill。

## 形态判定（先定形态，抄最近同类案例）

- **源码构建**（上游开源可编译）：zellij、herdr（Rust+zig，签名重试循环）、starship（cargo）、bun（Rust+LLVM）、vite-plus（最复杂）
- **预编译重打包**（上游官方二进制）：qemu-aarch64、bun-bootstrap、claude-code；单一消费者场景优先 install() 内联 resource（见 herdr 的 zig 用法），别急着独立开一个 formula
- **npm 应用包装**（本体是 npm/TS，formula 只做 wrapper）：sshport、claude-code、opencode@2

形态决定后续每一步；写之前先读 `docs/tap.md` 对应案例节。

## 硬约束

- **有官方 core 同名 formula 就对齐它**：url/desc/license/test 断言/deps 结构尽量照抄官方 [Homebrew/homebrew-core](https://github.com/Homebrew/homebrew-core) 最新版（`https://raw.githubusercontent.com/Homebrew/homebrew-core/main/Formula/<letter>/<name>.rb` 直接拉），只在 OHOS 平台确实需要处才发散（额外 build deps、env、vendor patch、签名）；上游升级/改写法时顺手判断本 tap 是否也该同步，别让自有版本越漂越远——但发散点只能凭已验证的教训保留，不能为了"像上游"就删掉没实测过的 OHOS 适配（案例：zellij 对齐上游 v0.45.1，见 `docs/tap.md`）
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
- **shim/patch/caveat 从别的 formula 抄过来必须逐个单独验证，不能假设"同根因"**：不确定某条 fix 现在是否还需要，别猜、别翻注释历史当结论——开一个不合并的草稿 PR，去掉它让 CI 跑一次真实容器构建 + `brew test`，绿了就是真不需要，红了照抄日志追根因（读 `pr-validate` 失败点附近最后编译的几个 crate/文件，别停在第一个看似合理的解释上）。案例：zellij/starship/herdr 三个 formula 都带过同一份 `strerror_r` shim，逐个验证后发现 starship/herdr 各自需要（且元凶完全不同：starship 是依赖树里一条古董 `errno 0.2.8`，跟 rustc/libc crate 本身无关），zellij 从头到尾都不需要（PR #484）
- **对齐上游/重新移植时，核对 Cargo.lock 版本号没变 ≠ 验证过 fix/caveat 仍然必要**：zellij 重新移植到 v0.45.1 时只做了前者，把 `strerror_r` shim 和一条从未验证过的 `rustls-native-certs` caveat 原样带过去，隔天审计才发现都是错的——凡是"移植时继承的假设"，重新移植/大版本升级都是免费的复核窗口，别只顾着核对版本号

## 真机验证（上线依据）

容器结果不是部署证明——真机有独有坑（exec 签名强制、seccomp SIGSYS、内核屏蔽项，见 `docs/ohos-porting.md` §1.2；例证：zig 中间产物签名坑只在真机现身）。装完跑 `brew test` + 真实负载；`ohos-shim check` 逐拦截点实测设备是否还需 shim。一次性验证可真机手动工具链直建（产物不发布）。

## 上游化到 Harmonybrew 官方 core

自有 tap 验证过的 formula 可再提 PR 到官方 `Harmonybrew/homebrew-core`（llvm@21/lld@21/libsecret/zellij 均走过）。这是 gitcode.com 上的独立仓库，不是 GitHub，`gh` CLI 无效，PR（merge request）要用 gitcode v5 API 开。官方硬要求以贡献指南 `Harmonybrew/docs` 仓 `zh-CN/contributor/contribute-formula.md` 为权威出处，执行时逐条对表：准入 = Acceptable-Formulae + **英文注释** + **最小化修改**（每处改动缺了必构建/测试失败、或缺了 OHOS 设备业务功能必出问题）；上游 Homebrew/homebrew-core 已有的 formula **必须搬运上游文件严禁手写**；**「一个 PR → 一个 commit → 一个 formula」**，多 commit 被门禁拦截，整改即压成单 commit 后 `git push -f`（与自有 tap「禁 squash」相反）；标题/commit 走 `<formula> <version> (new formula)` / `<formula> <version>` / `<formula>: <action>` 三段式；MR 开好后等维护者打 `request-ci` 标签触发流水线，构建成功机器人发「替代 PR」一并合并。细节、API 调用方式、fork 仓库信息全部见 `docs/tap.md` 对应节，照抄别现推。

## 深层参考（随 skill 分发）

- `docs/tap.md` — 现役 formula 逐案例教训、CI 发布链机制与实测坑、命令速查
- `docs/ohos-porting.md` — 平台事实、构建系统适配模式、方法论、32 条陷阱速查
- `docs/container.md` — openharmony 容器搭建、一次性配置、日常命令、故障排查
