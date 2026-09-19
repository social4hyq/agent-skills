# harmonybrew-core tap：Formula 清单、CI 发布链与打包细节

> 随 skill 分发的参考，独立维护。formula 清单以 `ls Formula/*/*.rb` 实时为准。

## Formula 权威源

路径：`~/.harmonybrew/Homebrew/Library/Taps/social4hyq/homebrew-core/`。Patches/ 仅存 `Patches/llvm@21/`（其余 formula 补丁均已内联 `inreplace`）。

现役 18 个 formula：

| 分组 | Formula | 要点 |
|---|---|---|
| 重型构建链 | `llvm@21` → `bun-webkit` → `bun-bootstrap` / `bun` | 下游重编顺序从底向上；llvm@21（~62min）是唯一超时风险项；ICU 用上游 harmonybrew/core 的 `icu4c@78`（本 tap fork 已删）；bun 桥常驻（不向 oven-sh/bun 开 PR） |
| 源码构建 CLI | `opencode`（v1）、`opencode@2`（v2） | bun compile 源码构建，补丁全内联 |
| 源码构建 Rust | `zellij`、`herdr`、`starship`、`vite-plus` | starship 现为 cargo 源码构建（早期 musl 预编译方案已弃）；vite-plus 最复杂；herdr 的 zig 工具链是 install() 内联 resource，不经独立 formula（见下节） |
| 预编译重打包 | `qemu-aarch64`、`claude-code`、`bun-bootstrap` | claude-code / qemu-aarch64 在 `UNSET_SIGN_FORMULAS` 名单（禁 CI 自动签名） |
| npm/TS 应用包装 | `sshport` | 纯 TS bun bundle，无 `.so`，免签名 |
| 工具/基础设施 | `ohos-compat-shim`、`ohos-bst-light`、`node-ohos`、`hishell-font` | shim/签名基础设施、llvm@21 编译的 node（bun/nan addon ABI 兼容）、Nerd Font 配置 |

已下线（由 Harmonybrew 官方 core 原生提供，裸名 `brew install`）：`reasonix`/`uv`/`codegraph`/`nvm`/`deepseek-harness`。旧构建记录已随 formula 删除，普适教训沉淀在本文各节。`zig@0.15`（2026-09-03 删除，PR #473）另属一类：不是被官方 core 取代，而是唯一消费者 herdr 早改用 install() 内联 resource（同款官方预编译 zig + binary-sign-tool 签名 + chmod +x），resource 签名可执行即可跑，没必要再单独包一层 formula——判断某工具要不要独立 formula 还是内联 resource，先查有没有第二个消费者；打包坑沿用进了下方 herdr 一节，不重复存档。

## 各 formula 的持久教训

### opencode / opencode@2（bun compile 源码构建）

- 补丁机制：编号补丁文件（`Patches/opencode/` 8 个、`Patches/opencode@2/` 8 个，formula 内 `%w[].each { patch do file }` 挂载）；inreplace 时代已结束。bump 冲突补丁按语义重生成（sed+diff 出整文件，禁手改 `@@`）；v2 已知坑：上游会删 `packages/{web,www,storybook,enterprise}`（rm_r 带守卫）、CLI binary const 可能改名（2.0.7 靠 0008 补丁吸回）、bun.lock openharmony-arm64 的 os:none→openharmony 随锁重出
- opencode@2 版本方案 = 上游 git tag `v2.*`（上游 2026-09 把 v2 npm 包从 `@opencode-ai/cli` 改名 `@opencode/cli`，npm dist-tag 方案弃用）：`livecheck` 用 `url :stable` + `regex(/^v(2\.\d+\.\d+)$/i)`，git pin = release tag 指向的 commit（`git ls-remote` 取 peeled），不再做 npm 发布时间戳→分支 tip 反查；`version_scheme 1` 兜住旧 keg 升级
- 原生依赖走社区 port，tap 现消费 `@ohos-npm-ports/*` scope（opentui-core / lightningcss / tailwindcss-oxide / bun-pty / parcel-watcher；旧 `@ohos-ports` scope 已停发，2026-09 经 PR #461-463 + [ohos-npm-ports#28](https://github.com/ohos-npm-ports/ohos-npm-ports/pull/28) 全量切换）；上游收口后 `npm deprecate` port 包、依赖切回官方

### claude-code（npm musl 二进制 repack + wrapper）

- 现行策略「抽 bundle + tap 自建 bun 执行」，不执行官方二进制——官方内嵌 bun 在 OHOS 启动即崩：stdout/stderr 的 `R_AARCH64_COPY` 重定位被 OHOS musl ld.so 解析成自拷贝、槽位留 NULL，首次 stdio 调用触发加固 libc abort（`ohos-compat-shim` v0.4.0 的 std_streams 拦截点可兜官方二进制）
- **brew test 必须真跑二进制**（断言真实版本输出）——只断言文件存在曾放过坏 bump，升级用户全崩
- 签名工具选错的症状很隐蔽：`binary-sign-tool` 的 `-outFile` 重写会破坏 `.bun` section trailer（产物退化成裸 bun，`--version` 打 bun 版本）——官方 claude-code 二进制须用 `ohos-bst-light self-sign`
- 在 autobump 白名单内（CI 端到端 brew test 裁决）

### zellij（Rust 源码构建，tag pin）

- **git url 大坑：`revision:` 与 `branch:` 并存时 `branch:` 静默胜出、pin 从未生效**——要么 `revision:` 单独用，要么 `tag:`+`revision:` 成对
- 三个 OHOS 修复（均可复用）：
  1. `cargo update --precise` 提老依赖过 OHOS 支持线（curl 0.4.50 → socket2 ≥0.5.6）
  2. vendor 补丁版 `close_fds` 绕 `SYS_close_range`——HongMeng seccomp 对 436 号 syscall 回 **SIGSYS 直接杀进程**（不是 ENOSYS），"探测式降级"设计失效。**能源码修掉对问题 syscall 的调用就别留 LD_PRELOAD shim**（shim 是兜底，依赖树审计往往能找到唯一元凶）
  3. `OHOS_NDK_HOME` 指向 ohos-sdk **keg 根**（aws-lc-sys 的 OHOS 支持只在 CMake builder 路径；指成 `native/` 会拼出双层路径）
- **strerror_r shim 曾经也在这，2026-09-05（PR #484）验证后删除**：跟 starship/herdr 一样照抄过 `__xpg_strerror_r` 转发 shim。这个符号问题的典型根因（在 starship 上实锤过）是依赖树里某条古老 crate 自己手写了只判断 `target_os = "linux"`、不判断 `target_env` 的 FFI 声明（starship 是 `guess_host_triple 0.1.5 → errno 0.2.8`）——`rustc`/`libc` crate 本身早就正确处理了 `target_env = "ohos"`，不是它们的锅。但 zellij **从没单独验证过自己是否真的需要**这个 shim——草稿 PR #484 直接去掉它让 CI 跑真实容器构建，完整源码构建 + `brew test` 一次性通过，零链接错误：zellij 的 `Cargo.lock` 锁的 `errno` 是 `0.3.10`（已重写版，正确委托给 `libc` crate），依赖树里压根没有独立手写这个符号的旧 crate。教训：**shim 从别的 formula 抄过来时必须逐个 formula 单独验证是否需要，不能假设"这几个 formula 同根因"**，starship/herdr 需要不代表 zellij 也需要（revision 1 bump，因为去 shim 改变了最终 ELF）
- **`rustls-native-certs` caveats 也是没验证过的错误假设，同一批（PR #484）一并删除**：原文案说"OHOS 系统 CA store 可能找不到"，但 `rustls-native-certs 0.8.3` 实际依赖的 `openssl-probe 0.2.1` 早就上游修复，显式加了 `/etc/security/certificates`、`/etc/ssl/certs/cacert.pem` 两条 OpenHarmony 路径（crate 源码里直接引用了华为官方文档链接）；真机核实两条路径都真实存在且有内容（完整 CA 证书目录 + 191KB 的 `cacert.pem`）
- **对齐上游重新移植（v0.45.1）**：官方 core 已从 `git url tag:+revision:` 切回普通 tag tarball（`.../archive/refs/tags/v0.45.1.tar.gz`），彻底绕开上面这条 `revision:`/`branch:` 大坑本身——本 tap 跟进同款 url，不再需要那条 NOTE 注释；顺带删掉了 upstream 没有的显式 `livecheck` 块（tarball url 走 Homebrew 默认 GitHub tag 探测）和多余的 `base_name: "zellij"`（`generate_completions_from_executable` 对 `bin/` 下的可执行文件本就自动派生 basename）。当时把四个 OHOS 修复（含 strerror_r shim）原样保留、`rustls-native-certs` caveats 也原样保留——**这正是问题所在：重新移植时只逐项核对了 Cargo.lock 版本号没变，没有反向验证每条 fix/caveat 当下是否仍然必要**，隔天专门审计才揪出这两处，教训见上两条。照抄了 upstream 的 `service do`（`zellij web` 常驻）块——纯声明式，真机验证 `brew services` 确实不可用（报"can only be used on macOS or systemd"警告），但不影响 `brew install`/`test`，抄它没风险。`on_linux do end` 包 `zlib-ng-compat` 这条 upstream 写法特意没抄：本 tap 只产 `arm64_ohos` 一个平台，`on_linux` 判定在这个 fork 上的实际取值没有真机验证过，为了「像上游」冒险换掉一个已知能用的写法不值得——**对齐上游是默认动作，不是不计代价的目标**，拿不准就地保留验证过的写法

### herdr（Rust + zig 混合构建）

- `build.rs` 的 zig target 映射表不认 OHOS → 补丁加一行映射到 `aarch64-linux-musl`（产出的 `.a` 由 rustc 的 OHOS-aware 链接器吃掉，zig 自己不需要认识 "ohos"）；OHOS 源码适配统一走 `Patches/herdr/*.patch`（inreplace 已于 #458 迁出），**hunk 版本敏感**：升版本前对新 tarball `patch --dry-run` 试打，断了就改好源码侧机器重生成，**禁手改 `@@` 行号**——toybox patch 普通 context 漂移也会 `Hunk N FAILED` 却 **exit 0 且一字节没打上**（原子全或无），brew 只在 rc≠0 时报错，install() 顶部有逐文件 marker odie 兜底；已入 autobump 白名单（hunk 断裂 = pr-validate 红 → 不自动合并，卡住的 bump PR 即手动再生成信号）
- **签名重试循环**（本 tap 最特别的机制）：`zig build` 内部编译并直接 exec 中间工具，这些产物不经监管工具链、无 codesign 段，真机拒绝 exec——install() 里 rescue `AccessDenied` 提取文件名、在 zig-cache 定位补签重试（上限 20 次，实测个位数次收敛）
- **该坑只在真机现身**：容器/CI 不复现 exec 签名强制——重试逻辑的验证靠真机 bash 原型 + 真实报错文本单测，CI 绿不证明该分支正确
- zig 联网依赖预热：`ZIG_GLOBAL_CACHE_DIR` 指向 HOMEBREW_CACHE 常驻目录，host 上跑通一次后 tar 进容器（与 bun 缓存预热同套路）；`deps.files.ghostty.org` 本机 DNS 解析失败（污染）时：DoH 查 IP + `curl --resolve` 拉包，按 `p/<hash>/` 布局解进缓存即可
- **依赖瘦身（0.8.2_1）**：①不依赖独立 `zig@0.15` formula（2026-09-03 该 formula 已因无第二个消费者而删除，PR #473）——install() 用 resource 内联官方静态预编译 zig（版本锚定 libghostty-vt 的 minimum_zig_version），暂存后 binary-sign-tool 签名（zig 靠 self-exe-realpath 找 lib/，暂存树必须完整——沿用当年 zig@0.15 formula 的教训：Homebrew 解包会剥掉 tarball 唯一顶层目录，直接引用 `buildpath`/暂存目录而非拼二级路径；`std.debug.print` 走 stderr，测试断言要 `2>&1`；binary-sign-tool 对 zig 静态 ELF 单签/双签均正常）；②运行时无 ohos-shim wrapper——herdr 源码零拦截点命中，真机无 shim 全链路实测等价（含 session 重启持久化）；差异行为要先做带 shim 对照实验排除 shim 归因再下结论
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

## 上游化到 Harmonybrew 官方 core

自有 tap 的 formula 稳定后，可再提交一份「上游化」PR 把同样的适配合并进官方 `Harmonybrew/homebrew-core`（llvm@21/lld@21/libsecret/zellij 均已合并；herdr [#18651](https://gitcode.com/Harmonybrew/homebrew-core/merge_requests/18651) 提交中，带一个请维护者裁决的"预编译 zig 依赖"例外）。评审口径的权威出处是官方贡献指南 `Harmonybrew/docs` 仓 `zh-CN/contributor/contribute-formula.md`（atomgit/gitcode 同后端两域名均可读）——本节是它的执行细则，冲突时以官方文档为准。跟自有 tap 的 PR 流程是两套完全不同的机制，别混：

- **仓库不在 GitHub，在 gitcode.com**（`origin` 镜像到 `atomgit.com/Harmonybrew/homebrew-core.git`，两个域名同一后端）；`gh` CLI 对它无效。本机已有官方仓库克隆 `~/.harmonybrew/Homebrew/Library/Taps/harmonybrew/homebrew-core`（tap 名 `harmonybrew/core`），以及一个专用 fork 仓库 `atomgit.com/social4hyq/homebrew-core-harmonybrew-pr.git`（remote 名 `fork`，repo 名跟官方仓库**不同名**，是真正意义的 fork——`git worktree add` 走独立 worktree，禁止直接在这个主克隆上改，规则跟自有 tap一样）。
- **PR（gitcode 叫 merge request）用 v5 API 开**，不能网页/gh CLI：`POST /repos/Harmonybrew/homebrew-core/pulls`，body 含 `access_token`（`~/.atomgit` 里的 `ATOMGIT_TOKEN`，Bearer 头也要带）、`title`、`base: "main"`、`head`。**`head` 必须写成 `"<fork_owner>/<fork_repo_name>:<branch>"` 全路径**（不是 GitHub 那种 `owner:branch`）——因为 fork 仓库名跟官方不同，短格式会报 404 "Can not find the branch"（API 误以为要在 `homebrew-core` 这个名字下找分支）。改标题/正文用 `PATCH /repos/Harmonybrew/homebrew-core/pulls/{number}`。
- **PR 描述必须严格套用官方模板** `.gitcode/PULL_REQUEST_TEMPLATE/PULL_REQUEST_TEMPLATE.md`（描述/类型/Checklist/验证结果四段，勾选框用小写 `x`）——别自由发挥格式。
- **验证结果段不需要真截图，一条可核验的 CI 流水线链接 + 几行关键日志摘录就够**（自有 tap 那条 PR 的 GitHub Actions run 链接，因为跟官方 `ci-runner` 同一派生镜像）；模板写的「必须截图，不允许口头描述」针对的是没有任何可核验证据的情况，别自己加码要求截图，也别写「尚未提供截图」这类道歉式免责声明或任何"相比上一版改了什么"的过程叙事——PR 描述只描述当前状态，编辑过程留在 commit message 里（这条允许比 formula 注释详细）。
- **Checklist 三项里只勾前两项**（`新增 formula`/`版本升级`/`修复/增强` 对应类型 + `我已阅读贡献指南`），**「AI 代码人工审核」「已验证」两项留空**——这两项是要用户本人确认的事实陈述，agent 不能替用户勾；已合并的 `libsecret` PR（#18633）就是这么处理的，照抄。
- **formula 准入规则跟上游 Acceptable-Formulae 一致：必须能从源码构建，禁止录入预编译二进制**——唯二例外是 `ohos-sdk`/`rust`（工具链本身作为 formula 产物分发给用户）。如果某个 formula 需要一个"官方预编译制品仅用于构建、不分发给用户"的依赖（比如 zig 之于 herdr），这不是同一类例外，是 `openjdk`/`go` 那类**构建期工具**模式——`Formula/g/go.rb` 的 `gobootstrap` resource 是本仓已有的正例，直接抄它的写法（`resource(...).stage(...)`，不额外签名，因为下一条）。
- **官方 ci-runner 构建期间不校验代码签名，分发给用户前由流水线统一签名**——formula 的 `install()` 不需要任何 `binary-sign-tool` 签名/重试逻辑（这跟自有 tap 的部分 formula 因为面向真机部署而带的签名防御代码不是一回事，上游化时要把这些去掉，对照 `gobootstrap` 的写法就知道该有多简单）。
- **formula 里的注释要压到极致精简**（能一行不两行），把详细的权衡分析、backport 可行性论证这类内容放到 PR 描述/commit message，别堆进代码注释——官方维护者对这条卡得比自有 tap 严，herdr PR (#18651) 来回改了三轮才收敛到这个标准。
- **`patch do` 不用带 `:p1`**——Homebrew 默认 strip level 就是 1，只有 diff 没有 `a/`/`b/` 这层前缀时才需要显式标 `:p0`；本仓已合并的 formula（`libsecret`、`go`）patch 块都是裸 `patch do`，照抄。
- **标题走纯版本号 `<formula> <version>` 格式，不带 `_<N>` revision 后缀**（`_<N>` 是 formula 内部记法，不进标题）——跟自有 tap 那套 `<formula>: <描述>` 完全不同。新增 formula 加 `(new formula)` 后缀（`herdr 0.9.0 (new formula)`、`libsecret 0.21.7 (new formula)`）；已有 formula 的版本对齐/结构同步不加任何后缀，就是 `<formula> <version>`（如 `zellij 0.45.1`）；纯 revision bump（版本号不变）写 `<formula>: revision bump (<原因>)`。参照同仓库其他已合并 PR 抄最近同类案例，别自造描述性标题。
- **提交里不能出现 agent/AI 协作者痕迹**：commit message 不带 `Co-Authored-By`/session 链接一类尾注，PR 描述不带「Generated with」「claude.ai」这类内容——这条只对 Harmonybrew 官方仓库生效，自有 tap 的 PR 仍按会话默认规则带 attribution。已经推上去的话用 `git commit --amend`（分支 tip 是自己的 commit）+ `git push --force-with-lease fork <branch>` 改。
- 类型/revision/bottle 处理跟着最近的同类已合并 PR 抄：纯结构对齐（不改版本号）标 `修复/增强`，`bottle do` 的 sha256 不用自己填/改，官方那边有自己的自动化在 PR 合并后单独提交 `<formula>: update <version> bottle.` 回填。
- **准入在 Acceptable-Formulae 之上还有两条官方硬性追加**：① formula 注释一律英文（与上游仓库语言一致）；② **最小化修改原则**——每处改动必须满足其一：少了它在 ci-runner 环境里构建/测试必失败，或少了它 formula 业务功能在 OpenHarmony（含 HarmonyOS 商用版）设备上必出问题。拿不准的改动点按这个标准逐条自我裁决，别等评审打回；全量重写上游已有 formula 的，PR 描述必须注明原因。
- **上游 Homebrew/homebrew-core 已有的 formula 必须直接搬运上游文件，严禁从零手写**（`curl -fL` 拉 upstream raw 到首字母目录，构建配置/依赖关系与上游保持一致），OHOS 适配只在其上做最小修改；Aliases 软链接一并创建。全新手写 formula 维护者会手工过 `brew style`/`brew audit`，校验不过拒收。
- **commit message 三段官方格式**：新增 `<formula> <version> (new formula)` / 版本升级 `<formula> <version>` / 修复增强 `<formula>: <action>`（例：`tcl-tk: update livecheck blocks`）；MR 标题与 commit message 保持一致。
- **官方门禁是「一个 PR → 一个 commit → 一个 formula」**：多 commit、一个 commit 动多个 formula 都会被流水线直接拦截；整改方式就是把分支压成单 commit 后 `git push -f`（与自有 tap「禁 squash」正好相反，别套错）。revision 规则与自有 tap 相同：升版本删 `revision`、改产物 +1、纯注释/格式改动不动。
- **合并机制**：MR 开好后由维护者加 `request-ci` 标签（=评审通过）触发流水线门禁/构建/测试/打包，机器人把构建日志贴进讨论区；成功后机器人生成「替代 PR」（平台不支持 Allow edits by maintainers 的妥协，内含原始 commit + 机器人一条 commit），随后两个 PR 一起被机器人合并（扫描周期约 10 分钟）。AtomGit 账号绑定 git 邮箱后才进仓库贡献者列表——commit 邮箱与本机 git 配置一致即可。
- **补丁制作走官方附录标准法**：两份干净源码树 `diff -ruN a b > 0001-add-ohos-support.patch`（与自有 tap「hunk 机器重生成、禁手改 `@@`」同一条纪律），放 `Patches/<formula>/`；官方验证环是 ci-runner 容器内 `brew install -y -s -v --include-test <f>` + `brew test <f>`（真机 `brew install -s` 被包管理器代码层禁止，勿绕过）。C/C++ 条件编译用 `__OHOS__` 宏（编译器自动传入）；Harmonybrew 业务逻辑全走 Linux 分支，适配可直接改 Linux 部分不影响其他平台；耗时的构建放后台跑，避免超时被杀重来过。

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
