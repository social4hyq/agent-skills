# agent-skills

OpenHarmony / 鸿蒙 PC 移植相关的 AI agent skills 合集。

## 包含的 skills

- **harmonybrew-formula-porting** — 把命令行工具做成 Harmonybrew tap formula 并打包发布
- **npm-porting** — npm 包的 OpenHarmony 移植路径判定与 `@ohos-npm-ports` port 制作
- **ohos-frontend-upgrade** — 已有前端工程升级适配到 OpenHarmony 本机 install/build/run（vite 8 系配方）

## 安装

需要 Node.js 18+。

```bash
npx skills add social4hyq/agent-skills
```

定向安装单个 skill：

```bash
npx skills add social4hyq/agent-skills --skill harmonybrew-formula-porting -g
npx skills add social4hyq/agent-skills --skill npm-porting -g
npx skills add social4hyq/agent-skills --skill ohos-frontend-upgrade -g
```
