# codex-handoff

> 让一个即将到达额度边界的长任务，带着已核实的状态继续，而不是让下一位 agent 从零猜起。

`codex-handoff` 是给 Codex 用的交接插件。它不替你继续开发，也不会自动创建或切换会话；它只在恰当的时候提醒、暂停后续消耗，并帮你把已完成的工作交给下一位 agent。

## 适合什么情况？

如果你的额度一直足够完成任务，**不需要安装它**。

它适合这样的情况：一个大任务还没做完，五小时额度快用尽了。直接把聊天记录、spec 或几个文件交给新的 agent，往往会让对方重新摸索、遗漏重点或擅自扩展工作；等到下一个额度窗口，也可能继续为同一批上下文付费。

`codex-handoff` 的目标是把“交接”变成一个有边界的动作：保留目标、证据、进度、决定和下一步，而不是把一整段聊天记录塞给下一个 agent。

<p align="center">
  <img src="assets/codex-handoff-00-origin-story.png" alt="额度充足时一个小黑完成大任务；额度有限时多个小黑先封装标准交接单，再由下一位继续" width="100%">
</p>

## 一次开发如何被保护？

下面是一段典型的长任务经历。

### 1. 任务正常推进

额度高于 15% 时，插件保持安静。你和 Codex 像平时一样工作，不会被提醒或打断。

### 2. 剩余 15% 到高于 6%：只提醒，不停工

插件只提醒一次：现在适合准备交接。你可以忽略它并继续工作；它不会暂停 agent、不会撤销任何改动，也不会自动生成 handoff。

### 3. 剩余 6% 或以下：保留成果，暂停等你选择

此时会出现两种情况：

- **你刚提交一条新请求**：这次请求会先被阻止，agent 不会开始新一轮推理或执行。插件请你二选一：运行 `$handoff-prepare` 保存交接单，或只回复 `继续开发`，让 agent 继续原本暂停的任务；不需要重新描述原任务。
- **agent 正在调用本地工具**：已完成的工具结果会被保留；不会撤销该工具已经做过的事，也不会丢掉它的输出。随后同一轮中下一次受支持的本地工具调用会被拒绝，agent 停下来把选择权交还给你。

<p align="center">
  <img src="assets/codex-handoff-03-quota-guard-v2.png" alt="小黑保留已完成的工具结果，在额度低时暂停后续调用" width="100%">
</p>

这不是“清空上下文”或“丢失工作”。它只是停止**后续**动作；已经得到的工具结果、已写入的文件和当前对话都还在。

<p align="center">
  <img src="assets/codex-handoff-04-protective-block.png" alt="额度达到保护阈值时，插件暂停后续操作并提示交接" width="100%">
</p>

### 4. 由你决定交接与继续

如果你想继续开发，直接回复 `继续开发`。Codex 会接着做原本暂停的事；插件不会在同一会话、同一额度窗口里反复拦你。继续消耗剩余额度的风险由你决定。

如果你想交接，就在**当前任务**运行 `$handoff-prepare`。它会在项目的 `.handoff/` 中写入一份不可变的 Markdown 交接单。最前面的三段只讲清楚：现在停在哪里、这项任务的目标和边界是什么、下一步建议做什么以及还需要你授权什么。后面的交付记录会区分“已实现 / 已验证 / 已验收 / 进行中 / 阻塞”，避免把测试通过误当成你已经验收。

然后在一个新任务里运行 `$handoff-continue`。新 agent 先看交接单最前面的三段（**L0**）和项目本来就该遵守的说明（如 `AGENTS.md`）。交接单引用的其他资料只是索引：当前任务确实需要某个事实时，再去读对应的 **L1/L2**，不必一上来把所有旧 spec、日志和代码都塞进新会话。它先向你报告自己理解的目标、证据、边界和缺口，停下来等你授权下一步。

<p align="center">
  <img src="assets/codex-handoff-05-progressive-checkpoint-v2.png" alt="小黑先展开交接单的断点、任务边界和下一步，L1/L2 资料留作按需查阅的索引" width="100%">
</p>

如果新 agent 真有疑问，首轮可以提出 **0 到 3 个具体问题**，不用为了凑数而提问。你可以直接回答，也可以在旧任务还有额度时请原 agent 写一份补遗。补遗不会覆盖原交接单，会放在 `.handoff/clarifications/` 并注明它回答的问题与证据；新 agent 不会自动选中它，只有你明确指定或同意后才会读取。

<p align="center">
  <img src="assets/codex-handoff-06-optional-clarification-v2.png" alt="新 agent 有疑问才提问，最多三个；是否让旧 agent 补充并读取补遗由用户决定" width="100%">
</p>

## 会带来什么影响？

你应该预期这些行为和限制：

- **不会自动切换会话**：不会帮你新建 agent、提交代码、推送仓库或开始下一步；所有继续动作都需要你决定。
- **低额度时可能被打断一次**：五小时或周额度剩余 6% 或以下时，插件会为当前会话和本次额度窗口做一次保护性阻断。你选择 `继续开发` 后，同一会话和窗口不会反复被阻断；目的只是留住交接机会，而不是取消已完成工作。
- **不会撤销已完成操作**：已经完成的工具结果、已经写入的文件和对话上下文仍然存在。它只会拒绝同一轮的后续受支持工具调用。
- **不是百分之百的总开关**：额度保护只是**尽力而为**。托管或特殊工具路径可能绕过本地保护；如果读取额度信息失败，插件会放行，而不是误伤正常工作。
- **自动压缩仍可发生**：自动压缩前会给出强提醒，但不会强行阻止压缩。需要交接时，请主动运行 `$handoff-prepare`。


## 三步开始使用

### 1. 安装

将公开仓库注册为 Codex marketplace，再安装插件；不需要 clone：

```bash
codex plugin marketplace add LLeung49/codex-handoff --ref main
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

确认 `codex-handoff@codex-handoff` 已安装并启用后，新开一个 **Codex 任务**，让它加载新的 hook 和 skill。

#### Windows 使用说明

从 v0.2.3 起，Windows 上的 hook 会通过 `cmd.exe` 调用 `python`，并使用
Windows 的 `%PLUGIN_ROOT%` 变量语法；macOS/Linux 仍调用 `python3`。因此
Windows 请先在终端确认 `python --version` 能运行，并确保它指向 Python 3；不要
只依赖 Microsoft Store 的 `python3.exe` 执行别名。插件更新后，在 Codex 中打开
`/hooks`，审查并重新信任变更后的四个 hook，关闭当前任务后新开一个任务；如仍
显示旧定义，再重启 Codex。

如果旧版在你回复 `继续开发` 后仍重复阻断，请更新到 v0.3.2 或更新版本。
旧版可暂时回复英文 `continue`；新版已修复 Windows 上中文输入的编码问题。

#### 已经安装过旧版本？

更新插件时，需刷新 Marketplace 缓存以获取 GitHub 远端最新代码：

```bash
codex plugin remove codex-handoff@codex-handoff
codex plugin marketplace remove codex-handoff
codex plugin marketplace add LLeung49/codex-handoff --ref main
codex plugin add codex-handoff@codex-handoff
codex plugin list
```

> **提示**：Codex CLI 会在本地缓存 Marketplace 仓库。更新版本时，请先 `marketplace remove` 再重新 `marketplace add`，以确保拉取远端最新提交，避免反复装回本地旧缓存。

如果确定不再使用它，移除插件后注销 marketplace 即可：

```bash
codex plugin remove codex-handoff@codex-handoff
codex plugin marketplace remove codex-handoff
```

### 2. 正常开发，看到提醒再决定

不需要为了插件改变平时的工作方式。五小时额度高于 15% 时它保持安静；剩余从 15% 降到高于 6% 时，收到一次提醒后，你自己决定是否立即交接。周额度没有这一档软提醒。

### 3. 需要换人时，做一次明确交接

在当前任务运行 `$handoff-prepare`，检查 `.handoff/` 里生成的交接单能否说清：现在停在哪里、做了什么、证据是什么、哪些还没有验收、建议的下一步是什么、还需要你授权什么。若你决定不交接，直接回复 `继续开发` 即可恢复原任务。若开新任务，再运行 `$handoff-continue`；它先做对齐报告，你授权一个明确的下一步后才继续。

## 三个技能分别做什么？

- `$handoff-prepare`：把当前断点、目标、边界、交付/验收状态、决定与风险、唯一下一步写成一份不可变交接单；其他资料只列为 L1/L2 索引，不要求接手时一次读完。
- `$handoff-continue`：让新 agent 先对齐交接单最前面的 L0 和项目说明；后续因具体任务需要再查 L1/L2，说明未读资料与需要澄清之处，然后等待你的授权。它不会自动扫描旧 spec、历史分支或交接单里只是“列举过”的文件。
- `$handoff-context-setup`：可选。它只提议创建稳定的 `agent-context.md` 背景索引；不再维护会过期的进度状态页。

## 想了解实现细节？

<details>
<summary>展开查看 hook、额度与本地文件的实现边界</summary>

五小时额度在剩余 15% 到高于 6% 时产生一次软提醒；≤6% 时产生一次保护性阻断。周额度没有软提醒，≤6% 时也会独立阻断一次。`UserPromptSubmit` 在新请求开始前检查额度；`PostToolUse` 只在一个本地工具完成后记录交接提示；`PreToolUse` 只会在同一轮已触发保护后拒绝下一次受支持的本地工具调用；`PreCompact(auto)` 只提醒，不阻断。

插件不会上传 telemetry。它只读取有限长度的本地 rollout 记录；读取失败或格式异常时 fail-open。去重和同轮保护使用的文件只存放本地状态，不保存 handoff 正文；真正的交接内容始终在项目 `.handoff/` 中。

</details>

## 本地开发

只有希望修改或验证插件时才需要 clone：

```bash
git clone https://github.com/LLeung49/codex-handoff.git
cd codex-handoff/plugins/codex-handoff
python3 -m unittest discover -s tests -v
```

完整的插件与 skill 验证命令见 [插件源码 README](plugins/codex-handoff/README.md)。
