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
4. **界面验证**：`uitest dumpLayout` 读无障碍树，`snapshot_display` 截图。用 `aa start` 拉**一次**前台，之后**直接连点，不要在每次点击前重复 `aa start`**：拉前台后的第一次点击常被吞，重复拉前台会让每次点击都被吞。点完看界面或进程有没有变化（如 daemon 的 pid），没变就再点，不要盲目判定“功能坏了”。窗口是浮动的、坐标会变，应用重新打开后常是小窗、侧栏被收起，要先最大化或展开再从无障碍树里取入口和按钮坐标；屏幕会息屏或锁屏，那时无法验证，等用户唤醒，**不要尝试解锁**。
5. **验升级**：`brew upgrade` 后旧的驻留进程是否还能用、启动器能否替换陈旧进程、界面是否不再停在重试页。
6. 验收记录里的截图、`bm dump` 输出（含签名证书指纹）、账户和会话 ID 属内部信息，**入库或公开前先过滤**。

### 六、拆成 `<app>` 和 `<app>-desktop` 两个 formula

同一个应用既有 CLI/daemon 又有桌面壳时（范例：`multica` 加 `multica-desktop`；官方 core 的 `opencode` 加 tap 里的 `opencode-desktop`），默认拆成两个 formula，**不要把 HAP 打进 CLI 的 bottle**。

1. **为什么拆**：HAP 占 bottle 的绝大部分（数量级差一个量级：HAP 两百多 MB，CLI 十几 MB），只要 CLI 的人也要下载它，还要连带装 `hap-installer`、SDK 工具、`zip` 三个只有桌面才用的依赖；桌面侧改动远比 CLI 频繁（权限、bridge、启动环境、文字），每次 revision 都让所有人重下一遍；修改上游已有文件的补丁全在桌面代码、锁文件和壳资源里，CLI 一个都不需要，拆开后 CLI 是普通 formula，可以进自动升级。
2. **边界**：`<app>` 是上游 CLI/daemon 原样构建，零补丁，只依赖构建工具，不放 HAP、bridge、安装脚本；wrapper 只设启动环境（如临时目录基址），直接 `exec` 到 CLI，不再经过转发脚本；**CLI 的安装位置（如 `libexec/<cli>`）要保持不变**，桌面按稳定 opt 路径引用它。`<app>-desktop` 是 `depends_on "<app>"` 加上本文一到五节的全部内容（补丁、resource、构建镜像守卫、bridge、安装与启动脚本），命令用 `<app>-desktop install|start|stop|status`。
3. **桌面 wrapper 也要设置 daemon 的启动环境**：daemon 是桌面经 bridge 拉起的，继承的是**桌面 wrapper** 的环境，不是 CLI wrapper 的。漏掉它，拆分后任务临时目录会回到 `/tmp`，`flock` 失败，而且 daemon 在线、界面正常，只有真实任务才暴露。
4. **版本一致只能提示，不能锁**：Homebrew 没法给依赖钉版本。桌面启动器在 `install` 和 `start` 时比较 CLI 版本与自身版本，不一致就往 stderr 警告并继续；读不出版本时不警告，`status` 不警告。先查应用本身有没有“桌面版本必须等于 CLI 版本”的硬检查，多数没有，那就不要在启动器里拒绝。
5. **顺序（一 PR 一 formula，依赖先行）**：① 新增 `<app>-desktop`，原 formula 不动（两者 `bin` 名不同，可以并存，共用 bridge 状态目录，过渡期只用其中一套命令），出 bottle 后真机验收；② 再瘦身原 formula（去掉 HAP、补丁、resource、桌面依赖，加 revision），出 bottle 后再验收一遍：升级前后运行中的 daemon 与 bridge 的 pid 不变，重启后仍由桌面拉起，真实任务能跑；③ 善后（下一条和第 7 条）。
6. **迁移副作用要主动收拾**：旧子命令消失，caveats 要说新命令在哪；**写进 shell 启动文件的旧启动行**若带 `|| true` 会静默失效，要同步改成新命令，并先复现旧行拉不起 bridge、改完再开新终端验证能拉起；已经在运行的 bridge 和 daemon 不受影响，因为它们引用的是稳定的 opt 路径。
7. **自动升级（自有 tap 的 autobump）**：CLI 回到普通 formula 后可以进自动升级并自动合并。桌面带补丁，**不能自动合并**：补丁是针对上一个版本写的，实测反向应用到相邻的上游版本没有失败，但有补丁靠偏移或 fuzz 才打上，而 `test do` 只看 HAP 内容、不看补丁的运行行为，所以绿灯不代表补丁对。让它自动开 PR、人工合并即可，但要注意三点：① 机器人开的 PR 其 `pr-validate` 会停在 `action_required`，要人手批准才跑 CI；② 自动合并按分支名的**前缀**匹配，`bump-<app>-desktop-<版本>` 会命中 `<app>` 的前缀，只“不加进名单”不够，要用单独的“人工合并”正则显式排除，并且放在名单检查之前；③ 同一个上游版本会同时开两个升级 PR，先合 `<app>`。
