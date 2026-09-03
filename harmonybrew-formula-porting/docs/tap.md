# harmonybrew-core tap：Formula 清单、CI 发布链与打包细节

> 随 skill 分发的参考，独立维护。formula 清单以 `ls Formula/*/*.rb` 实时为准。

## Formula 权威源

路径：`~/.harmonybrew/Homebrew/Library/Taps/social4hyq/homebrew-core/`。Patches/ 仅存 `Patches/llvm@21/`（其余 formula 补丁均已内联 `inreplace`）。

现役 18 个 formula：

| 分组 | Formula | 要点 |
|---|---|---|
| 重型构建链 | `llvm@21` → `bun-webkit` → `bun-bootstrap` / `bun` | 下游重编顺序从底向上；llvm@21（~62min）是唯一超时风险项；ICU 用上游 harmonybrew/core 的 `icu4c@78`（本 tap fork 已删）；bun 桥常驻（不向 oven-sh/bun 开 PR） |
| 源码构建 CLI | `opencode`（v1）、`opencode@2`（v2） | bun compile 源码构建，补丁全内联 |
| 源码构建 Rust | `zellij`、`herdr`、`starship`、`vite-plus` | starship 现为 cargo 源码构建（早期 musl 预编译方案已弃）；vite-plus 最复杂 |
| 预编译重打包 | `zig@0.15`、`qemu-aarch64`、`claude-code`、`bun-bootstrap` | claude-code / qemu-aarch64 在 `UNSET_SIGN_FORMULAS` 名单（禁 CI 自动签名） |
| npm/TS 应用包装 | `sshport` | 纯 TS bun bundle，无 `.so`，免签名 |
| 工具/基础设施 | `ohos-compat-shim`、`ohos-bst-light`、`node-ohos`、`hishell-font` | shim/签名基础设施、llvm@21 编译的 node（bun/nan addon ABI 兼容）、Nerd Font 配置 |

已下线（由 Harmonybrew 官方 core 原生提供，裸名 `brew install`）：`reasonix`/`uv`/`codegraph`/`nvm`/`deepseek-harness`。旧构建记录已随 formula 删除，普适教训沉淀在本文各节。

## 各 formula 的持久教训

### opencode / opencode@2（bun compile 源码构建）

- 补丁机制：formula 内 `inreplace`（version-independent 字符串/数组编辑）；结构性改动先在独立开发树（fork 的 dev 分支）验证再回填 formula
- opencode@2 版本方案 = npm beta dist-tag：`version` 镜像 npm dist-tag（`0.0.0-beta-<build>`），git pin = 该 npm 发布时间戳时刻的 v2 tip（npm 元数据无 gitHead，用 `commits?until=` 时间映射）；`version_scheme 1` 兜住旧 keg 升级
- 原生依赖走社区 port，tap 现消费 `@ohos-npm-ports/*` scope（opentui-core / lightningcss / tailwindcss-oxide / bun-pty / parcel-watcher；旧 `@ohos-ports` scope 已停发，2026-09 经 PR #461-463 + [ohos-npm-ports#28](https://github.com/ohos-npm-ports/ohos-npm-ports/pull/28) 全量切换）；上游收口后 `npm deprecate` port 包、依赖切回官方

### claude-code（npm musl 二进制 repack + wrapper）

- 现行策略「抽 bundle + tap 自建 bun 执行」，不执行官方二进制——官方内嵌 bun 在 OHOS 启动即崩：stdout/stderr 的 `R_AARCH64_COPY` 重定位被 OHOS musl ld.so 解析成自拷贝、槽位留 NULL，首次 stdio 调用触发加固 libc abort（`ohos-compat-shim` v0.4.0 的 std_streams 拦截点可兜官方二进制）
- **brew test 必须真跑二进制**（断言真实版本输出）——只断言文件存在曾放过坏 bump，升级用户全崩
- 签名工具选错的症状很隐蔽：`binary-sign-tool` 的 `-outFile` 重写会破坏 `.bun` section trailer（产物退化成裸 bun，`--version` 打 bun 版本）——官方 claude-code 二进制须用 `ohos-bst-light self-sign`
- 在 autobump 白名单内（CI 端到端 brew test 裁决）

### zellij（Rust 源码构建，tag pin）

- **git url 大坑：`revision:` 与 `branch:` 并存时 `branch:` 静默胜出、pin 从未生效**——要么 `revision:` 单独用，要么 `tag:`+`revision:` 成对
- 四个 OHOS 修复（均可复用）：
  1. `cargo update --precise` 提老依赖过 OHOS 支持线（curl 0.4.50 → socket2 ≥0.5.6）
  2. `strerror_r` 转发 `.o` + `RUSTFLAGS` shim——rust libc crate 对 OHOS 声明 glibc 专属 `__xpg_strerror_r`（zellij/starship/herdr 同根因同修法）
  3. vendor 补丁版 `close_fds` 绕 `SYS_close_range`——HongMeng seccomp 对 436 号 syscall 回 **SIGSYS 直接杀进程**（不是 ENOSYS），"探测式降级"设计失效。**能源码修掉对问题 syscall 的调用就别留 LD_PRELOAD shim**（shim 是兜底，依赖树审计往往能找到唯一元凶）
  4. `OHOS_NDK_HOME` 指向 ohos-sdk **keg 根**（aws-lc-sys 的 OHOS 支持只在 CMake builder 路径；指成 `native/` 会拼出双层路径）

### zig@0.15（官方静态二进制重打包）

- 为什么重打包：官方 core zig 源码构建依赖 llvm@20，本 tap 只有 llvm@21，不值得再拉一套
- 三个 formula 坑：Homebrew 解包会剥掉 tarball 唯一顶层目录（直接引用 `buildpath`）；zig 靠自身真实路径找 `lib/`（二进制+lib 整体进 `libexec`，`bin/` 放薄 wrapper）；`std.debug.print` 走 stderr（`brew test` 里 `shell_output "... 2>&1"`）
- 签名结论（真机复测）：binary-sign-tool 对 zig 静态 ELF 单签/双签均正常

### herdr（Rust + zig 混合构建）

- `build.rs` 的 zig target 映射表不认 OHOS → 补丁加一行映射到 `aarch64-linux-musl`（产出的 `.a` 由 rustc 的 OHOS-aware 链接器吃掉，zig 自己不需要认识 "ohos"）；OHOS 源码适配统一走 `Patches/herdr/*.patch`（inreplace 已于 #458 迁出），**hunk 版本敏感**：升版本前对新 tarball `patch --dry-run` 试打，断了就改好源码侧机器重生成，**禁手改 `@@` 行号**——toybox patch 普通 context 漂移也会 `Hunk N FAILED` 却 **exit 0 且一字节没打上**（原子全或无），brew 只在 rc≠0 时报错，install() 顶部有逐文件 marker odie 兜底；已入 autobump 白名单（hunk 断裂 = pr-validate 红 → 不自动合并，卡住的 bump PR 即手动再生成信号）
- **签名重试循环**（本 tap 最特别的机制）：`zig build` 内部编译并直接 exec 中间工具，这些产物不经监管工具链、无 codesign 段，真机拒绝 exec——install() 里 rescue `AccessDenied` 提取文件名、在 zig-cache 定位补签重试（上限 20 次，实测个位数次收敛）
- **该坑只在真机现身**：容器/CI 不复现 exec 签名强制——重试逻辑的验证靠真机 bash 原型 + 真实报错文本单测，CI 绿不证明该分支正确
- zig 联网依赖预热：`ZIG_GLOBAL_CACHE_DIR` 指向 HOMEBREW_CACHE 常驻目录，host 上跑通一次后 tar 进容器（与 bun 缓存预热同套路）；`deps.files.ghostty.org` 本机 DNS 解析失败（污染）时：DoH 查 IP + `curl --resolve` 拉包，按 `p/<hash>/` 布局解进缓存即可
- **依赖瘦身（0.8.2_1）**：①不依赖 zig@0.15 keg——install() 用 resource 内联官方静态预编译 zig（版本锚定 libghostty-vt 的 minimum_zig_version），暂存后 binary-sign-tool 签名（zig 靠 self-exe-realpath 找 lib/，暂存树必须完整）；②运行时无 ohos-shim wrapper——herdr 源码零拦截点命中，真机无 shim 全链路实测等价（含 session 重启持久化）；差异行为要先做带 shim 对照实验排除 shim 归因再下结论
- **agent 检测修复（tcgetpgrp 回退）**：OHOS procfs 对所有进程报 tty_nr/tpgid=0、内核无 `/proc/<pid>/task/<tid>/children`——herdr 的原生前台进程组识别与 `child-groups` 兜底全废，`HERDR_AGENT` 提示也依赖 job 发现而失效，hook 上报再被 `process_present` 门抑制，侧边栏 agent 列表恒空。修法 = 补丁（`Patches/herdr/pane-agent-detection-tcgetpgrp.patch`）给两条检测循环加「/proc 拿不到就 tcgetpgrp(pane 自己的 PTY master fd，actor 本就有现成实现）」回退，成员枚举降级 leader-only；claude 因 wrapper exec 成 `bun …/cli`（basename 不在识别表）需 claude-code wrapper 配套 `export HERDR_AGENT=claude`。brew test 内置端到端断言（pane 跑假 opencode 进 agent list）；真机验证用 `HERDR_SOCKET_PATH`+`XDG_STATE_HOME` 隔离的 scratch server，别动用户活 server；scratch socket 必须放 `/data/storage/el2/base/tmp/` 等沙箱私有目录（共享目录 bind unix socket EPERM）。0.8.2 曾重构 spawn-task 前台组查询为 `match (pid, foreground_observation_due)`，回退挂点改到 `(_, true) =>` 臂——升级必重核 hunk

### vite-plus（最复杂综合案例）

Rust workspace（stable rust + `RUSTC_BOOTSTRAP=1` 解锁 `-Z bindeps`）+ pnpm deploy。原生 binding 三层接线：上游原生发布直装 / `@ohos-npm-ports` 社区 fork overrides（**catalog: 声明的依赖 override 键必须裸名**，版本限定键匹配不上）/ 仅 `@napi-rs` 三件套走 musl 产物伪装 shim；port scope 须加 `minimumReleaseAgeExclude`（工程 24h 成熟度门拦新发布 port）；构建期 pnpm@10 / 运行期 pnpm 分离。细节见 formula 注释。

### 其他

- `ohos-compat-shim`：LD_PRELOAD 兼容垫片 + `ohos-shim` 工具；`ohos-shim check` 逐拦截点实测当前设备是否还需要该 shim（换新 OHOS 版本机器先跑再决定关不关）；拦截点含 `link()`（musl 内联 syscall 绕过 linkat 动态符号）与 `std_streams` COPY-reloc 回填
- `ohos-bst-light`：备选签名器（`self-sign` 命令，保留 ELF 结构）
- `qemu-aarch64`：Alpine apk repack 范式

## dlopen 符号解析限制

OHOS 动态链接器命名空间隔离：dlopen 加载的模块无法回溯解析主二进制导出符号（zsh/ruby/perl 的扩展模块均受影响，`-rdynamic`/`--export-dynamic` 修不了）。轻量修法 = 链接时 `-Wl,-z,global`（设 `DF_1_GLOBAL`）；笨重修法 = `--disable-dynamic` 全静态内建（本 tap 曾用于 zsh，已被 -Wl,-z,global 方案取代）。细节见 `ohos-porting.md` §3.1。

## CI 全自动发布链

workflows（15 个）核心链：**pr-validate**（Formula/** PR 门禁：audit + 源码构建 + brew test；bottle 在合并**前**发布并回写 PR 分支；通过打 `ci-passed`）→ **automerge-autobump**（白名单 bump PR 自动合并）→ **publish-on-merge + sync-to-atomgit**（双发布：atomgit 主、GitHub Releases 灾备镜像）。bottle-build.yml 为核心构建（dispatch / workflow_call 复用）。

**持久约束**（全是实测坑换来的）：

- **GITHUB_TOKEN 产生的事件（打标签、合并 push）不触发任何 workflow**（GitHub 防递归）——链路设计第一约束。CI 的 bottle 回写 push 因此不触发新 run，分支保护在回写 commit 上找不到检查 → `gh pr merge` 报 "base branch policy prohibits" 是**已知假失败**，`gh pr merge <N> --merge --admin` 处理
- Token 分工：开 PR / 打标签用 `GITHUB_TOKEN`（bot 身份）；推保护 main / 合并用 `BOT_PUSH_TOKEN`（管理员 PAT，**会静默过期**——push 401 先怀疑它）
- main 受 ruleset 保护，**禁 squash**（压平后 detect-changes 识别不了 bottle 回写，仓库层已禁用）——正因为禁 squash，"PR 只许 1 个 commit" 这条约束没有平台兜底，得自己维护：CI 报错需要改动时 `git commit --amend`（branch tip 是自己的 commit，符合硬约束 12 的 amend 许可条件）+ `git push --force-with-lease`，禁止每轮修复都 `git commit` 摞一个新的（libsecret PR #471 一次踩过：5 轮 getpass 修复堆了 5 个独立 commit 才合并，被要求登记进这里）
- bottle 内容变化（sha256 变）必须新 tag `-r<N>` 递增；上传成功后才回写 formula `root_url`+`sha256`
- atomgit 上传 = 预签名 URL 两步流（`.github/scripts/publish.sh`）；GHA→OBS PUT 可慢至 ~18KB/s，用 `--speed-limit 1024 --speed-time 120` 别用硬超时（下载方向是快的，别混淆）
- npm livecheck/时间戳查询曾因 registry.npmjs.org 给 CI runner IP 回 Cloudflare 挑战页（200 非 JSON → livecheck `--json` 静默 exit 1）切 npmmirror；本机直连限制已解除，怀疑 404 先直连官方 registry 复核
- build.sh 环境修正**勿删**：`seccomp=unconfined`（io_uring）、`/system/lib/ld-musl` symlink、`brew trust social4hyq/core`（否则静默假成功）、brew install 90s 重试、cargo sparse、`UNSET_SIGN_FORMULAS`（现 `claude-code qemu-aarch64`）
- `brew update` 会把 bind-mount tap 的 detached HEAD rebase 到 origin/main 留下幽灵提交 → bottle 回写落在幽灵上推不出去（已在 build.sh 修：update 前记录 sha）；诊断特征 = 幽灵 sha 在 GitHub API 404
- publish.sh 的 push 失败原因被 `2>/dev/null` 吞掉——401（token 死）和非快进在日志里长得一样，别急着信守卫报错文案
- 容器里改 formula 走 `docker cp` 会带 660 权限 → `brew audit` 报权限错，host `chmod 644` 即可（容器 tap 目录不是 git repo）
- 容器可能被别的会话占用（Cellar 锁冲突）→ **不要杀别人构建**，直接靠 PR 自己的 pr-validate 把关
- Runner：`ubuntu-24.04-arm` + ghcr 派生 ci-runner 镜像（sync-ci-image 按 digest 跟踪上游）；实测 icu4c@78 6.5min、bun 18min、llvm@21 62min
- 卫生设施：actionlint（**workflow 改动的门禁是它，不是 ci-passed**）、bottle-gc（周清孤儿 bottle）、version-check（周 livecheck 报告，report-only）、daily-regression（每日级联回归）、`uses:` 全钉 SHA

## 命令速查

| 命令 | 用途 |
|---|---|
| `brew install --build-bottle <f>` | bottle 用途构建（与 `--build-from-source` 互斥）|
| `brew install --build-from-source <f>` | 验证构建，不生成 bottle（**真机上源码构建已被 Harmonybrew 禁用**，只能容器/CI；一次性验证可在真机手动 cargo 直建，产物不发布）|
| `brew bottle --json --root-url <url> <f>` | 对已装 keg 打 bottle tarball |
| `brew uninstall --ignore-dependencies <f>` | 强制卸载，跳过下游依赖阻断 |
| `brew test <f>` | 运行 formula 内置 test |

## 下游重编顺序（依赖链从底向上）

```
llvm@21 → bun-webkit → bun → opencode/opencode@2（@ohos-npm-ports/* npm 依赖，非 formula）
```
