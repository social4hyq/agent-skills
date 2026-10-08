# OHOS 适配速查

构建/测试挂了再来对照，不预读。

## 底数

- 用户空间是 **musl**，与 Alpine musl、glibc 都有出入；NDK clang 自动定义 `__OHOS__`，**同时也定义 `__linux__`**（别以为落进 Linux 分支就安全）。
- Rust triple `aarch64-unknown-linux-ohos`：`target_os="linux"`、`target_family="unix"` 为真，但 `target_env="ohos"` —— **不是 `"musl"`**，crate 里 `cfg(target_env="musl")` 的分支会静默跳过。
- Homebrew 在鸿蒙上全走 Linux 业务逻辑，改 formula 直接改 Linux 分支。CMake toolchain：`/opt/ohos-sdk/ohos/native/build/cmake/ohos.toolchain.cmake`。

## 容器 ≠ 真机

ci-runner 跑在 vanilla Linux 内核上，真机的 HongMeng 内核另外屏蔽一批能力：

| 能力 | 容器 | 真机 |
|---|---|---|
| `LD_PRELOAD` | ✅ | ❌ **垫片方案只能在容器验证，真机必须换源码级修法** |
| `seccomp` filter／`clone3`／`ptrace(TRACEME)` | ✅ | ❌ |
| `landlock`／`bpf`／`userfaultfd`／`fanotify`（用 `inotify` 替代）／`fchmodat2` | ❌ | ❌ |

**SIGSYS 模式**：被拦的 syscall 直接杀进程，拿不到 errno 回退机会——"先走乐观快路径、失败再降级"的代码（`close_range`、`clone3`）必须改成根本不走。

## 报错 → 修法

| 现象 | 根因 | 修法 |
|---|---|---|
| Rust `E0425`/`E0432`，或功能分支静默没进去 | cfg gate 把 OHOS 排除了 | 升级 crate（`nix`≥0.30／`crossterm`≥0.27／`mio`≥1.0／`libc`≥0.2.169），或改成 `any(target_env="ohos", target_env="musl")` |
| `undefined reference to pthread_cancel`／`pthread_setcancelstate` 无效 | musl 不导出或语义不同 | `#ifndef __OHOS__` guard，或 `pthread_kill(SIGUSR1)`+标志位重实现；范例 `Patches/git/0001-disable-pthread-setcancelstate.patch` |
| `execveat` 链接失败 | 符号永久不导出 | `syscall(SYS_execveat, ...)` 直调，**不要** `extern "C"` 声明 |
| `'program_invocation_name' undeclared`／`_res` 缺失 | glibc 专有 | 换 `__progname`／`getaddrinfo()`；`defined(__GLIBC__)` 已隐式排除 musl，不必再叠 `!__OHOS__` |
| `freadahead.c: invalid use of incomplete type` | gnulib 探测 musl FILE 失败 | 已知 libc 分支末尾加 `#elif defined __OHOS__`；coreutils/findutils/m4/tar/sed/grep 同一个坑，**直接复用 `Patches/coreutils/0001-port-gnulib-to-ohos.patch`** |
| configure 不识别 host triple | `config.guess`/`config.sub` 没有 OHOS | 加 `linux-ohos*`／`LIBC=ohos` 分支；若禁个可选功能就能绕过，优先禁功能 |
| C 扩展 require 报 symbol not found | 动态链接器命名空间隔离，dlopen 模块回溯不到主二进制符号 | 链接时 `-Wl,-z,global`，比全静态内建轻量 |
| TLS 相关 SIGSEGV | OHOS clang 默认 emulated TLS | 全局加 `-fno-emulated-tls`（只加在局部 flag 上不生效） |
| `tmpfile()` 返回 NULL、Go 报缓存目录失败 | 应用沙箱无 `/tmp` 写权限 | `mkstemp()` + fallback 链；Go 硬编码 `GOCACHE`/`GOTMPDIR`，范例 `Patches/go/0001-gocache-default.patch` |
| Python `_musllinux` 检测不出 musl 版本 | 动态链接器路径不含 "musl" | patch 成硬编码返回 `(1, 2)` |
| `try_run`/`CHECK_*_SOURCE_RUNS` 失败 | 交叉编译下不可用 | 预填 `-DRUN_RESULT` 或换 `try_compile` |
| cargo fetch 卡住／20-30KB/s | crates.io 直连 | 配镜像（见下） |
| pnpm/cargo/napi-rs 找不到配置 | superenv 过滤了环境变量 | formula 内显式 `ENV[...]`（见下） |
| git clone 大仓库超时 | 几百 MB | 换 `https://codeload.github.com/<org>/<repo>/tar.gz/<sha>` |
| npm 包缺 `openharmony-arm64` 二进制 | 上游未发布该平台 | 先查上游新版，再查 `@ohos-npm-ports` scope；都没有才自制——走 `npm-porting` skill |
| NDK clang 太旧编不动现代 C++ | LLVM 版本低 | Alpine 与 OHOS 共享 musl ABI，可在 Alpine chroot 里用 GCC 构建（仅限不需要 OHOS 特有头文件/系统库），LDFLAGS 加 `-static-libgcc -static-libstdc++` |

## `#ifdef __linux__` 要不要加 `|| defined(__OHOS__)`

**man 2 的加，man 3 的不加**——内核 syscall（fork/gettid/sendfile/epoll）加；glibc API（confstr/mallinfo2）、新内核特性（pidfd_open/io_uring/clone3）、系统路径工具（/sbin/ldconfig）都不加。

## superenv

superenv 会改写/过滤构建环境，按需显式设回；cargo 镜像写进 `$CARGO_HOME/config.toml`（备选 rsproxy.cn／tuna，镜像偶发不可用先 `curl -I` 预检）：

```ruby
ENV["CARGO_HOME"] = "/root/.cargo" if File.directory?("/root/.cargo")  # HOME 被改成 buildpath/.brew_home
ENV["OHOS_SDK_PATH"] = "/opt/ohos-sdk/ohos"   # napi-rs 等需要，会被过滤
ENV["RUSTC_BOOTSTRAP"] = "1"                  # stable rustc 解锁 -Z bindeps
```

```toml
[source.crates-io]
replace-with = "ustc"
[source.ustc]
registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"
[net]
git-fetch-with-cli = true
```

上游用 `../crate` 引用 workspace 时，`resource` 要 stage 到 `buildpath.parent`，放子目录会让 workspace 继承错乱。

## 补丁参考库

官方 core 近百份已合入：`ls $(brew --repo harmonybrew/core)/Patches`——同类问题优先复用，写法照抄。再不够查 [aports](https://gitlab.alpinelinux.org/alpine/aports)（musl 兼容补丁总库）与 [termux-packages](https://github.com/termux/termux-packages)（沙箱与非 FHS 路径实践）。
