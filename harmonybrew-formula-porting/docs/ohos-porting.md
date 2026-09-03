# 鸿蒙/OpenHarmony 适配知识（formula 视角精选）

> 随 skill 分发的参考，独立维护。覆盖：平台事实、构建系统适配模式、方法论、陷阱速查。表格中的 § 引用指向本文自身小节。

## 1. 平台特性

### 1.1 Rust target triple

`aarch64-unknown-linux-ohos` 的关键语义：

| cfg 谓词 | 值 | 含义 |
|----------|-----|------|
| `target_os` | `"linux"` | Linux family，`cfg(target_os="linux")` 为 true |
| `target_env` | `"ohos"` | **不是** `"musl"`，`cfg(target_env="musl")` 为 false |
| `target_family` | `"unix"` | `cfg(unix)` 为 true |
| `target_arch` | `"aarch64"` | ARM 64-bit |

大多数 crate 的 Linux 分支用 `cfg(target_os="linux")` 做 gate，OHOS 上自动激活——nix/io/fs 路径直接可用，但某些 Linux 特定 syscall 编译报错。

### 1.2 HongMeng kernel 屏蔽清单

openharmony 容器跑在 vanilla Linux 6.6 内核上，HarmonyOS 真机的 HongMeng Kernel 主动屏蔽：

| 能力 | openharmony 容器 | harmonyos 真机 | 影响 |
|------|-------------|-----------|------|
| `seccomp(SECCOMP_SET_MODE_FILTER)` + `NEW_LISTENER` | ✅ | ❌ EINVAL | fspy supervisor 不可用 |
| `LD_PRELOAD` honor | ✅ | ❌ 不生效 | preload 拦截链路真机不可用 |
| `clone3` | ✅ | ❌ SIGSYS | tokio 优化不可用 |
| `ptrace(PTRACE_TRACEME)` | ✅ | ❌ EPERM | 调试器后备路径不可用 |
| `landlock_create_ruleset` | ❌ ENOSYS | ❌ SIGSYS | Landlock 不可用 |
| `bpf` (BPF_MAP_CREATE) | ❌ EPERM | ❌ SIGSYS | eBPF 不可用 |
| `userfaultfd` | ❌ EPERM | ❌ ENOSYS | 用户态缺页处理不可用 |
| `fanotify` | ❌ EPERM | ❌ SIGSYS | 用 `inotify` 替代 |
| `fchmodat2` (SYS 452) | ❌ ENOSYS | ❌ ENOSYS | 用 `fchmodat` + AT_SYMLINK_NOFOLLOW |

注意 SIGSYS 模式：**被拦的 syscall 拿不到 errno 回退机会**——依赖"失败后降级"设计的代码（如 close_fds 的 `SYS_CLOSE_RANGE` 乐观快路径）会直接被杀。

双轨均不可用/均可用（与 HongMeng 无关）：`CAP_SYS_PTRACE` 双 fail（环境 drop，非内核）；`execveat` 符号 musl 永久不导出（`syscall(SYS_execveat)` 直调可用，见 §3.3）；shm/memfd/eventfd/signalfd/epoll/socketpair/SCM_RIGHTS/`/proc/self/*` 双轨完整可用。

**方法论**：有 openharmony 容器（可选）时先测它（OHOS userspace 能力上限），再测真机（实际可用），diff = 需向系统侧申请的放权清单；无容器则直接以真机为准。真机不可用 `LD_PRELOAD` 意味着：**兼容垫片方案只能在容器里验证，真机验证必须换源码级修法**（或 tap 内已内置 shim 的 wrapper 路线）。

## 2. 运行环境差异

### 2.1 三层安全模型

```
文件访问请求
    ↓
SELinux (MAC) → 拒绝/允许 ← 最终裁决者
    ↓ (通过)
HMDFS (UID 映射) → 虚拟化文件系统
    ↓
Unix 权限位 (DAC) → 忽略（装饰性，chmod/chown 返回成功但权限不变）
```

### 2.2 SELinux 域与执行

- `hishell_hap:s0` — Shell，高权限；`adhoc_bin:s0` — 用户程序，受限；`hnp_file:s0` — SDK 工具
- `adhoc_bin` 域进程 `fork+execve` 执行 `hnp_file` 二进制会被拦截；`posix_spawn()` 不受限——需要拉起 SDK 工具时优先用 `posix_spawn`

### 2.3 HMDFS 文件系统

`chmod()` 与 POSIX 不同（无 portable 替代）：group 强制 `rw-`、other 强制 `---`、owner 最低 `rw-`。**不能依赖 chmod 做权限隔离**（`chmod 000` 实际 `0o660` 仍可读写），真正隔离靠 SELinux 域或 UID 映射。

HMDFS 路径下创建 symlink 可能失败——必须用先 `access()` 探测。

`/proc/self/maps` 可能返回内核内部路径无法 open——解析自身 `.so` 路径改用 `dladdr()`（libffi trampoline 自定位等场景）。

### 2.4 musl libc 差异

OHOS userspace 用 musl（`ld-musl-aarch64.so.1`），但与 Alpine musl、glibc 都有差异。缺失/受限符号与修法：

| 缺失/受限 | 修法 |
|---|---|
| `pthread_cancel`（双轨缺失） | `#ifndef __OHOS__` 跳过调用点；或 `pthread_kill(SIGUSR1)`+标志位重实现（ruby 模式） |
| `pthread_setcancelstate`（符号存在但可能 no-op） | 不可靠，同上 guard |
| `execveat`（永久不导出） | `syscall(SYS_execveat)` 直调，见 §3.3 |
| `_res`（DNS resolver state） | 改 `getaddrinfo()` |
| `program_invocation_name`（glibc 专有） | musl `__progname` 等效替代 |
| `getpass` / `getusershell` 系 | 符号实际存在，历史 guard 可清理 |

**gnulib FILE 结构**：任何用 gnulib 的软件（coreutils/findutils/m4/tar/sed/grep）都会在 `freadahead.c` 撞 musl FILE 探测问题，在已知 libc 分支末尾加 OHOS 分支（`#elif defined __OHOS__` 读 `f->rend - f->rpos`）。多个 formula 撞同一 gnulib 模块错误时直接复用已有 patch。

### 2.5 应用沙箱与身份

- 应用 UID ≥ 20000000 且无 passwd 条目：git 的 ownership 检查、nginx 的 user 解析在此类 UID 下失败——检查逻辑对 `geteuid() >= 20000000` 放行
- `tmpfile()` 沙箱中失败 → `mkstemp()` + TMPDIR fallback 链（`$TMPDIR` → `/tmp` 探测 → `/data/storage/el2/base/cache`）

### 2.6 toybox 与系统工具差异

`sed` 不支持复杂多行块与分支命令；`awk` 功能有限；`expr` 不支持复合正则 `\|`。autotools 项目注意：configure 阶段（容器 GNU sed）生成与运行阶段（真机 toybox）行为可能不一致。

### 2.7 路径约定速查

| 路径 | OH 容器 | HM 真机 | 用途 |
|------|---------|---------|------|
| `/dev/fd` | ✅ | ✅ | 替代 `/proc/self/fd` |
| `/system/bin/sh` | ❌ | ✅ | 标准 shell（鸿蒙特有） |
| `/dev/ptmx` | ✅ | ✅ | PTY |
| `/data/local/tmp` | ❌ | ❌ | 双轨均不可用 |
| `/data/storage/el2/base/files` | ✅ | ✅ | 应用私有文件（Go GOCACHE） |
| `/data/storage/el2/base/cache` | ✅ | ✅ | 沙箱可写路径（tmpfile fallback） |
| `/tmp` | ⚠️ | ⚠️ | 部分沙箱可访问，需 `access()` 探测 |
| `/storage/Users/currentUser` | — | ✅ | HarmonyPC 用户存储 |

### 2.8 libc++ ABI 命名空间

全链路已统一 `__n1`（llvm@21/bun 均已迁移）；新建 C++ 工具链产物必须与 `__n1` 对齐。历史 `__h` 时代的兼容问题已消亡。

## 3. 构建系统适配模式

### 3.1 Rust/Cargo

**cfg gate 正确写法**：

```rust
#[cfg(target_os = "linux")]          // ✅ OHOS 自动走 Linux 路径
#[cfg(all(target_os = "linux", not(target_env = "ohos")))]  // ❌ 把 OHOS 排除了
#[cfg(target_env = "ohos")]          // ✅ 需要区分 OHOS 时
#[cfg(any(target_env = "ohos", target_env = "musl"))]       // ✅ 兼容 musl 系
```

常见 crate：`nix` ≥0.30 才有 OHOS gate（升级）；`libc` 部分符号无绑定（syscall 直调）；`crossterm`/`mio` 用 `target_family="unix"` gate（升级到新版）。

**镜像**（crates.io 直连 20-30KB/s 必配）：

```toml
[source.crates-io]
replace-with = "ustc"
[source.ustc]
registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"
[net]
git-fetch-with-cli = true
```

备选 rsproxy.cn / tuna；`CARGO_HTTP_CAINFO` 可能需指向系统 CA 包。

**关键依赖版本线**：`nix` ≥0.30、`crossterm` ≥0.27、`mio` ≥1.0、`libc` ≥0.2.169。`core::ffi::VaList` 的方法名随 rustc 版本变（`arg::<T>()` → `next_arg::<T>()`，rust-lang/rust#141980）——旧 rustc 对新写法做重命名 patch。

**autotools**：`config.guess`/`config.sub` 不识别 OHOS——加 `LIBC=ohos` 分支 / `linux-ohos*` triple。

**`-Wl,-z,global`**（设 `DF_1_GLOBAL`）：OHOS 动态链接器命名空间隔离导致 dlopen 模块无法回溯主二进制符号（ruby/perl C 扩展、zsh 模块），链接时加此 flag 恢复标准行为——比全静态内建轻量。

**`-fno-emulated-tls`**：OHOS 不支持 GCC emulated TLS（openjdk 等需要）。`__OHOS__` 宏由 NDK clang 自动定义，无需 `-D`。

### 3.2 Homebrew superenv 机关

superenv 在源码构建时会过滤/改写环境，formula 的 `install` 里显式处理：

```ruby
# 必选项（Rust formula）
ENV["CARGO_HOME"] = "/root/.cargo" if File.directory?("/root/.cargo")  # superenv 把 HOME 改为 buildpath/.brew_home

# 按需
ENV["OHOS_SDK_PATH"] = "/opt/ohos-sdk/ohos"   # napi-rs 需要，superenv 会过滤
ENV["RUSTC_BOOTSTRAP"] = "1"                  # nightly 特性（-Z bindeps 等）
ENV["NPM_CONFIG_MANAGE_PACKAGE_MANAGER_VERSIONS"] = "false"
```

- **Cargo workspace sibling staging**：上游经 `../crate` 引用外部 workspace 时，`resource.stage` 到 `buildpath.parent`（不是 buildpath 子目录，workspace 继承会乱）
- **大仓库用 codeload tarball**：`https://codeload.github.com/<org>/<repo>/tar.gz/<sha>` 几 MB 秒下，git clone 几百 MB 必超时
- **`[patch.crates-io]` 注入**：向 `Cargo.toml` 追加 section 把 crate 替换为本地 patched 版本

### 3.3 syscall 直调（libc 缺符号时）

编译期常量可用、运行时走内核——用 `libc::syscall(libc::SYS_execveat, ...)`，不要 `extern "C"` 声明（musl libc.so 无该符号，链接失败）。

### 3.4 Python virtualenv formula

纯 Python 通常零 patch；C 扩展（psutil 的 ioctl、ruamel-yaml-clib 的 headers）按报错打 patch。

```ruby
include Language::Python::Virtualenv
depends_on "python@3.14"
def install = virtualenv_install_with_resources
```

pip 的 `_musllinux.py` 在 OHOS 检测不出 musl 版本（动态链接器路径不含 "musl"）→ 硬编码返回 `(1, 2)`。

**Go**：`os.UserCacheDir()`/`os.TempDir()` 沙箱失败 → 硬编码 `GOCACHE`/`GOTMPDIR` 到可写路径；CGO_ENABLED=0 静态产物有签名坑（见 SKILL.md 签名节）。

### 3.5 npm/Node native binding

npm 包缺 `openharmony-arm64` 平台二进制时：**先查上游新版本是否已原生支持，再查社区 port（`@ohos-ports`/`@ohos-npm-ports` scope）overrides 复用**——都不行才手工编译注入（`cargo build` + 把 `.node` 装进 pnpm store 的包目录），移植路径判定与 port 制作走 `npm-porting` skill。

### 3.6 Alpine chroot 构建策略

OHOS NDK clang（LLVM 15）太旧编不动现代 C++ 时：Alpine 与 OHOS 共享 musl libc ABI，chroot 里用原生 GCC 构建，产物直接可跑。

- 适用：目标 musl、NDK 编译器太旧、构建依赖在 apk 里、**不需要** OHOS 特有头文件/系统库
- 要点：LDFLAGS 加 `-static-libgcc -static-libstdc++`（或 Node 的 `--partly-static`）；`env -i` 执行 chroot 防环境泄漏；复制宿主 `resolv.conf` 进去才能 `apk update`；rootfs 架构必须与目标一致
- Node.js 是完整案例：上游 `--dest-os=openharmony` 一等支持，chroot 构建、35 个 gyp 条件中 30 个复用 Linux 路径、仅 2 处源码守卫——**上游一等收录后改动面趋近于零**

### 3.7 CMake 项目适配

toolchain file：`/opt/ohos-sdk/ohos/native/build/cmake/ohos.toolchain.cmake`（`CMAKE_SYSTEM_NAME Linux` + `aarch64-unknown-linux-ohos` triple）。陷阱：交叉编译下 `try_run`/`CHECK_*_SOURCE_RUNS` 不可用（预填 `-DRUN_RESULT` 或换 `try_compile`）；`find_package` 查的是 NDK sysroot；NDK 自带 CMake 可能较旧，别用高版本特性。

### 3.8 bun 单体二进制（`bun build --compile`）移植模式

四条实测硬规则（opencode 为完整案例）：

1. **资产嵌入只认 `with { type: "file" }`**：`new URL(..., import.meta.url)` 模式 bundler 不嵌入（`/$bunfs` 路径存在但文件没进去，TUI 初始化 dlopen 时报 "not supported"）；`--version` 级 smoke 测不出来，**验证必须含 pty 级 smoke**（`timeout 10 script -qec "<bin>" /dev/null`，检查无 dlopen 报错且活到超时）
2. **预签名 `.so` 免运行时签名**：npm 包内 `.so` 先 self-sign 再发布，compile 嵌入字节保真，解包后 `.codesign` 段有效
3. **bundler 平台包解析 × openharmony os 过滤叠加**：与 compile target 匹配的平台包缺失会硬报错，而 openharmony 上 `bun install` 的 os 过滤恰好把 `os:["linux"]` 包全跳过 → **OHOS 本机构建必挂而 linux CI 全绿**。修法：让构建脚本的 `bun install --os="*"` 跑起来（勿传 `--skip-install`）
4. **compile target 用 `bun-linux-arm64-ohos`（不是 musl）**：ohos target 烘焙 `process.platform="openharmony"` 且等于 `CompileTarget::default()`（直接嵌入运行中的真 ELF，不需本地 runtime 文件）；musl target 把 platform 烘焙成 "linux"，平台检测全走错分支。构建日志出现 runtime 下载即是配置错误；链接目标必须真 ELF（brew bun 的 `Cellar/bin/bun` 是 wrapper 脚本，真身 `libexec/bin/bun`）

## 4. 通用适配方法论

### 4.1 错误分类决策树

```
brew install -s 报错
 ├─ E0425/E0432 unresolved import → cfg gate 缺失 → patch cfg 或升级 crate
 ├─ E0599 method not found → 类型/method 版本差异 → 重命名 patch（验证语义等价）
 ├─ "undefined reference to pthread_cancel" 等 → musl 不导出 → syscall 直调 / guard / stub
 ├─ "'program_invocation_name' undeclared" → glibc 专有 → defined(__GLIBC__) 守卫
 ├─ "freadahead.c: invalid use of incomplete type" → gnulib FILE 探测 → #elif __OHOS__ 分支
 ├─ "tmpfile() failed" → 沙箱路径 → mkstemp() 替代
 ├─ cargo fetch 卡住 → 镜像未配置/不可用
 ├─ pnpm install 卡住 → registry 慢或 superenv 过滤 npm_config_* → .npmrc 写进 ENV["HOME"]
 └─ superenv 环境变量丢失 → CARGO_HOME / OHOS_SDK_PATH / npm_config_* 显式设置
```

### 4.2 修复内循环与上限

`brew install -s -v --include-test --keep-tmp` → 报错则「诊断（对照 §4.1）→ 改 formula/patch → 重跑」，直到 EXIT=0（零 patch 出口最好）。**MAX_ROUNDS = 3**：1 回合定位根因 → 2 验证修法 → 3 处理连锁；3 轮仍败说明根因诊断有误，ABANDON 记录诊断、另起 spike，不要无限修补。

### 4.3 Patch 组织与 fork-diff 不变量

- patch 文件头必须写三件事：现象、根因、何时可删（上游修复后的退出条件）
- 有活跃 fork 时（如 bun 的 `ohos-aarch64` 分支）**patch 不手写**，全部由 fork diff 生成，保持 patch ≡ fork diff：改动先进 fork commit，再 `git diff <upstream-tag>..dev -- <files>` 重新生成；同一文件多组改动交织时合为一个 patch（避免拆分顺序/偏移风险）
- 验证三件套：`git apply --check` + `patch -p1 --dry-run` + 真实应用后 **grep marker** 确认非 no-op（toybox patch 对错误 header 静默 exit 0）
- **inreplace 替代路径**：纯字符串替换、不涉及行号/上下文漂移的改动直接在 formula 里 `inreplace`（opencode 系现行形态）；多行结构性 diff 仍走 patch 文件

### 4.4 改动面边界

formula 工作只碰 `Formula/<首字母>/<name>.rb` 与 `Patches/**/*`，其他任何文件不动；每轮修改后 `git status --porcelain` 确认无越界改动。

### 4.5 上游 PR 提交策略

- 叙事口径：❌"下游需要这个 patch" → ✅"ecosystem gap: 同生态其他项目已支持该 target"
- 方案权衡优先级：升级依赖 → cfg gate patch → fork → vendor（vendor 最容易被拒，未 stable 项目上几乎必拒）
- commit 拆分：vendor/prep、bug fix（强调非 OHOS 价值）、feature、workaround、CI 各自独立——maintainer 可部分接受
- 现实预期：复杂综合案例（如 vite-plus）可能被拒多次转长期 carry patch；先推底层依赖（crate 绑定、libc 绑定）的上游 PR 是更好的重启姿势

### 4.6 `__OHOS__` 条件编译决策树

```
遇到 #ifdef __linux__ 条件
 ├─ 依赖内核 syscall？（fork/gettid/sendfile/epoll…） → ✅ 加 || defined(__OHOS__)
 ├─ 依赖 glibc API？（confstr/mallinfo2…） → ❌ 不加，musl 不同或缺失
 ├─ 依赖新内核特性？（pidfd_open/io_uring…） → ❌ 不加，鸿蒙内核未移植
 └─ 依赖系统路径/工具？（/sbin/ldconfig…） → ❌ 不加，单独处理路径
```

核心口诀：**"man 2 的加，man 3 的不加"**（`#include <sys/...>` 内核级可加；标准头文件 libc 级需确认 musl 行为）。OHOS NDK clang 定义 `__linux__`（勿以为 Linux 路径都安全）；`defined(__GLIBC__)` 已隐式排除 musl，无需再叠 `!defined(__OHOS__)`。

### 4.7 preload shim vs 源码的分工边界

**核心判据**：preload shim 只能拦截**经 libc 符号或 `syscall()` 入口**发出的调用并在失败时介入。

| 适配类别 | 提取到 shim？ |
|---|---|
| seccomp 拦截的 syscall（经 libc 入口） | ✅ 是（透明回退，源码分叉归零） |
| libc 函数行为异常（getpwuid_r/tmpfile/getcwd） | ✅ 是 |
| 内联汇编 syscall（rustix linux_raw/naked_asm） | ❌ shim 不可达 |
| 策略/逻辑（监控、手解、规避整套） | ❌ 非单点失败 |
| 路径/fs 逻辑、ABI/类型差异、ELF 签名、元数据、构建配置 | ❌ 结构性在 shim 之外 |

结论：可重编应用 shim 能干净提取的就是"经 libc 入口失败的 syscall"一类（通常 3-6 个），其余必须留源码。**能 shim 的先 shim 最大化减少上游分叉，其余源码修**；反过来，**已经源码修掉的 syscall 调用，发现 shim 能兜时也别留 shim**（zellij close_fds 案例：vendor 一行补丁 > LD_PRELOAD wrapper）。

## 5. 案例索引

| 案例 | 形态 | 演示的模式 |
|---|---|---|
| vite-plus | Rust workspace + pnpm（本 tap，最复杂） | §3.2 全套 superenv 机关 + 社区 fork overrides + pnpm deploy（详见 tap 文档） |
| node-ohos | C++/V8（本 tap） | 上游一等支持 + Alpine chroot 构建，零 OHOS patch |
| opencode / opencode@2 | bun compile（本 tap） | §3.8 全部四条规则 + inreplace + 社区 port 依赖 |
| zellij / herdr / zig@0.15 | Rust / Rust+zig / 预编译（本 tap） | 见 tap 文档逐案例教训 |
| yazi / hermes-agent / cryptography | 纯 Rust / Python venv / Python C 扩展（历史案例） | 模式已提炼进 §2/§3：纯 Rust 可能零 patch；Python 复杂度集中在 C/Rust 扩展 |

## 6. 已知陷阱速查

| # | 陷阱 | 现象 | 修法 |
|----|------|------|------|
| 1 | `target_os="linux"` 为 true 导致误激活 | Linux 特定 syscall 编译报错 | 加 `not(target_env="ohos")` gate（§3.1） |
| 2 | `target_env="musl"` 不匹配 OHOS | cfg gate 静默跳过，功能缺失 | 改 `target_env="ohos"` 或 `any(ohos, musl)`（§3.1） |
| 3 | VaList::arg vs next_arg | 多处 E0599 | 按 rustc 版本重命名 patch（§3.1） |
| 4 | crates.io 直连 | 拉取灾难性慢 | 配 USTC 镜像（§3.1） |
| 5 | superenv 过滤环境变量 | pnpm/cargo/napi-rs 找不到配置 | formula 内显式 ENV（§3.2） |
| 6 | 镜像偶发不可用 | cargo fetch 静默卡住 | 预检 `curl -I`；备选 rsproxy（§3.1） |
| 7 | CARGO_HOME 被 superenv 重定向 | cargo 用空配置目录 | 显式 `ENV["CARGO_HOME"]`（§3.2） |
| 8 | git clone 大仓库超时 | 几百 MB 必超时 | codeload tarball（§3.2） |
| 9 | npm 缺 openharmony prebuild | pnpm 静默跳过 optional dep | 查上游/社区 port/手工注入（§3.5 + npm-porting skill） |
| 10 | rust rpath 锁死 prefix | 换机器后找不到依赖 | 目标机 prefix 与构建机完全一致（见 container.md） |
| 11 | bottle 安装报 "requires the tap /tmp" | brew 把本地路径当 tap 名 | 放 cache 用 `<sha256>--<name>` 标准命名（§3.2） |
| 12 | `brew bottle --no-rebuild` 报未 build-bottle | INSTALL_RECEIPT 标记未改 | sed 改 `"built_as_bottle": true`（§3.2） |
| 13 | `cellar :any_skip_relocation` 写法 | undefined method | 只能内联写在 sha256 行：`sha256 cellar: :any_skip_relocation, arm64_ohos: "..."` |
| 14 | npm 镜像 CDN 滞后 | pnpm 找不到某版本 | 切 registry.npmjs.org 为主（§3.2） |
| 15 | pthread_cancel 未定义 | 链接报错 | `#ifndef __OHOS__` guard；ruby 标志位模式（§2.4） |
| 16 | getpass/getusershell 未定义 | configure/链接失败 | 符号实际存在，可清理历史 guard（§2.4） |
| 17 | program_invocation_name 未声明 | 编译报错 | glibc 专有，musl 用 `__progname`（§2.4） |
| 18 | config.guess/sub 不识别 OHOS | configure 失败 | 加 ohos triple 解析（§3.1） |
| 19 | 动态库符号不可见 | C 扩展 require 报 symbol not found | `-Wl,-z,global`（§3.1） |
| 20 | tmpfile() 返回 NULL | 沙箱无 /tmp 写权限 | mkstemp + fallback 链（§2.5） |
| 21 | /proc/self/maps open 失败 | HMDFS 内核路径 | dladdr() 解析（§2.3） |
| 22 | gnulib freadahead 编译错 | incomplete type | `#elif defined __OHOS__` 分支（§2.4） |
| 23 | musl 分支被静默跳过 | 功能缺失 | `cfg(any(target_env="musl", target_env="ohos"))`（§3.1） |
| 24 | NDK LLVM 太旧不支持 C++20 | 编译报错 | Alpine chroot + GCC（§3.6） |
| 25 | bun compile 不嵌入 URL 资产 | existsSync false，"not supported"；直跑正常 → 假象通过 | `with { type: "file" }` import；pty 级 smoke（§3.8） |
| 26 | os 过滤 × bundler target 匹配硬报错 | linux CI 全绿，OHOS 本机 "Could not resolve" | `bun install --os="*"` 跑起来（§3.8） |
| 27 | compile 误用 musl target | platform 烘焙成 linux，loader 分支全失效 | 改 `bun-linux-arm64-ohos`（§3.8） |
| 28 | 长构建经 docker exec 附着执行 | ssh 断连带崩、假完成、日志截断 | `docker exec -d` 分离 + 日志落容器内 + 按输出内容轮询（见 container.md） |
| 29 | splice() 源端 EOF 返回 -1/EPIPE | 拷贝循环文件尾误报（cat: -: Broken pipe） | 应用层改 read()/write()（§2.5 同类内核差异） |
| 30 | /proc/<pid>/stat 的 tty_nr/tpgid 恒 0 | 作业控制观测失效 | 改 waitpid(WUNTRACED)/tcgetpgrp() 查询（§2.5 同类） |
| 31 | PTY 行规程不生成信号 | 写 ^Z/^C 只回显不产信号 | 直接 `kill(-pgid, SIG...)`（§2.5 同类） |
| 32 | 缺 CONFIG_PROC_CHILDREN | children 文件不存在被当"无子进程" | 扫 /proc 按 stat 的 ppid 匹配（§2.5 同类） |

## 参考

- tap 现役 formula 与逐案例教训：`tap.md`（本 skill）
- openharmony 容器环境：`container.md`（本 skill）
- npm 包移植路径判定与 port 制作：`npm-porting` skill
- Harmonybrew 上游补丁库（参考他人 OHOS patch 写法）：`https://gitcode.com/Harmonybrew/homebrew-core`
