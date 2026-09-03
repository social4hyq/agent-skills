# OHOS 平台差异速查（npm port 视角）

每条均经真机或社区仓 PR 实证；按需查用，不是必读。

## 基本面

- aarch64 + musl（非 glibc）；`process.platform === 'openharmony'`（不是 linux）
- ELF 需带 `.codesign` 才能 exec/dlopen（两层签名：LLD CodeSign patch 链接期即签，或 `binary-sign-tool sign -selfSign 1` 补签；容器 CI 镜像的 LLD 自动签，zig 自带 LLD 不签）
- musl ldso 不做 lazy binding：`.so`/`.node` 的全部 UND 符号在 dlopen 时即解析，缺一个就整体失败（glibc 习惯的"没用到就不炸"不成立）

## OHOS musl 缺符号

- `pthread_tryjoin_np` 缺失（readelf/nm 双验，glibc 与标准 musl 都有）。上游代码引用它会让 dlopen 直接挂
  - 解法（zig，opentui-core 0.5.8 PR #22）：`@extern(T, .{ .name = ..., .linkage = .weak })` 返回 optional，`orelse` 回退
  - 解法（C/C++）：`__attribute__((weak))` 声明 + 运行时判空回退
  - 验收前 `env -u LD_PRELOAD`——shell 环境可能残留 opencode@2 的 tryjoin 垫片，会掩盖 weak 方案失效

## 缺 syscall（直接 SIGSYS 杀进程，不是 ENOSYS）

写构建/工具链相关代码时避让，port 的运行时代码更要注意：

- `fchmodat2`（docker CLI 拷出方向撞过；单文件拷出用 `docker exec cat >` 替代）
- `fanotify_init`（Go tsgo 在 init 里探测即崩；上游发 `-2` 修了优雅降级）
- `close_range`（zellij 间歇启动崩溃；vendor 补丁版 close_fds 绕开）

## dlopen 命名空间与符号可见性

- OHOS 动态链接器命名空间隔离：dlopen 加载的模块**不能回溯解析主二进制导出的符号**（zsh/ruby/perl 模块系统均受影响）；链接时 `-Wl,-z,global`（设 DF_1_GLOBAL）可恢复 Linux 行为
- 依赖宿主 C++ 符号的 addon（nan 类调 v8:: 符号）有硬 ABI 边界：调用方与宿主必须同 C++ 标准库实现——GNU libstdc++ 静态编的 node（Alpine chroot 产物）无法加载 libc++ 编的插件，mangled name 不同且无编译选项可桥接（pprof port 实测结论）

## 工具链行为（dockerharmony / ci-runner 容器）

- rustc host triple 即 `aarch64-unknown-linux-ohos`：cargo / `napi build --platform` 原生构建，无需交叉 target、无需自定义 rustflags
- **brew rust 只随带 ohos host std**：交叉编 musl/cargo-zigbuild 会 `can't find crate for core`——host 原生编译是最短路径（ast-grep 试错结论）
- `@napi-rs/cli` 2.x 不认 openharmony host：绕过 `napi build`，直接 `cargo build --release` + `.so` 改名成 loader 认的文件名（resvg-js 先例）；tag 树里的 `rust-toolchain` 文件删掉，避免 spurious rustup 查找
- napi-rs v3 平台名固定 `openharmony-arm64`（2.x 无）；rspack 系自家 loader 用 `linux-arm64-ohos`——动手前先读各包 loader 实际认哪个名字
- `@napi-rs/cli` 3.7+ 对 ohos target 无条件拼交叉链接器路径（原生构建也触发）：`export CARGO_TARGET_AARCH64_UNKNOWN_LINUX_OHOS_LINKER="$(command -v cc)"` 绕开
- **zig**：`aarch64-linux-ohos` target 产物引用 `__emutls_get_address`（OHOS libc 无）不可用，用 `aarch64-linux-musl`（与上游官方 musl 产物同构，`NEEDED libc.so`）；zig 0.16 缓存用 hardlink 原子安装，真机文件系统（hmdfs）拒绝 `link()`——构建必须在容器内完成（yuku 先例）
- **vendored crate 常见补丁**（turbo/nx/bun-pty 先例）：nix<0.30 首选升 0.30+（自带 ohos 支持），依赖者用 `^0.x` 钉死时改走 vendor 锁定版本打补丁——`[patch.crates-io]` 无法跨 0.x semver minor 重定向；其余套路：zstd-sys 扩展 `__ANDROID__` 的 qsort_r carve-out 到 OHOS（OHOS musl 无 qsort_r）、aws-lc-sys 放开 cc builder 按 linux 处理、jemalloc 排除 ohos
- **node-gyp (nan)**：显式 `brew install llvm@21` 再设 `CC=cc CXX=c++`——`llvm-gcc-compat` 默认退回的系统 clang 15 缺 node 头文件要的 `<source_location>`（pprof 先例）；`node-gyp-build` 系产物落 `prebuilds/openharmony-arm64/<name>.node.abi<N>.node`（N 为 ABI 版本，断言后命名）
- **Go**：brew go host 原生静态编译即可（typescript/tsgolint 先例），`-ldflags="-s -w" -trimpath`
- node 26 有 `--experimental-ffi`：`node:ffi` 能 dlopen 但 `ffi_closure_alloc` 失败（closure 不支持），loader 的 try/catch 兜底要匹配该错误消息；node 全功能 FFI 以 bun 为准（bun:ffi 原生支持，opentui-core PR #22 实测）
- CI 镜像无 git 二进制：build.sh 一律 curl tag tarball（codeload），别依赖 git clone（上游子模块用浅克隆 tarball 替代，tsgolint 先例）

## SIGSYS 修复模式

init() 里无条件探测的 syscall 会直接杀进程（不是 ENOSYS），err 防御路径没机会执行——修复靠运行时内核识别降级：`uname()` 判 HongMeng/HarmonyOS 内核返回 false，走上游自带回退后端（typescript 的 fanotify→inotify 先例，仿上游 android 特判）。

## npm 生态行为

- `npm install file:<目录>` = symlink 安装，不装该包依赖；tarball 才正常解析依赖
- bun 1.4 `build --compile` 用 `--outfile=`（`-o` 不是合法 flag）
- 工程接入未签名 `.node`：npm/pnpm 需 ohos-signpost；bun install / bun build --compile 已内置签名
- packageManager 字段（如 pnpm）在 openharmony 无对应 @pnpm/exe 发布，重打包时删掉（vite-plus 先例）
