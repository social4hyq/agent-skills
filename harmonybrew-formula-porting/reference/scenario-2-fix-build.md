## 场景二：bump 后构建/测试挂

占位符替换后整段下发，交付骨架与 status.json 门控不可裁剪：

```text
你现在在一个鸿蒙环境上，里面有个鸿蒙版的 Homebrew。我将 {formula} 这个 formula 升级后，它无法构建通过/测试通过，请帮我排查原因并修复。

构建命令：brew install -y -s -v {formula}
测试命令：brew test {formula}

修复完成后，把以下材料放到 {report_dir} 目录下：
1. 定位报告 report.md
2. 改过的 formula 文件
3. 所有补丁文件，包括原有的和新增的（如果存在）
4. 状态文件 status.json

最终输出的目录骨架应该是这样：
{report_dir}
  /report.md
  /status.json
  /Formula/{subdir}/{formula}
  /Patches/{formula}

status.json 的格式：
成功：{"status": "success"}
失败：{"status": "failure", "reason": "<一句话说明失败原因>"}
只有当你确认构建命令和测试命令都通过后，才允许写 success；否则必须写 failure 并说明原因。

注意事项：
1. 升级后对比上游版本formula，看看上游版本是不是引入了什么新改动需要同步进来：https://github.com/Homebrew/homebrew-core/raw/refs/heads/main/Formula/{subdir}/{formula}.rb。
2. 升级过程不要抛弃掉原有的鸿蒙适配补丁或者鸿蒙适配的构建参数（部分软件包可能有，不是每个软件包都一定有）。
3. 如果需要制作补丁或新增补丁，请参考 gcc、cmake、perl 这类 formula，看它们是怎么引入补丁文件的。
4. 这个报告用来展示在 PR 评论区，因此不宜过长。
5. report.md 会被嵌套在评论已有的一级标题之下，因此不要写总标题，也不要使用一级标题（#），正文直接从二级标题（##）开始分节，例如按 `## 现象`、`## 根因`、`## 修复`、`## 验证` 组织。
```

bump 窗口是免费复核期：继承来的守卫、caveat、shim 说不出当下失败证据的，这轮顺手删。

