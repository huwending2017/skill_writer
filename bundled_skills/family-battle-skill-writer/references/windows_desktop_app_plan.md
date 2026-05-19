# Windows Desktop App Plan

## 目标

把下面这条链路做成一个 Windows 可视化桌面工具：

1. 选择工作目录
2. 选择输入模板
3. 输入技能描述
4. 触发技能开发
5. 触发测试
6. 生成临时 Lua 配置与 `temp_excel_payload.json`
7. 写回 Excel

## 建议技术栈

优先建议：

- Python
- Tkinter 或 PySide6
- `win32com` 操作 Excel

原因：

- 当前本机已经能直接使用 `win32com`
- Excel 回写天然适合 Windows COM
- 跟现有脚本能力复用成本最低

## 最小可用版本

### 页面 1：工程设置

- 工作目录选择
- battle 根目录自动识别
- Excel 路径配置
  - `J_技能表_skill.xlsx`
  - `Z_战报表.xlsx`
- 临时输出目录配置

### 页面 2：技能输入

- 模板选择
  - 单技能开发模板
  - 多技能联动 bundle 模板
  - 最简快速投喂模板
- 描述输入框
- 保护文件输入框
- 额外约束输入框

### 页面 3：生成结果

- 技能拆解结果
- 复用审计结果
- 临时配置预览
- 临时脚本预览
- `temp_excel_payload.json` 预览

### 页面 4：测试与回写

- 测试按钮
- 测试日志输出
- 写入 Excel 副本按钮
- 写回正式 Excel 按钮
- 备份目录选择

## 后端模块建议

拆成 4 个模块：

1. `skill_generation`
   - 调用技能生成流程
   - 输出 Lua / payload / 测试计划

2. `battle_validation`
   - 运行临时测试
   - 生成验证结果

3. `excel_writeback`
   - 复用 `write_temp_skill_excel.py`
   - 提供 dry-run / copy-write / real-write

4. `workspace_manager`
   - 识别 battle_root
   - 组织 `temp_skill_workspace`
   - 管理每次技能任务目录

## 推荐目录结构

```text
skill_desktop_app/
  app.py
  ui/
  services/
    skill_generation.py
    battle_validation.py
    excel_writeback.py
    workspace_manager.py
  models/
  assets/
```

## 第一期必须具备的能力

- 可配置工作目录
- 可配置 Excel 路径
- 可选择模板
- 可保存输入历史
- 可展示生成产物
- 可执行测试
- 可先写副本再写正式 Excel

## 第二期可以增强的能力

- 技能机制知识库检索
- 现有 buff / action 自动复用提示
- 冲突风险提示
- 战报字段自动推荐
- 多技能 bundle 的依赖图可视化

## 和当前 Skill 的关系

这个桌面应用不应该重新发明一套流程，而应该直接复用当前 `$family-battle-skill-writer` 的约束：

- 先复用审计
- 再生成临时配置
- 再测试
- 最后再回写 Excel

也就是说，桌面应用只是流程壳层，核心战斗技能开发规范仍然由 Skill 本身保证。
