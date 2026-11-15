## Qt 应用（Qt for OHOS）

先读 `gui-apps.md`：HAP 沙箱、签名与交付分工、权限、专用 CI 镜像、真机验收都通用，本文只写 Qt 特有的部分。范例 formula：`snow-shot`。**目前只有一个应用实测过，下面是已验证的做法，遇到新现象以实测为准并回来补。**

1. **Qt SDK 来自专用 CI 镜像，不是 formula 依赖**：Qt for OHOS SDK 是预编译的，固定在镜像里的路径下；formula 在 `install` 开头 `odie` 守卫该路径是否存在，镜像用 `OHOS_CI_IMAGE_OVERRIDES` 按 formula 指定（见 `gui-apps.md` 第二节）。
2. **cmake 消费 SDK**：`CMAKE_TOOLCHAIN_FILE` 用 SDK 的 `qt.toolchain.cmake`，`QT_CHAINLOAD_TOOLCHAIN_FILE` 指 brew `ohos-sdk` 的 `ohos.toolchain.cmake`；**`-DOHOS_ARCH=arm64-v8a` 必须用 `-D` 传**，`qt.toolchain` 会清空它，环境变量无效。用 qmake 的话，SDK 的前缀配成了 `<SDK>/lib`，要自写 `bin/qt.conf`（`[Paths]` 的 `Prefix=..`）。
3. **SDK 不带的模块自己补**：`QtSvg` 直接源码构建（`QT_HOST_PATH` 指向 SDK，host 与 target 同为 aarch64，能原地跑）；`LinguistTools` 要 host 版的 qttools；翻译包等作为 `resource`。
4. **编译器与标准库**：NDK 自带的 libc++ 没有 C++20 的 `<stop_token>`/`jthread`，vendor `josuttis/jthread`（header-only，条件变量类名与标准的不同，使用点要改）；aarch64 的 CRC intrinsic 要加 `-march=armv8-a+crc`；上游的 `-Werror` 会被较老的 clang 批量误伤，**条件化，别全局去掉**。
5. **打 HAP 用 `harmonydeployqt`**：吃一份 JSON，**必须带完整的部署目录**：`ndk-root`、`qtLibsDirectory`、`qtPluginsDirectory`、`qtLibExecsDirectory`、`qtHostDirectory`，第三方库目录放 `extra-libs-dirs`（工具用 NDK 的 `llvm-readobj` 递归收集依赖）。缺字段时只打印 "llvm-readobj not found"、"Could not find Qt plugins directory" 之类**非致命警告**，却会产出只有 app 自己库的 HAP，装机后 ArkTS 因缺 `libqohos.so` 直接退出。
6. **调用写法**：让 `harmonydeployqt` 直接输出到构建日志，别重定向到文件再在失败时读——重定向目标没创建会抛 ENOENT 盖住真错。`Formula#system` 成功返回 `nil`、失败抛 `BuildError`，**别判断它的返回值**。
7. **`libz` 要手动补**：部署工具把 `libz*` 当系统库跳过，但鸿蒙 PC 的应用命名空间里没有 `libz.so.1`，freetype 之类需要它。部署后显式复制 brew 的 zlib 到 HAP 的 `libs/arm64-v8a`，并加测试断言。
8. **`.so` 的签名**：clang 直出的可执行文件能跑，但**被 `dlopen` 的 `.so` 在本机一律 `Permission denied`**，要 `binary-sign-tool sign -selfSign 1` 补签后才行——可执行文件和 `.so` 行为不一致，很容易误判。formula 里不放签名步骤（见 `own-tap.md` 第 6 条），本机单测 `.so` 时记得补签，最终以真机装机结果为准。
9. **formula 测试要断言 HAP 内容**，因为 `bm install` 和 `aa start` 成功不代表能运行：
   - 清单里有 `libqohos.so`、用到的 Qt 模块、第三方运行库，以及上面第 7 条补的 `libz`；
   - `module.json` 的 `bundleName`、ability 名、权限（如截屏类的受限权限）、图标；
   - 打进去的数据资源（模型、字典等）校验大小和 sha256；
   - 真机装机后查 `hilog` 和截图，别只看安装与启动是否成功。
10. **没有 HAP 时的逻辑验证**：Qt 应用的独立可执行文件可以用 `offscreen` 平台在命令行跑，适合验证非界面逻辑；界面行为必须在 HAP + `libqohos` 下验证。
