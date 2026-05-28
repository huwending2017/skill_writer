from __future__ import annotations

from datetime import datetime
from pathlib import Path


DEFAULT_LESSONS = """# Skill Writer Lessons

这些规则来自历史技能开发和修复踩坑。每次技能开发、续接和修复都必须优先遵守。

## Excel 配置

- `skill.desc` 和 `skill.de_desc` 都必须填写。只有简单描述或只有详细描述都不合格。
- `skill.skill_type` 只能使用正式表已有值：`1=指挥`、`2=主动`、`3=突击`、`4=被动`、`6=兵种`、`7=阵法`。禁止写 `8`。
- `skill_stage` 的阶段字段必须是 `stage=1/2/...`，禁止把阶段写成 `0`。主键格式是 `技能id_阶段_等级`。
- `war_paper` 的正文必须写 `desc1`，不要只写 `desc`。自定义战报 ID 默认留空，由写回工具按正式表最大 ID 续号。
- Excel 参数字段禁止写 JSON/Python/Lua 字面量，例如 `["ATK",10000]`。应写成 `ATK,10000` 或 `ATK,10000|DEF,5000`。

## Lua 脚本

- 新增生产脚本必须自洽，不能依赖 `test_skill_temp.lua`、`temp_skill_workspace` 或测试 helper。
- 生产脚本必须有关键中文注释：参数、事件时机、状态读写、异常保护、战报插入、层数变化。
- 调试日志必须直接写 `DEBUG("[技能名]", ...)`，不要封装 `debug_log`，否则日志行号无法定位真实分支。
- 指挥、被动、装备等常驻 Buff 必须处理临时失效和恢复，不能在 `uninit_script(..., true)` 时误清长期状态。
- 显示层数 Buff 只能做展示，真实业务层数必须保存在核心 Buff runtime 或明确状态中。
- 续写/修复技能时禁止修改底层战斗框架文件，例如 `module/object/actor.lua`、`module/fight/skill.lua`、`module/fight/buff.lua`、`module/fight/action.lua`、`module/fight/damage.lua`、`module/scene/battle_scene.lua`。只能修改本次任务目录产物，或用户明确要求的新增/既有技能脚本。

## 战报

- 战报是机制契约，不是装饰。层数增减、阈值触发、状态添加/消失、驱散尝试、无目标、首次触发都要考虑展示。
- 事件触发 Buff 响应其他技能或伤害事件时，不能只 `make_effect_records`；需要通过当前 `extern.skill` 插回本次战报，否则 DEBUG 显示写了但前端不展示。
- 战报顺序必须贴近实际触发顺序，不能无故拖到回合结束。

## 复用与性能

- 简单属性、增减伤、倒戈、治疗等优先审计现有配置型 action/buff，能用配置不要新增监听脚本。
- 开发前优先读取 `SKILL_DEV_GUIDE.md`、`battle_knowledge_index`、当前任务 `task_handoff.md` 和 `task_memory.json`，不要无目的全量扫描源码。
- 切换 Codex/Claude 或账号/API key 时，必须沿用任务目录和本地记忆，不能从 0 重建。
"""


class LessonService:
    """Persist global lessons so repeated bugs become tool-level context."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.ensure_exists()

    def ensure_exists(self) -> None:
        if self.path.exists():
            return
        self.path.write_text(DEFAULT_LESSONS.rstrip() + "\n", encoding="utf-8")

    def read(self, max_chars: int = 12000) -> str:
        self.ensure_exists()
        try:
            text = self.path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            return ""
        if len(text) <= max_chars:
            return text
        return text[-max_chars:]

    def prompt_block(self) -> str:
        text = self.read()
        if not text:
            return ""
        return "\n".join(
            [
                "【全局经验沉淀】",
                "下面是工具从历史开发/修复中沉淀出的硬性经验。本次必须优先遵守；如果用户需求与其冲突，需要说明原因并选择更安全的实现。",
                "```markdown",
                text,
                "```",
            ]
        )

    def append_lesson(self, title: str, body: str) -> None:
        self.ensure_exists()
        title = title.strip() or "未命名经验"
        body = body.strip()
        if not body:
            return
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(
                "\n\n"
                f"## {title}\n\n"
                f"- recorded_at: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}`\n\n"
                f"{body}\n"
            )
