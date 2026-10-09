## 提交纪律（官方 core）

来自 `self-check-pr.md`，agent 最容易踩的几条：

1. **建 PR 交人**：agent 只到「描述落文件、交用户审阅」为止，PR 由用户在 AtomGit 手工创建（平台会带 PR 模板）。禁用 `gh`/v5 API/任何自动化工具建 PR——新规明令禁止，且"PR 由 AI 提交"会被维护者判低质量直接忽略。`brew style` + `brew audit` 通过后再交。
2. **作者与标题**：commit 作者必须是用户本人（邮箱须绑定 AtomGit），禁止写成 Bot/AI；PR 标题与 commit message 一字不差，不自创格式。禁在非自有仓留任何 AI 痕迹。
3. **数量**：一人同时最多 4 个 PR，5 个及以上按刷屏处理、拉黑。
4. **冗余修改黑名单**（维护者必揪）：声明了 `depends_on` 还手写 `-I#{formula_opt_include(...)}`/`-L#{formula_opt_lib(...)}`（superenv 自动注入）；`ENV["AR"] = "llvm-ar"`、`ENV.append_path "PATH", …`（同为 superenv 默认）；`depends_on "make"/"perl" => :build`（隐式依赖，从不显式声明）；上游未启用、也非 OHOS 必需的构建参数；构建期鸿蒙内核（`uname`=HarmonyOS）适配项（官方 core 从不在鸿蒙内核上构建）。
5. **来源、bottle 与补丁**：上游 formula 自带的仓内补丁不要复制进下游，改用远程补丁引用；默认禁引入 homebrew-core 以外的开源代码（版权，违者永久拉黑），仅自研（含 AI）与 0BSD/MIT-0 例外。搬运上游 formula 时必须保留当前上游对应 formula 的完整 `bottle do` 块，不能因 OHOS 没有 bottle 而整块删掉；块内平台、SHA256 和区块位置均按当前上游原样保留，不自行改写或移位；检查 diff 时确认未因移动造成删除再新增的噪声。已有 bottle 块同样禁止随意改动。
6. **依赖注释要对准依赖项**：条件依赖的行尾注释应直接、准确说明为何省略该依赖本身；不要只写它提供的间接库/能力，造成注释对象与 `depends_on` 不一致。若真正原因是某个间接依赖不可用，应明确写出因果关系，而非把它说成当前公式正在声明的依赖不可用。
7. **用词**：注释/commit 默认不写 "HarmonyOS"，用 OpenHarmony/OHOS；只有鸿蒙内核这类发行版特有问题、或特指华为鸿蒙 PC 时才用。应用沙箱、hmdfs 都不算发行版特有。

