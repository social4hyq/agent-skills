# HarmonyPC 远程 Docker 环境（openharmony 容器）

> 随 skill 分发的参考，独立维护。**本环境可选**——仅本地重型构建/bottle 打包需要；不搭容器可直接走 tap 仓 CI（见 SKILL.md「打包与发布」）。覆盖：从零搭建、容器重建后一次性配置、日常命令、故障排查。

# HarmonyPC 远程 Docker 环境搭建指南

在鸿蒙 PC 上通过 `docker` CLI 操控远程 Linux 服务器上的容器。利用 Docker C/S 架构的 SSH 传输，本地敲 docker 命令如同操作本机，实际容器跑在远程服务器上。

## 架构

```
鸿蒙 PC (客户端)                          Linux 服务器 (服务端)
┌─────────────────────┐                 ┌──────────────────────────┐
│  docker CLI         │   ssh 隧道      │  dockerd (systemd 管理)   │
│  (ohos-builder ctx) │ ──────────────> │  /var/run/docker.sock    │
│  brew install docker│   ssh://        │  ↓                       │
└─────────────────────┘                 │  openharmony 容器         │
                                        │  (OHOS userspace)        │
                                        └──────────────────────────┘
```

**2026-08 更新**：服务端引擎重装后原生带 systemd，直接用标准 dockerd + `--restart=always`（本文档 Step 3–6 主路径）。若服务端没有 systemd 或 dockerd 起不来，需另行设计 podman + VFS + sshrc 恢复脚本的变通方案（超出本文范围）。

**为什么曾经用 podman？** 部分服务器环境（如 openEuler in OzoneC 容器、无 systemd 的 `hsl_init`）的 devices cgroup 无法挂载，dockerd 启动即崩，只能用 podman（支持禁用 cgroups 运行）+ `podman system service` 模拟 Docker API。2026-08 重装后的引擎带了完整 systemd 和 cgroup v2 unified hierarchy，原生 dockerd 可以正常跑——但**必须用较新版本**，见 Step 3 的关键坑。

---

## 前置条件

| 角色 | 要求 |
|------|------|
| 客户端 | 鸿蒙 PC，已安装 [Harmonybrew](https://atomgit.com/Harmonybrew) |
| 服务端 | Linux 服务器（aarch64/x86_64），SSH 端口对客户端可达 |
| 网络 | 客户端 → 服务端 SSH 可达 |

以下用 `user@172.16.105.2` 作为示例，请替换为你的实际地址。

---

## Step 1: 配置 SSH 免密登录

**客户端操作**：

```bash
# 生成密钥对（已有时跳过）
ssh-keygen -t ed25519 -N "" -f ~/.ssh/id_ed25519

# 将公钥追加到服务端
ssh-copy-id user@172.16.105.2

# 手动登录一次，将服务端指纹写入 known_hosts（必须！否则 docker SSH 连接会被安全提示拦截）
ssh user@172.16.105.2 'echo OK'
```

验证：`ssh user@172.16.105.2 'echo OK'` 无需密码即输出 OK。

> **服务端整机重装后**：旧 host key、旧 authorized_keys 全部作废，免密登录会失效，必须用密码重新走一遍上面的流程。本机没有 `ssh-copy-id` 二进制（`brew install openssh` 不带这个脚本），也没有 `sshpass`，需要先 `brew install sshpass`，再手动拼等价命令：
> ```bash
> # 1. known_hosts 在 hmdfs 上，ssh-keygen -R 的 rename+link 操作会报 "Operation not permitted"
> #    改为手动编辑 known_hosts 删除旧条目（grep -n 172.16.105.2 定位行号后用 Edit 工具删）
> # 2. 用 sshpass 免交互跑一次密码登录，把公钥追加到远端 authorized_keys
> export SSHPASS='<password>'
> sshpass -e ssh -o StrictHostKeyChecking=accept-new user@172.16.105.2 'mkdir -p ~/.ssh && chmod 700 ~/.ssh'
> cat ~/.ssh/id_ed25519.pub | sshpass -e ssh user@172.16.105.2 'cat >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
> unset SSHPASS
> ```
> 密码只在环境变量里传递一次，不落盘、不留 shell history（`export` 在子 shell 里执行完立即 `unset`）。

---

## Step 2: 客户端安装 Docker CLI

```bash
brew install docker
docker --version  # 确认安装成功
```

> 只安装 CLI 客户端，不需要 dockerd。容器引擎在服务端运行。

---

## Step 3: 服务端安装 Docker Engine

```bash
ssh user@172.16.105.2
```

### 关键坑：发行版自带的 docker-engine 包可能太旧，不支持纯 cgroup v2

openEuler 24.03 SP3 的 `dnf install docker-engine` 装的是 **18.09**（2018 年的版本）。如果服务端内核只挂载了 cgroup v2 unified hierarchy（`mount | grep cgroup` 只看到一行 `cgroup2 on /sys/fs/cgroup`，没有独立的 `/sys/fs/cgroup/devices` 等 v1 子目录），18.09 启动即报：

```
Error starting daemon: Devices cgroup isn't mounted
```

根因：Docker 对纯 cgroup v2（用 eBPF 做设备过滤，不依赖 legacy `devices` 子系统）的支持是 20.10（2020 年底）才加的，openEuler 仓库里的 docker-engine 停在此之前。**判断方法**：

```bash
mount | grep cgroup                    # 只有一行 cgroup2 → 纯 v2 unified
cat /proc/cgroups | grep devices        # enabled=1 说明内核支持，只是没有旧版 dockerd 能用的挂载点
```

如果是这种情况，卸载发行版包，改装官方静态二进制（不依赖包管理器的版本滞后）：

```bash
# 卸载发行版自带的旧版本
sudo systemctl stop docker.service 2>/dev/null
sudo systemctl disable docker.service 2>/dev/null
sudo dnf remove -y docker-engine   # openEuler/CentOS/RHEL 用 dnf；Ubuntu/Debian 用 apt remove docker.io

# 官方静态二进制（下载点在国外 CDN，服务端直连大概率卡在 TLS 握手；
# 改成本机 curl 下载后 scp 传过去，见下面「网络坑」）
curl -fLO https://download.docker.com/linux/static/stable/aarch64/docker-<version>.tgz
tar xzf docker-<version>.tgz
sudo cp docker/* /usr/bin/
```

`docker-<version>.tgz` 是完整 bundle（dockerd + containerd + runc + docker-init + docker-proxy + docker CLI），解开直接铺到 `/usr/bin` 即可，不需要单独装 containerd。

手写 systemd unit（发行版包移除时会带走 `/usr/lib/systemd/system/docker.service`）：

```bash
sudo tee /usr/lib/systemd/system/docker.service > /dev/null << 'EOF'
[Unit]
Description=Docker Application Container Engine
Documentation=https://docs.docker.com
After=network-online.target
Wants=network-online.target

[Service]
Type=notify
ExecStart=/usr/bin/dockerd
ExecReload=/bin/kill -s HUP $MAINPID
TimeoutStartSec=0
RestartSec=2
Restart=always
LimitNOFILE=infinity
LimitNPROC=infinity
LimitCORE=infinity
TasksMax=infinity
Delegate=yes
KillMode=process
OOMScoreAdjust=-500

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now docker.service
sudo systemctl status docker.service --no-pager   # 应为 active (running)，日志里不再有 cgroup 报错
```

### 网络坑：服务端直连 download.docker.com 可能卡在 TLS 握手

服务端对 `get.docker.com`（Cloudflare）访问正常，但对 `download.docker.com`（AWS CloudFront）TLS 握手常卡死（`curl -v` 停在 `TLSv1.3 (IN), TLS handshake, Server hello` 不再往下走）。本机（鸿蒙 PC）访问同一 URL 完全正常。判断+绕过：

```bash
# 服务端探测（观察是否卡在 TLS 握手）
ssh user@172.16.105.2 'curl -v --max-time 8 https://download.docker.com/ 2>&1 | tail -20'

# 卡住就改本机下载 + scp 传入（同一模式适用于任何服务端连不上的国外资源）
curl -fLO https://download.docker.com/linux/static/stable/aarch64/docker-<version>.tgz
scp docker-<version>.tgz user@172.16.105.2:/home/user/docker-<version>.tgz   # 见下面 /tmp 坑，别传 /tmp
ssh user@172.16.105.2 'sha256sum /home/user/docker-<version>.tgz'            # 和本机 sha256sum 对账
```

### 权限组

```bash
sudo groupadd docker 2>/dev/null || true
sudo usermod -aG docker $USER
# 退出重连一次 ssh 让组生效，或用 newgrp docker
docker ps   # 免 sudo 验证
```

---

## Step 4: 下载镜像并创建容器

```bash
docker pull swr.cn-north-4.myhuaweicloud.com/harmonybrew/ci-runner:latest

docker run -d --name openharmony \
  --init --restart=always --stop-timeout=0 \
  --workdir /root \
  -v /home/user/openharmony:/root \
  swr.cn-north-4.myhuaweicloud.com/harmonybrew/ci-runner:latest sleep infinity

docker ps
docker exec openharmony echo "container OK"
```

**容器参数说明**：

| 参数 | 作用 |
|------|------|
| `--name openharmony` | 容器名 |
| `--init` | catatonit/docker-init 做 PID 1，回收僵尸进程 |
| `--restart=always` | systemd 管 dockerd，dockerd 管容器；服务端重启后自动拉起，取代了旧的 podman DB-reset 恢复脚本 |
| `--stop-timeout=0` | 停止时不等待 |
| `-v /home/user/openharmony:/root` | 持久化卷（容器重建后数据保留） |
| `sleep infinity` | 保持容器常驻 |

**存储驱动仍可能是 VFS，不是性能提升的来源**：如果服务端根文件系统本身是 `overlay`（`df -h /` 显示 `Filesystem` 一列是 `overlay`），Docker 的 overlay2 存储驱动没法叠在另一层 overlay 上（内核不支持 overlay-on-overlay），`docker info` 里 `Storage Driver` 会自动落回 `vfs`。这不是 bug，也不需要修——升级到原生 dockerd 换来的是 systemd 生命周期管理和标准恢复语义，不是镜像操作速度；镜像层操作耗时和旧的 podman+VFS 方案量级相近。

---

## Step 5: 客户端配置 Docker Context

```bash
docker context create ohos-builder --docker "host=ssh://user@172.16.105.2"
docker context use ohos-builder

# 验证（应显示服务端的容器）
docker ps
docker exec openharmony echo "remote container OK"
```

之后所有 `docker` 命令自动走远程，无需额外参数。

---

## 容器重建后的一次性配置

容器（`openharmony`）被重建后（镜像更新、数据卷从备份恢复后新建容器等），需要重跑这几项——都是 writable layer 里的东西，重建就丢：

### 1. loader / 路径垫片

```bash
docker exec openharmony bash -lc '
  mkdir -p /system/bin /system/lib /data/local/tmp
  ln -sf /bin/sh /system/bin/sh
  ln -sf /lib/ld-musl-aarch64.so.1 /system/lib/ld-musl-aarch64.so.1'
```

不做的话，设备侧编译的 OHOS ELF（bun 等）execve 直接 exit 127（`cannot execute: required file not found`，INTERP 指向设备路径 `/system/lib/ld-musl-aarch64.so.1`，容器里的 loader 在 `/lib/` 下）。

### 2. brew 工具链重装

容器里的 brew 前缀（`/storage/Users/currentUser/.harmonybrew`）属于 writable layer，不在持久卷 `/root` 里，任何重建都会丢。重建前留一份包清单（`brew list --versions`、`brew tap`），重建后按清单 `brew install`。tap 除了镜像自带的 `harmonybrew/core`，还要手动 `brew tap social4hyq/core`（bun/ohos-* formula 的权威源）。

`ca-certificates` formula 必须最先装（`brew tap` 走 https git clone，用的是 brew 自己 `$HOMEBREW_PREFIX/etc/ca-certificates/cert.pem`，这个文件由 ca-certificates formula 提供，没装就是先有鸡还是先有蛋的死锁——容器系统级 curl 能连通不代表 brew 能 tap）。全新安装/重装 brew 时 install.sh 收尾的 `brew update --force` 就会卡在这个死锁上（git clone 报 `error adding trust anchors from file: .../cert.pem`），破法：先 `mkdir -p $HOMEBREW_PREFIX/etc/ca-certificates && cp /etc/ssl/certs/cacert.pem $HOMEBREW_PREFIX/etc/ca-certificates/cert.pem`（容器系统 CA 包，curl 实测验证通过）临时顶位，再 `brew update --force` + `brew install ca-certificates`——formula 的 post_install 会先 `rm_f` 再重建该文件，临时副本不冲突。

只要 tap 里已有目标版本的 bottle（`brew info <formula>` 能看到 bottled 就是），`brew install` 走预编译二进制，几十个包几分钟装完，不需要触发源码构建。`bun` 从源码构建（`brew install --build-bottle social4hyq/core/bun`）需要预热 `BUN_INSTALL_CACHE_DIR`/`BUN_BUILD_PREFETCH_DIR` 两个缓存那一整套复杂流程，只在**产出新 bottle**（改了补丁、升级版本）时才需要——单纯把已发布的 bottle 装到新容器上，走普通 `brew install bun` 就够。

### 3. cmake readdir-errno 垫片（如果还需要）

openharmony 容器（非 HM 内核的 openEuler 服务器）里，cmake 的 `file(GLOB)` 对 >64 条目的目录曾经静默返回空列表（OHOS musl 分配器在非 HM 内核上污染 errno，被 cmake KWSys 误判为遍历失败）。**每次容器重建/引擎重装后都要重新验证**——底层内核换了就可能不复现，别不测就假设还在：

```bash
docker exec openharmony bash -lc '
  mkdir -p /tmp/globtest && cd /tmp/globtest && for i in $(seq 1 900); do touch f$i; done
  echo "message(GLOB_COUNT=\${N})" # 占位，实际用下面的 CMakeLists.txt
'
cat > /tmp/CMakeLists.txt << 'EOF'
cmake_minimum_required(VERSION 3.10)
project(globtest)
file(GLOB FILES "f*")
list(LENGTH FILES N)
message("GLOB_COUNT=${N}")
EOF
docker cp /tmp/CMakeLists.txt openharmony:/tmp/globtest/
docker exec openharmony bash -lc 'cd /tmp/globtest && cmake . 2>&1 | grep GLOB_COUNT'
# 返回 GLOB_COUNT=900 → 不需要垫片；返回 0 或空 → 部署下面的垫片
```

若复现，垫片源码+产物在持久卷 `/root/shims/readdir-errno-fix.{c,so}`（随数据备份一起保留，不用重新编译），只需重新挂 wrapper：

```bash
docker exec openharmony bash -lc '
  CELLAR="$(brew --prefix cmake)/bin"
  cp "$CELLAR/cmake" "$CELLAR/cmake.real"
  cat > "$CELLAR/cmake" << "EOF"
#!/bin/sh
export LD_PRELOAD=/root/shims/readdir-errno-fix.so
exec "$(dirname "$0")/cmake.real" "$@"
EOF
  chmod +x "$CELLAR/cmake"'
```

musl 不支持 `/etc/ld.so.preload`，只认 `LD_PRELOAD` 环境变量；brew superenv 可能过滤 `LD_*`，所以必须走 wrapper 脚本而不是外层 `export`。

容器构建结果与本机（真机）行为的对比验证：容器只是参照系，不是部署证明——最终以真机结果为准。

---

## 日常使用

服务器重启后 systemd 会自动拉起 dockerd，dockerd 因 `--restart=always` 自动拉起容器，**无需手动操作**。

```bash
# 查看容器
docker ps

# 进入容器
docker exec -it openharmony bash

# 执行命令
docker exec openharmony make -C /root/my-project

# 传文件到容器
docker cp ./local-file openharmony:/root/

# 从容器取文件
docker cp openharmony:/root/output.bin ./

# 查看镜像
docker images

# 重启容器
docker restart openharmony
```

### 避坑指南

| 问题 | 说明 |
|------|------|
| **`-v` 挂载的是远程路径** | `docker run -v /data:/app` 中的 `/data` 是服务端路径，不是本地路径 |
| **`-p` 端口映射在远程** | `-p 8080:80` 的 8080 开在服务端，本地访问需 SSH 隧道：`ssh -N -L 9090:localhost:8080 user@172.16.105.2` |
| **文件传输用 `docker cp`** | 不要用 `-v` 挂载本地目录，用 `docker cp ./file openharmony:/path/` |
| **服务端 `/tmp` 是 tmpfs，容量小** | 见过 3.9G 上限（`findmnt /tmp` 能看到 `tmpfs` 类型），传大文件（几个 G 以上的备份 tar、docker 静态二进制）落这里会写到一半报 "Failure"。改传到 `/home/<user>/` 之类落在根分区（`overlay`/`ext4` 等真实磁盘）的路径 |
| **大文件 tar 备份/恢复时的 GNU tar 警告不一定是数据丢失** | 服务端根文件系统若是 `overlay`，`tar` 解压大量文件（尤其 cargo/git 里那种硬链接密集的 checkout 树）时可能报 `Directory renamed before its status could be extracted`（GNU tar 对 overlayfs 上不稳定的 inode 号做硬链接识别时的已知局限）。这类警告出现在 tar 的"延迟设置目录权限"收尾阶段，此时文件内容通常已经写完——用 `sudo du -sh <dir>` 核对恢复后的体积是否和备份前一致（**必须以 root 权限查看**，受影响目录的最终 chmod 步骤没跑完，会停在创建时的临时权限如 `0700`，非 root 用户直接 `du`/`ls` 会看到 permission denied 而误判为空/丢失）；真正的数据丢失表现为体积明显小于备份前，而不是"权限像是空目录" |

---

## 故障排查

### docker ps 报 "Cannot connect to the Docker daemon"

```bash
ssh user@172.16.105.2 'systemctl status docker.service --no-pager'
```

若 `inactive`/`failed`：`sudo systemctl start docker.service`，仍失败看 `journalctl -xeu docker.service`——最常见原因是 Step 3 提到的 cgroup v2 不兼容（发行版自带 docker-engine 版本太旧）。

### docker exec 报容器未运行

```bash
docker start openharmony   # --restart=always 通常会自愈，手动兜底
docker logs openharmony --tail 50
```

### sshpass / ssh-copy-id 找不到命令

本机 brew 没有独立的 `ssh-copy-id`（openssh formula 不带这个脚本）。`brew install sshpass` 后用 Step 1 底部的等价命令手动拼。

### known_hosts 编辑报 "Operation not permitted"

`~/.ssh/known_hosts` 在 hmdfs（`/storage/Users/...`）上，`ssh-keygen -R` 内部用 `link()` 做原子替换，hmdfs 不支持这个 syscall。改用文本编辑工具直接删除对应行（`grep -n <ip> known_hosts` 定位，删掉整行），普通文件写入在 hmdfs 上没问题，只有 `link`/`rename` 类操作会踩雷。

### 容器里 bun-bootstrap 跑 `bun install` 段错误（RLIMIT_NOFILE 过大）

症状：`brew install --build-from-source social4hyq/core/bun` 在最初的 `bun install` 步骤崩溃，`panic: Segmentation fault at address 0xFFFFFFFFFFFFFFFF`，约 160ms 即挂；同一二进制同一源码树在真机跑完全正常。

根因：容器默认 `RLIMIT_NOFILE=2^30`（`prlimit64` 实测 `rlim_cur=1073741816`），bun-bootstrap（1.4.0-5467a689）的 install 按 rlimit 给 fd 表分配内存，乘法溢出 32 位后 `mmap(NULL, 0, ...)` 返回 -1，空指针解引用崩溃（qemu -strace 实证）。真机 rlim_cur=32768 所以不触发。

修法：构建前 `ulimit -n 32768`（会继承到所有构建子进程）。已写进容器 `/root/.bashrc`；注意 `docker exec ... bash -lc` 是 login shell，读 `.bash_profile`/`.profile` 而非 `.bashrc`，非交互构建命令里要显式带 `ulimit -n 32768;`。

历史备注：2026-08-02 的 r46 容器构建能成功、之后同代码同二进制全挂，曾误判为"容器环境漂移"，实际就是引擎/容器重建后默认 nofile 变了。

