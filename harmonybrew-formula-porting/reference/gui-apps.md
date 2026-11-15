## GUI 桌面应用（Electron 壳 / 通用 HAP）

适用于要以 HAP 形态交付的图形应用。Qt 应用另读 `gui-qt.md`。提交身份、先自有 tap 后官方等硬规则仍以 `SKILL.md` 开头为准。范例以 tap 里的 formula 为准（现成的有 Electron 壳的 `multica`、`opencode-desktop`，Qt 的 `snow-shot`），本文只写**从多个应用里反复验证过的共性**，不重复版本号和 PR。

### 一、先定形态：沙箱决定架构

1. **HAP 沙箱读不到宿主、执行不了宿主**：HAP 进程的 uid 是应用专属的，访问不了宿主家目录，也执行不了 brew 里的 CLI；沙箱内起的子进程会随 app 退出被杀（detached/setsid 都没用）。需要宿主能力（执行 CLI、读写宿主配置、常驻 daemon）的应用，别把 daemon 塞进 HAP，做成**宿主常驻进程 + 回环 HTTP**：只监听 `127.0.0.1`、Bearer 鉴权、命令白名单、路径严格校验。HAP 只有 `INTERNET` 权限就能访问回环。
2. **签名与交付分工**：formula 只产**未签名 HAP**放进 bottle，用户在本机用 `hap-installer` 签名、安装、启动（提供一个 `install` 命令封装）。签名材料、凭据、配对密钥都不进 bottle；需要注入的配置在安装时写进**签名副本**，bottle 里的 HAP 不改。凭据烧在 HAP 里的，更换后要重跑安装命令。
3. **权限默认取自动签名能授予的最小集**（`INTERNET`、`GET_NETWORK_INFO`）。`system_basic` 级权限（如 `CUSTOM_SANDBOX`、`READ_WRITE_USER_FILE`）需要带对应 ACL 的 AGC 调试 profile，自动签名下安装会报 `9568289`。做成 opt-in（如 `install --acl-profile <build-profile>` 另出一个带权限的副本），**别默认申请**，否则没有该 ACL 的设备装不上。ACL 只解决读写与执行，不改变"沙箱内子进程随 app 退出被杀"，所以不能替代宿主常驻进程。
4. **HAP 内嵌二进制**用 `.bin` 扩展名：无扩展名或 `.so` 会走 hvigor 原生库流水线，破坏预签好的 `.codesign`，安装报 `9568393`，换签名器没用。

### 二、formula 骨架

1. **预编译 Electron 包当 `resource`**（托管在 tap 的 release asset 上），在 `def patch` 里解压到 buildpath 再 `super`；补丁多时按目录循环声明（见第六条）。
2. **专用 CI 镜像承载工具链**：HarmonyOS 命令行工具链不可公开再分发，所以用**专用 CI 镜像**固化，formula 的 `install` 里先 `odie` 守卫镜像是否就绪；用仓库变量 `OHOS_CI_IMAGE_OVERRIDES` 按 formula 指定镜像并 pin 到 manifest digest；私有镜像要 CI 能拉，必须配 `read:packages` 权限的 PAT 作为仓库 secret（`GITHUB_TOKEN` 拉不了用户私有包）。
3. **brew superenv 会改环境，按需显式设回**：`LD_LIBRARY_PATH`（打包工具要 SDK 的 clang 运行时）、`DEVECO_SDK_HOME`/`HOS_SDK_HOME`；`ENV.delete("NODE_OPTIONS")`；容器继承的 `RLIMIT_NOFILE` 过大会让 musl 的 FD 表映射失败，对构建进程只降不升。hvigor 的 `llvm-strip` 找不到只是非致命警告。
4. **依赖**：`hap-installer`、`ohos-sdk-toolchains`（提供 `hdc`）、`zip`（运行时依赖——安装时往 HAP 里注入配置要用，CI 镜像里没有）。Electron 应用的 node 依赖在 OHOS 上有缺平台二进制、`.node` 未签名等问题，走 `npm-porting` skill。
5. **应用名和 ability label 要改所有 `resources/*/element/string.json`**：模板的 `zh_CN`/`en_US` 会覆盖 base，只改 base 时启动器仍显示 "Electron"。本地验证：`unzip -p <hap> resources.index | strings | grep -c '^Electron$'` 应为 0。
6. **大补丁按文件拆**：`Patches/<formula>/ohos/<路径里 / 换成 _>.patch`，一个补丁一个文件，头部一行 `OHOS: …`，formula 用 `Dir[]` 目录循环声明。陷阱：`Dir[]` 不匹配点开头的文件（`.npmrc` 要命名成 `dot_npmrc.patch`）；CI 的 `remove-unused-patches` 按 glob 的静态目录前缀保留文件。验证：对干净上游检出用真 `patch` 逐个应用，与源分支的树哈希逐字节比对。

### 三、长期驻留进程与启动环境

1. **驻留进程引用稳定路径**：bridge/daemon 要调用的 CLI 必须是 `opt_libexec`/`opt_bin`，不能是 Cellar 版本目录——`brew upgrade` 会删掉旧版本目录，旧进程就指向不存在的路径。bridge 的 `/health` 要在 CLI 路径失效时报不健康，启动器据此替换旧进程。
2. **启动环境显式设置，别靠继承或某个脚本碰巧设置**：OHOS 上 `/tmp` 的 `flock` 会报 `EACCES`，凡是在 `/tmp` 下锁临时目录的 daemon，都要由 wrapper 设置临时目录基址变量，写成 `${VAR:-默认值}` 保留用户已设的值。
3. **`write_env_script` 的目标必须是安装后路径**（`libexec`/`pkgshare`），指 `buildpath` 会在 test 阶段报 "inaccessible or not found"。
4. **建议用户写进 shell 启动文件的命令，用绝对路径**：很多配置里启动文件先于 Homebrew 的 `bin` 进 PATH 执行，裸命令找不到且**静默失败**；caveats 里写绝对路径并说明原因。

### 四、formula 测试能做什么

`brew test` 不能启动图形界面，但能把交付链路断言住：
- fake `hap-installer`（以及签名器）录下参数，注入后用 `unzip` 断言配置文件、`module.json` 的权限集（默认几项、ACL 版几项）。
- 断言 wrapper 内容：稳定 opt 路径、环境变量；更实的做法是把 wrapper 最后的 `exec` 换成 `env` 实跑，覆盖"未设置取默认、已设置用用户值"两条路径。
- 驻留进程：起 bridge 验证未鉴权 401、白名单、路径穿越被拒、陈旧进程能被替换。
- 先写测试，再做**变异检查**（故意破坏实现，看对应断言变红）。断言字符串避开 heredoc 折行处。

### 五、真机验收（不可省，容器和 `brew test` 都不能替代）

1. **装机状态**：`bm dump -n <bundle>` 看 `reqPermissions` 与 `reqPermissionStates`（`0` 为已授予）；`ps` 看 app 的 uid 是否为应用专属。
2. **"在线"不等于"可用"**：健康检查、界面显示在线之外，必须**派一个真实的最小任务走完并确认回写**（临时目录 `flock` 问题就是这样才暴露的）。验完把验收数据清掉。
3. **没有 CDP 时从沙箱内部验证**：做一个探针副本（用同一份签名配置，只替换入口为探针），结果经回环 HTTP 回传——文件回传在读写被拒时拿不到结果。**必须带对照组**（默认签名跑同一探针），否则分不清"被拒"和"没跑起来"。后台监听器要在顶层启动，管道子 shell 里的 `wait` 不生效。
4. **界面验证**：`uitest dumpLayout` 读无障碍树，`snapshot_display` 截图。每次操作前先 `aa start` 拉前台；窗口是浮动的、坐标会变，页面刚重建后第一次点击常被吞；屏幕会息屏或锁屏，那时无法验证，等用户唤醒，**不要尝试解锁**。
5. **验升级**：`brew upgrade` 后旧的驻留进程是否还能用、启动器能否替换陈旧进程、界面是否不再停在重试页。
6. 验收记录里的截图、`bm dump` 输出（含签名证书指纹）、账户和会话 ID 属内部信息，**入库或公开前先过滤**。
