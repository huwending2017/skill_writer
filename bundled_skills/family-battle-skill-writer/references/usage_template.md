# Battle Skill Writer Usage Template

在使用下面这个技能时，直接复制对应模板并填写即可：

- `$family-battle-skill-writer`

## Simple Single / Independent Batch Template

```text
Use $family-battle-skill-writer

技能描述：
<这里填写一个技能，或多个互不关联技能的完整描述>

补充说明：
1. 这是单技能还是多技能联动：<单技能 / 多个互不关联的独立技能；只有互相影响才写多技能联动>
2. 是否已有参考实现文件但不能直接照抄：<是/否>
3. 是否有保护文件不能修改：<列出文件路径，没有就写无>
4. 是否要求优先只加配置：<是/否>
5. 是否需要战报展示：<是/否，若是请描述>
6. 是否需要统计支持：<是/否，若是请描述>

要求：
1. 先定位 battle_root
2. 先做复用审计，优先复用现有 action / buff / add_state / extern / customized_buff_state
3. 能只加配置就不要加脚本
4. 临时产物放到 temp_skill_workspace 子目录
5. 给出临时 skill / stage / buff / war_paper 配置
6. 生成需要的脚本，且脚本要带详细中文注释，尽量细到每一步
7. 给出测试步骤、预期触发链路、预期战报结果
8. 如果一次填写多个互不关联技能，按独立批量开发处理：先拆成多个独立工作单元；环境支持时可以按技能并行做复用审计、脚本编写、单技能测试；不要构造跨技能依赖，不要让一个技能依赖另一个技能的运行时状态；最后再合并到一个 batch 临时目录和一个 payload，做统一冲突检查
```

## Linked-Skill Bundle Template

```text
Use $family-battle-skill-writer

这里有一组联动机制，需要作为一个 bundle 一起分析和开发：

1. 技能A：
<填写描述>

2. 技能B：
<填写描述>

3. 技能C或Buff机制：
<填写描述>

依赖关系补充：
1. 谁影响谁：<例如 A 影响 B，C 影响 A>
2. 哪些效果你认为可能复用现有机制：<可选填写>
3. 哪些文件不能修改：<列出文件路径，没有就写无>
4. 是否已有可运行实现但只允许做行为对比：<是/否>

要求：
1. 不要先按兵书 / 自带 / 被动这些标签固化判断
2. 统一按 A 机制影响 B 机制做依赖分析
3. 先做 bundle 级复用审计
4. 优先复用现有 action / buff / add_state / extern / customized_buff_state
5. 如果必须新增脚本，要说明为什么现有机制不够
6. 临时产物统一放到 temp_skill_workspace/<bundle_name>/ 下
7. 给出 bundle 级临时配置、脚本、测试方案，且新增脚本需要带详细中文注释
8. 说明每个技能的触发顺序、异常情况、战报展示
```

## Existing Skill Iteration Template

```text
Use $family-battle-skill-writer

这是一次迭代已有技能的需求，不是从 0 开发旧技能。

迭代需求描述：
<填写新机制，以及它会影响哪个旧技能>

已有技能定位：
1. 旧技能名 / 技能 id：<填写>
2. 旧脚本路径：<例如 module/buffs_new/buff_xxx.lua，没有就写无>
3. 旧任务目录或 payload：<例如 temp_skill_workspace/xxx/temp_excel_payload.json，没有就写无>
4. 新机制影响点：<触发、概率、层数、阈值、目标、伤害、战报、统计等>
5. 保护文件：<不能修改的文件，没有就写无>

要求：
1. 先读取明确给出的旧脚本 / payload / 任务目录
2. 说明旧技能当前怎么跑，新机制要改变哪一段
3. 优先用 provider 状态、buff_add_state、customized_buff_state、script.extern 或已有状态 key 影响旧技能
4. 只做最小补丁，旧技能在没有新机制时行为必须保持不变
5. 更新必要的 temp_excel_payload.json 行，不要无意义重写旧配置
6. 给出两组测试：无新机制回归测试；有新机制生效测试
```

## Minimal Fast Template

```text
Use $family-battle-skill-writer

技能描述：
<直接填写>

要求：
1. 先做复用审计
2. 能复用就不要新增脚本
3. 临时文件放到 temp_skill_workspace
4. 输出配置、脚本、测试，脚本带详细中文注释
```

## 建议补充的信息

如果你希望产出更稳定，尽量补充这些内容：

- 完整技能描述原文
- 触发时机
- 目标规则
- 持续回合
- 概率规则
- 是否受另一个技能或 Buff 影响
- 是否需要特殊战报展示
- 是否存在保护文件不能修改

## 这个 Skill 的预期产出

正常情况下，这个 Skill 应该返回：

1. 技能拆解与依赖分析
2. 复用审计结果
3. 临时目录路径
4. 临时配置结构
5. 需要新增或复用的脚本方案
6. 测试步骤
7. 预期触发链路与战报表现
