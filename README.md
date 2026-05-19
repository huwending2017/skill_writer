# Skill Writer 使用说明

Skill Writer 是用于辅助生成、检查、测试并回写战斗技能配置的桌面工具。它会调用 Codex 生成技能 Lua、临时配置、测试文件和 Excel 回写 payload，并在正式 Excel 写回成功后完成知识索引沉淀、内置 skill 同步和临时产物清理。

## 目录结构

```text
G:\skill_writer
  app.py                         # 桌面工具入口
  skill_writer_app/              # 桌面工具源码
  scripts/                       # 工具脚本
  bundled_skills/                # 内置 Codex skills，当前是技能源头
  data/                          # 本机运行状态、历史、日志、附件，不是源码
  build_exe.ps1 / .bat           # 构建桌面 EXE
  package_release.ps1 / .bat     # 打包 release zip
  clean_workspace.ps1 / .bat     # 清理构建产物、日志、缓存和运行状态
  SkillWriterDesktop.spec        # PyInstaller 配置
```

运行后会自动生成以下本机状态或产物，这些都不是源码：

```text
build/
dist/
release/
dist_rebuild/
data/
__pycache__/
.pycache_tmp/
*.pyc
```

这些内容已写入 `.gitignore`，可以用 `clean_workspace.bat` 清理。

## 启动工具

源码方式启动：

```powershell
cd /d G:\skill_writer
python app.py
```

EXE 方式启动：

```text
G:\skill_writer\dist\SkillWriterDesktop\SkillWriterDesktop.exe
```

如果 `dist/` 不存在，先执行构建。

## 构建 EXE

```powershell
cd /d G:\skill_writer
powershell -ExecutionPolicy Bypass -File .\build_exe.ps1
```

构建脚本会：

1. 确认本机可用 Codex CLI。
2. 同步 `bundled_skills/` 到 Codex 运行目录。
3. 清理旧的 `build/` 和 `dist/SkillWriterDesktop/`。
4. 使用 PyInstaller 构建桌面程序。
5. 输出到 `dist/SkillWriterDesktop/`。
6. 构建成功后清理 `build/` 中间目录，避免根目录长期堆积。

## 打包 Release

```powershell
cd /d G:\skill_writer
powershell -ExecutionPolicy Bypass -File .\package_release.ps1
```

输出位置：

```text
G:\skill_writer\release\SkillWriterDesktop_yyyyMMdd_HHmmss.zip
```

## 清理工作区

完整清理：

```powershell
G:\skill_writer\clean_workspace.bat
```

保留用户状态，只清理构建产物和缓存：

```powershell
G:\skill_writer\clean_workspace.bat -KeepUserState
```

清理脚本会校验目标路径必须在 `G:\skill_writer` 内，避免误删工程外文件。

## 内置 Codex Skill

当前内置 skill：

```text
G:\skill_writer\bundled_skills\family-battle-skill-writer
```

这是 skill 的源头。不要只改 Codex 运行目录：

```text
%USERPROFILE%\.codex\skills\family-battle-skill-writer
```

正确维护方式：

1. 先修改 `G:\skill_writer\bundled_skills\family-battle-skill-writer`。
2. 执行同步：

```powershell
cd /d G:\skill_writer
python .\scripts\sync_bundled_skills.py
```

3. 如需发布到其他机器，重新执行 `build_exe.ps1` 和 `package_release.ps1`。

工具启动时也会自动同步 bundled skill 到 Codex 运行目录。

## 技能生成流程

推荐流程：

1. 选择工作区，工具定位 `xgame_server/service/battle`。
2. 输入技能描述。
3. 生成 Prompt。
4. 执行技能开发。
5. 本地预审。
6. 本地编译。
7. 技能测试。
8. 预览 Excel 回写。
9. 写入 Excel 副本。
10. 人工检查副本。
11. 确认无误后写回正式 Excel。

自动串行可以覆盖大部分步骤，但正式 Excel 写回属于高风险步骤，建议保留人工确认。

Excel 回写现在会额外输出结构化摘要：

- 每个 sheet 新增 / 更新多少行
- 本次写入覆盖的行号范围
- 本次 key 的起止范围
- 如果发生去重或重排，会单独列出
- 真实写入后会按本次 key 做一次回读校验；若回读缺 key，任务直接失败

当已经做过一次预览后，点击“写回正式 Excel”会先展示最近一次摘要，再要求二次确认。

### 单次任务目录

每一次技能开发只占用一个任务目录，目录内部固定为：

```text
temp_skill_workspace/<task_name>/
  config/    # temp_excel_payload.json、temp_skill_config.lua
  scripts/   # 任务私有的临时 Lua 草稿
  tests/     # test_skill_temp.lua、test_runtime_validation.lua
  docs/      # IMPLEMENTATION.md
  repair/    # 修复对话、截图、附件
  logs/      # 与该任务直接相关的日志
```

全局缓存、Excel 备份和测试副本统一放在 `temp_skill_workspace/_global/`，不会再混入任务列表。

### 单技能模板里的多技能输入

界面里的 `单技能 / 多独立技能` 模板对应内部 `single` 模板。如果一次输入多个互不关联的技能，工具会要求模型按“独立技能批量开发”处理：

- 每个技能单独拆解、单独复用审计、单独生成配置和脚本。
- 在执行环境支持时，各技能的复用审计、脚本编写、单技能测试可以并行推进。
- 不构造跨技能依赖图。
- 不让一个技能依赖另一个技能的运行时状态。
- 只有在各自完成后，才统一合并到同一个批次目录和同一个 `temp_excel_payload.json`。
- 合并前必须再做一次汇总校验，重点检查 ID 冲突、脚本命名冲突、战报 ID 冲突和写回顺序。
- 可以共用一个 batch 临时目录和一个 `temp_excel_payload.json`，方便统一测试、预览和回写。

只有技能描述明确写了互相影响、联动、改变另一个技能概率/层数/触发/目标/伤害等关系时，才应切换到 `多技能联动` 模板。

### 迭代已有技能

如果新机制会影响之前已经开发完成的技能，选择 `迭代已有技能` 模板。描述里建议明确写：

- 被迭代的旧技能名 / 技能 id。
- 旧脚本路径，例如 `module/buffs_new/buff_xxx.lua` 或 `module/actions_new/action_xxx.lua`。
- 旧任务目录或旧 `temp_excel_payload.json`。
- 新机制具体影响旧技能的哪一块：触发、概率、层数、阈值、目标、伤害、战报、统计等。

这个模板会要求模型先读取旧脚本和旧产物，保留旧技能在没有新机制时的行为，只对新机制影响的分支做最小迭代，并给出“无新机制回归”和“有新机制生效”两组测试。

## 技能会话与修复

工具会把每次技能开发、预审、编译、测试和 Excel 写回记录到 `history.json`。`技能会话` 页默认按同一个任务目录或 payload 聚合，使用方式类似会话列表：

1. 左侧选择或双击某一次技能会话。
2. 右侧查看会话详情、历史修复对话和原始任务信息。
3. 在底部连续粘贴问题、战报日志或复现步骤。
4. 截图后可以直接在输入框里按 `Ctrl+V`，工具会保存为 PNG 并加入附件；完整日志也可以点击 `选择文件`。
5. 点击 `发送修复`，工具会优先续接该技能原来的 Codex session，并沿用原任务目录、Lua、payload 和测试产物。

如果同一个技能会话里同时有导表记录和开发记录，工具会优先选择带 `session_id` 的 `技能开发` / `续接修复` 记录，避免修复时误命中 Excel 写回任务。

修复对话会保存在对应任务目录：

```text
temp_skill_workspace/<当前任务目录>/repair/_repair_chat.md
temp_skill_workspace/<当前任务目录>/repair/attachments/
temp_skill_workspace/<当前任务目录>/repair/clipboard/
```

## 环境体检、健康面板与任务记忆

工作台会提供“环境体检”和“健康状态”：

- 环境体检会检查 Python、Codex CLI、Claude CLI、工作区、battle_root、Excel 路径和临时目录写权限。
- 当前任务健康面板会展示任务目录、payload、已完成步骤、下一步、最近产物和结构化记忆状态。
- 每次流程推进都会写入 `task_state.json`、`task_handoff.md` 和 `task_memory.json`。
- `task_memory.json` 是跨模型续接用的结构化记忆，Codex / Claude 切换后也应优先沿用它，不从 0 重跑。

本地测试会自动执行：

```text
tests/test_runtime_validation.lua
tests/test_skill_temp.lua
tests/regression_*.lua
tests/mechanism_*.lua
```

涉及层数、指挥失效/恢复、清零但属性保留、驱散、死亡目标、首次/后续触发、战报展示值与内部值分离等高风险机制时，应补充 `regression_*.lua` 或 `mechanism_*.lua`。

## 分发给其他人使用

`dist\SkillWriterDesktop\` 可以整体发给其他人使用。对方机器至少需要具备：

- 一个可用的执行后端：`Codex CLI` 或 `Claude Code CLI`
- 一个可用的本地 `Python`，用于本地预审、编译、测试和 Excel 回写脚本
- 能访问他们自己的战斗工程目录与配置表目录

工具会随包携带 `bundled_skills/` 和 `scripts/`，启动时会自动把 Codex 侧 skill 同步到当前用户自己的 `%USERPROFILE%\.codex\skills`。使用 Claude 后端时，工具会直接把随包的本地 skill 路径交给 Claude 读取，不依赖当前机器已经存在 Codex skill。

附件里的文本日志会自动尝试 UTF-8 / GBK 解码，并截取尾部关键内容放入修复 prompt；图片会作为证据路径传给模型。界面不再单独显示一个空的“会话对话”框，已有修复对话会合并显示在会话详情里。

## 正式 Excel 写回后的自动收尾

正式 Excel 写回成功后，工具会自动执行收尾：

1. 重建 battle 能力索引：

```text
<battle_root>/temp_skill_workspace/_global/_battle_knowledge_cache/
  battle_knowledge_index.json
  battle_knowledge_index.md
```

2. 同步内置 skill 到 Codex 运行目录：

```text
G:\skill_writer\bundled_skills\family-battle-skill-writer
  -> %USERPROFILE%\.codex\skills\family-battle-skill-writer
```

3. 清理本次临时产物。

会清理：

```text
temp_skill_workspace/<当前任务目录>
temp_skill_workspace/_global/excel_test_copy
temp_skill_workspace/_global/excel_writeback_test
当前配置的 Excel 副本目录
```

会保留：

```text
temp_skill_workspace/_global/_battle_knowledge_cache
temp_skill_workspace/_global/excel_backup
正式 Excel
正式 Lua
G:\skill_writer\bundled_skills
```

4. 清空工具中的当前 payload 和 task_dir 选择，避免下次误用旧任务。

预览回写和副本写入不会触发清理，方便检查和回溯。

## 知识沉淀规则

每次新增或实质修改可复用的生产 `BUFF` / `ACTION` 后，必须沉淀到 skill 能力体系：

- 更新相关 reference catalog。
- 如果影响复用定位，重建 `battle_knowledge_index`。
- 修改 skill 时先改 `G:\skill_writer\bundled_skills`，再同步到 `.codex\skills`。

这样能避免后续生成技能时重复造已有机制，也能让 Codex 更快定位可复用的 BUFF/ACTION。

## 常见问题

### 1. Codex 运行目录没有 skill

运行：

```powershell
cd /d G:\skill_writer
python .\scripts\sync_bundled_skills.py
```

### 2. 构建失败，提示 dist 文件被占用

通常是旧的 `SkillWriterDesktop.exe` 还在运行。关闭工具后重新构建：

```powershell
powershell -ExecutionPolicy Bypass -File G:\skill_writer\build_exe.ps1
```

### 3. 想恢复干净源码环境

```powershell
G:\skill_writer\clean_workspace.bat
```

### 4. 正式 Excel 写回前是否会清理临时文件

不会。清理只在正式 Excel 写回成功后触发。
