## 场景三：跟上游 Homebrew formula 最小化 diff

适用于下游 formula 跟随 Homebrew 上游同名 formula（macOS/Linux 也在构建）。目标是 `diff -u` 只剩流水线与 OHOS 必需项：

```sh
curl -fsSL https://raw.githubusercontent.com/Homebrew/homebrew-core/main/Formula/{subdir}/{formula}.rb -o upstream.rb
diff -u upstream.rb Formula/{subdir}/{formula}.rb
```

逐行过：**能保留的保留，能移除的移除，能不改的不改，必须适配的放补丁，能不用 wrapper 就不用。**

1. **对齐上游工具链**：依赖和构建环境变量回到上游写法（例如上游 `rust` + `RUSTC_BOOTSTRAP=1`，就别因为历史原因留 `rustup`）；本机网络便利（crates.io 镜像回退之类，构建只走 CI）直接删；疑似冗余的环境变量先试删，让 CI 判决，失败再按日志逐条恢复。
2. **适配进补丁，不进 formula 代码**：`Patches/{formula}/NNNN-*.patch` + `patch :p1 do file "Patches/…" end`。`inreplace`、`File.write` 改文本、在 install 里生成源码，凡是对固定文件的文本修改都改成补丁；对 `resource` 也一样，把 `patch` 块写在该 resource 内。例外：由 resource 或版本表在构建期动态算出的内容（如复制二进制进 shim 目录）补丁表达不了，留在 formula。
3. **OHOS 专有部分用 `if OS.ohos?` 守卫**（范例：Harmonybrew core 的 `openjdk@21.rb`）：OHOS 才需要的 `depends_on`、`resource`、`patch` 声明、install/test 里的步骤各自圈进 `OS.ohos?`，其余平台保持上游行为——该 OHOS 改掉的参数对别的平台要还原（如 `--no-optional` 对非 OHOS 保留、测试里上游的断言保留），拿不准能否在别的平台验证的 OHOS 步骤也一并圈进去。
4. **能不用 wrapper 就不用**：先问 wrapper 做了什么能否落进补丁。陷阱：wrapper 的 `exec target "$@"` 会让被调用二进制看到的 `argv[0]` 变成 target 名，靠 argv[0] 区分身份的多调用二进制（如 `vpr`/`vpx` 指向 `vp`）会错位；`write_env_script` 也是同样的 `exec`，同样有这个问题。环境默认值（如 `/tmp` 只读时的 `TMPDIR`）做成 OHOS 补丁，进程启动时若未设置再补上，已设置的不覆盖。
5. **别随手改上游默认值**：先读上游的首次启动、回退逻辑，用上游默认值的二进制在隔离 HOME 里实测。改默认值会牵动一串"默认值假设"（序列化时跳过默认值的判断、快照、测试），而上游逻辑往往已经覆盖了需求。
6. **补丁写法**：单一目的，按"构建修复"与"行为改动"拆开；头部只写**一行**说明（`OHOS: …`），不要 mbox 的 `From:/Date:/Subject:` 和长段背景；按应用顺序编号；用带上下文的 `git diff` 生成，不手改 `@@`，零上下文的 diff 会被应用到错位置。验证：对干净检出做 `git apply --check` 再真应用，结果与实测过的版本逐文件 `cmp`；不要在某个 git 仓库的子目录里验证，`git apply` 会以仓库根为准、静默跳过范围外的文件。
7. **用户必须自己设置的，放进 caveats**（静态文本）：如 OHOS 上首次交互启动的提示怎么答、需要导出哪个环境变量。别用改默认值或 wrapper 替用户做。
8. **对齐上游依赖要查运行时链接**：上游用系统库（如 `sqlite` + pkg-config），在 OHOS 上可能让原生模块动态链接 Homebrew 的库。被其他宿主 `dlopen` 的 `.node`/插件自己没有 `RUNPATH`，只在带 Homebrew `RUNPATH` 的宿主（如 Homebrew 的 node）下能加载，换成官方镜像的 Node 就 `dlopen` 失败。这类依赖在 OHOS 上守卫掉、保持静态打包；改完用 `readelf -d` 看 `NEEDED`，并用非 Homebrew 的宿主实际 `dlopen` 一次。
9. **测试种子要核对身份**：给测试 harness 预置的运行时（如 `js_runtime/node/<版本>`）别用别名冒充，建好后逐个跑 `bin/node -p process.version` 和目录名比对；冒充的版本会让依赖具体版本的用例悄悄跑在错误的运行时上，也会掩盖真实回归。
10. **粒度与证据**：每个 PR 只改一个 formula；工具链对齐、去 wrapper、补丁整理分开提，哪个 CI 挂了好单独回退。有行为影响的补丁要在隔离 HOME 用补丁后的二进制做行为探针，并回归受影响的测试，不要只看 `brew style`/`audit`/`readall`；这三项不会替你跑构建。

