# Excel Writeback Workflow

## 目标

把技能开发阶段产出的临时配置，按结构化方式写回原始 Excel：

- `J_技能表_skill.xlsx`
- `Z_战报表.xlsx`

这一步是正式落表前的“受控写回”，不是直接从 Lua 正则硬解析。

## 推荐产物

每次技能开发完成后，临时目录里除了 Lua 配置和测试文件，还应额外生成一份：

- `temp_excel_payload.json`

推荐放置位置：

- `<battle_root>/temp_skill_workspace/<skill_or_bundle_name>/temp_excel_payload.json`

## 为什么不建议直接解析 Lua

当前临时 Lua 配置通常是这种形态：

- 局部常量
- `make_skill()` / `make_stage()` / `make_buff()` 这类函数
- `inject()` 时再把数据写入 `data_skill` / `data_skill_stage` / `data_buff`

在没有稳定 Lua 解释器和统一代码模板保证的情况下，直接从 Lua 反解析到 Excel 行结构不够稳。

所以更推荐的做法是：

1. 生成技能时照常输出临时 Lua 配置。
2. 同时输出一份 `temp_excel_payload.json`。
3. 由回写脚本读取 `temp_excel_payload.json` 写回 Excel。

## Payload 结构

参考：

- `references/excel_payload_template.json`

核心结构：

```json
{
  "version": 1,
  "targets": {
    "skill_workbook": "G:\\\\...\\\\J_技能表_skill.xlsx",
    "war_paper_workbook": "G:\\\\...\\\\Z_战报表.xlsx"
  },
  "rows": {
    "skill": [],
    "skill_stage": [],
    "buff": [],
    "war_paper": []
  }
}
```

## 字段规则

`skill` / `skill_stage` / `buff` 推荐使用 Lua 侧字段名：

- `skill`
  - `id`
  - `skill_lv`
  - 其他字段按 `data_skill` 结构填
- `skill_stage`
  - `skill_id`
  - `skill_level`
  - `stage`
  - 其他字段按 `data_skill_stage` 结构填
- `buff`
  - `id`
  - `level`
  - `update_life`
  - 其他字段按 `data_buff` 结构填

脚本会自动补这些 Excel 主键：

- `skill.key = id_skillLv`
- `skill_stage.key = skillId_stage_skillLevel`
- `buff.key = id_level`

`war_paper` 直接按 Excel sheet 结构填：

- `ID`（新战报必须留空，由写回脚本按当前战报表最大 ID 自动续号；只有更新已存在战报时才允许复用原 ID）
- `name`
- `type`
- `desc1`
- `cost_time`
- `action_type`
- `key_param`
- `effect_desc`
- `beizhu2`
- `param1...param8`

战报配置准则：

- 不要把战报 ID 塞进 `buff.param` / `skill_stage.param` / 其他技能配置参数。
- 生产 `buff_*.lua` / `action_*.lua` 需要插入战报时，在脚本中通过战报配置枚举、常量名或运行时已有的名称映射来引用，避免 Excel 回写续号后参数失效。
- payload 中不要预填很大的临时战报 ID；写回脚本会以 `Z_战报表.xlsx` 当前最大 ID 为起点追加。

## 列化规则

脚本会自动把数组转成 Excel 常用字符串格式：

- 一维数组：`,` 连接
- 二维数组：每组内部 `,`，组与组之间 `|`

例如：

- `[1,2,3]` -> `1,2,3`
- `[[1001],[1002]]` -> `1001|1002`
- `[[5000,"INTELLECT",10000],[1,0]]` -> `5000,INTELLECT,10000|1,0`

## 回写脚本

脚本位置：

- `scripts/write_temp_skill_excel.py`

### 先写入测试副本

```powershell
python C:\Users\2020\.codex\skills\family-battle-skill-writer\scripts\write_temp_skill_excel.py `
  --payload G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\demo\temp_excel_payload.json `
  --copy-to G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\_global\excel_test_copy
```

### 只预览不保存

```powershell
python C:\Users\2020\.codex\skills\family-battle-skill-writer\scripts\write_temp_skill_excel.py `
  --payload G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\demo\temp_excel_payload.json `
  --dry-run
```

### 清理同一技能已存在的重复行

```powershell
python C:\Users\2020\.codex\skills\family-battle-skill-writer\scripts\write_temp_skill_excel.py `
  --payload G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\demo\temp_excel_payload.json `
  --backup-dir G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\_global\excel_backup `
  --dedupe-existing
```

### 写回真实 Excel 前先备份

```powershell
python C:\Users\2020\.codex\skills\family-battle-skill-writer\scripts\write_temp_skill_excel.py `
  --payload G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\demo\temp_excel_payload.json `
  --backup-dir G:\slg\server_version\family\xgame_server\service\battle\temp_skill_workspace\_global\excel_backup
```

## 推荐工作流

1. 生成临时 Lua 配置与脚本。
2. 生成并检查 `temp_excel_payload.json`。
3. 先写入 Excel 副本验证。
4. 用 Excel 人工 spot check：
   - `skill`
   - `skill_stage`
   - `buff`
   - `war_paper`
5. 确认无误后再写回真实 Excel。

重复执行注意：

- 默认会优先按多重标识做 `upsert`，避免同一条配置再次执行时继续插入新行
- 如果历史上已经写出了重复行，可以加 `--dedupe-existing` 做清理

## 适配到 Skill 的要求

后续调用 `$family-battle-skill-writer` 开发新技能时，除了输出：

- 临时 Lua 配置
- 临时脚本
- 测试步骤

还应同步输出：

- `temp_excel_payload.json`

这样“开发技能 -> 测试技能 -> 回写 Excel”才能变成一条完整流水线。
