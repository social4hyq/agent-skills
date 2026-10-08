## 场景一：录入/适配一个 formula

构建命令：`brew install -y -s -v --include-test {formula}`
测试命令：`brew test {formula}`
改动范围：`Formula/{subdir}/{formula}.rb` + `Patches/{formula}/` + `Aliases/`，其余文件一律不动，每轮 `git status --porcelain` 查越界。

注意事项：

1. 上游 homebrew-core 有就搬运过来改适配；没有先录进上游再搬回来，直接往下游手写被拒概率高得多；闭源/预编译二进制/源码取自第三方 fork 的不合准入，落自有 tap。
2. 禁止在鸿蒙 PC 本机构建官方 core 的 formula——包管理器已做限制，绕过做出来的产物合不进去。本机只服务自有 tap 试错。
3. 长构建用 `docker exec -d` 分离、日志落容器内按内容轮询；附着执行会被 ssh 断连带崩、假完成、日志截断。
4. 报错对照 `reference/ohos-adaptation.md` 定位。三轮修不好说明根因诊断错了，停下重新诊断，不要继续补。
5. 要打补丁先抄现成的：`ls $(brew --repo harmonybrew/core)/Patches` 近百份已合入范例，挑同生态的（gcc、cmake、perl、coreutils、git、go）连写法带风格照搬；同一个 gnulib/musl 报错直接复用已有 patch。
6. 补丁机器生成，禁手改 `@@` 行号；toybox `patch` 遇错误 header 会静默 `exit 0`，验证靠 grep marker 不靠退出码。
7. 每行改动必须挂实测证据：少了它一定构建/测试失败，或一定让 OHOS 设备上功能出问题。两条都答不上就删。无证据的守卫、双路径开关、顺手修、拆多 PR 全是负债——先例、审阅意见、用户批示执行前都要过这条筛。（跟随上游多平台 formula 时，OHOS 专有部分用 `if OS.ohos?` 圈起来不在此列，见场景三。）
8. 提 PR 前 `brew style` + `brew audit` 全绿。门禁不强校验，但维护者手工查，不过就拒收。本机 audit 要把临时 tap 的目录命名成 `homebrew-core`（如 `Taps/vpwork/homebrew-core` 软链到 worktree，用 `brew audit vpwork/core/{formula}`）：仓库名不是 `homebrew-core` 时，只在 homebrew-core 里启用的检查（如 caveats 里禁 if/else/unless）会被静默跳过，本机"无输出"、CI 却红。caveats 写静态文本，不写动态逻辑。**这个临时 tap 用完立刻摘掉**（`rm` 掉 symlink，worktree 本体留在 `../Software/` 别删）：Taps 下每个 `<owner>/<repo>` 目录都是一个独立 tap、会全部并入 formula 命名空间，再挂一个带同名 formula 的副本（哪怕物理副本各自独立）就会让 `brew upgrade` / `brew install <裸名>` 在解析阶段硬失败：`Error: Formulae found in multiple taps`。别拿 `brew tap` 当自检——它**不列** symlink 型 staging tap；用 `ls ~/.harmonybrew/Homebrew/Library/Taps/`（除 `harmonybrew/homebrew-core`、`social4hyq/homebrew-core` 外都该摘）看顶层、`brew upgrade --dry-run` 验收。
9. 非自有仓禁一切 AI 痕迹。PR 模板的「AI 人工审核」框与验证截图是用户本人的事实陈述，agent 一律留空，交付止于可核验的 CI 链接。

