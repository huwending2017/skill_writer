from __future__ import annotations

import re
from typing import Dict


TEMPLATE_OPTIONS = {
    "single": "单技能/多独立技能开发模板",
    "bundle": "多技能联动 bundle 模板",
    "iterate": "迭代已有技能模板",
    "fast": "最简快速投喂模板",
}

TEMPLATE_LABELS = {
    "single": "单技能 / 多独立技能",
    "bundle": "多技能联动",
    "iterate": "迭代已有技能",
    "fast": "快速生成",
}

TEMPLATE_KEYS_BY_LABEL = {label: key for key, label in TEMPLATE_LABELS.items()}


TEMPLATE_TEXT: Dict[str, str] = {
    "single": """Use $family-battle-skill-writer

技能描述：
{skill_description}

补充说明：
1. 这是单技能还是多技能联动：单技能或多个互不关联的独立技能；只有描述明确互相影响时才按 bundle
2. 是否已有参考实现文件但不能直接照抄：否
3. 是否有保护文件不能修改：{protected_files}
4. 是否要求优先只加配置：否
5. 是否需要战报展示：是，请根据技能效果补齐战报展示
6. 是否需要统计支持：如技能效果需要则补齐统计链路

要求：
1. 先定位 battle_root
2. 先读取/利用 battle knowledge index 和 skill references，做复用审计，优先复用现有 action / buff / add_state / extern / customized_buff_state
3. 能只加配置就不要加脚本；如果必须新增脚本，要说明现有机制为什么不够
4. 简单静态属性/伤害修正优先用配置：例如每层提高武器伤害、每层降低受到伤害，优先检查 buff_add_attr.lua / buff_add_attr_p.lua + data_attr_id，不能直接新增伤害监听脚本
5. 临时产物放到 temp_skill_workspace 子目录，并且后续续接必须沿用同一目录
6. 给出临时 skill / stage / buff / war_paper 配置；若技能描述写了“最大等级为 n / 满级 n / n 级”，skill、skill_stage、buff 必须生成 0-n 共 n+1 条；未写最大等级时默认补齐 0-10 级
7. skill_stage 主键必须使用 技能id_阶段_等级；buff 主键必须使用 buff_id_等级
8. 生成需要的生产脚本，且脚本必须带详尽中文注释：文件头、参数含义、事件时机、状态读写、关键分支、异常保护、伤害/治疗/战报插入都要说明，不能只有少量标题注释；每个非平凡 local function / INTERFACE 方法前都要有中文注释；函数内部关键 if/return、层数变化、缓存读写、监听注册、临时失效恢复、战报清理、伤害改写和 provider 状态消费处也必须就地写中文注释
8.1 新增或实质修改的生产脚本必须在真实逻辑行直接调用 DEBUG("[技能名]", ...) 排障日志，禁止封装 debug_log 包装函数，保证战斗日志行号指向实际分支；日志覆盖 init/uninit、事件分流、概率/阈值判定、状态变化、层数变化、目标数量、伤害/治疗值、战报 ID 和关键提前 return
9. 战报配置准则：不要把战报 ID 写进 buff.param / skill_stage.param；需要插入战报时，在对应生产 buff/action Lua 中用战报配置枚举或常量名引用，war_paper 行的 ID 留空，由 Excel 写回脚本按当前战报表最大 ID 自动续号
9.1 resident buff / 事件触发型 Buff 写战报时，不能只 make_effect_records；如果是在别的技能或伤害事件里响应，必须把 effect 通过 extern.skill 的 clean_effect_record -> make_effect_records -> insert_effect_list(extern.skill, nil) 插回本次战报，否则日志会显示写了但前端战报不展示
9.2 显示层数 Buff / overlying 只允许作为外观展示承载，真实业务层数必须保存在核心 Buff runtime 或明确的状态 Buff 中；BUFF_OVERLYING_EFFECT_FUNC 回调不能把显示 Buff 的 overlying 反写到真实 runtime，避免显示 Buff 被清理/重建成 0 时误清真实层数
10. 生产 Lua 必须自洽，不能依赖 test_skill_temp.lua、temp_skill_workspace、roll_skill_dice 或任何测试专用 helper
11. 单次任务目录统一使用 config/、scripts/、tests/、docs/、repair/、logs/ 子目录；payload 放在 config/temp_excel_payload.json
12. 对层数、指挥失效/恢复、清零但属性保留、驱散、死亡目标、首次/后续触发、战报展示值与内部值分离等机制，在 tests/ 下补充 regression_*.lua 或 mechanism_*.lua 回归测试
13. 生成 temp_excel_payload.json，便于后续写回 Excel
14. 给出测试步骤、预期触发链路、预期战报结果
15. 如果技能描述里包含多个互不关联的技能，请作为“独立技能批量开发”处理：先拆成多个独立工作单元；在实现环境支持并行时，复用审计、脚本编写、单技能测试可以按技能并行推进；不要构造跨技能依赖图，不要让一个技能依赖另一个技能的状态；最后再统一合并到同一个 batch 临时目录、同一个 temp_excel_payload.json，并做一次汇总校验与回写预览

额外约束：
{additional_constraints}
""",
    "bundle": """Use $family-battle-skill-writer

这里有一组联动机制，需要作为一个 bundle 一起分析和开发：

{skill_description}

依赖关系补充：
1. 谁影响谁：请根据上面的描述做完整依赖图分析
2. 哪些效果你认为可能复用现有机制：优先审计现有 action / buff / add_state / extern / customized_buff_state
3. 哪些文件不能修改：{protected_files}
4. 是否已有可运行实现但只允许做行为对比：如无则按无处理

要求：
1. 不要先按兵书 / 自带 / 被动这些标签固化判断
2. 统一按 A 机制影响 B 机制做依赖分析
3. 先读取/利用 battle knowledge index 和 skill references，做 bundle 级复用审计
4. 优先复用现有 action / buff / add_state / extern / customized_buff_state
5. 简单静态属性/伤害修正优先用配置：例如每层提高武器伤害、每层降低受到伤害，优先检查 buff_add_attr.lua / buff_add_attr_p.lua + data_attr_id，不能直接新增伤害监听脚本
6. 如果必须新增脚本，要说明为什么现有机制不够
7. 临时产物统一放到 temp_skill_workspace/<bundle_name>/ 下，后续续接必须沿用同一目录
8. 给出 bundle 级临时配置、脚本、测试方案；若技能描述写了“最大等级为 n / 满级 n / n 级”，skill、skill_stage、buff 必须生成 0-n 共 n+1 条；未写最大等级时默认补齐 0-10 级
9. skill_stage 主键必须使用 技能id_阶段_等级；buff 主键必须使用 buff_id_等级
10. 新增生产脚本必须带详尽中文注释：文件头、参数含义、事件时机、状态读写、关键分支、异常保护、伤害/治疗/战报插入都要说明；每个非平凡 local function / INTERFACE 方法前都要有中文注释；函数内部关键 if/return、层数变化、缓存读写、监听注册、临时失效恢复、战报清理、伤害改写和 provider 状态消费处也必须就地写中文注释；同时必须自洽，不能依赖测试文件或测试专用 helper
10.1 新增或实质修改的生产脚本必须在真实逻辑行直接调用 DEBUG("[技能名]", ...) 排障日志，禁止封装 debug_log 包装函数，保证战斗日志行号指向实际分支；日志覆盖 init/uninit、事件分流、概率/阈值判定、状态变化、层数变化、目标数量、伤害/治疗值、战报 ID 和关键提前 return
11. 战报配置准则：不要把战报 ID 写进 buff.param / skill_stage.param；需要插入战报时，在对应生产 buff/action Lua 中用战报配置枚举或常量名引用，war_paper 行的 ID 留空，由 Excel 写回脚本按当前战报表最大 ID 自动续号
11.1 resident buff / 事件触发型 Buff 写战报时，不能只 make_effect_records；如果是在别的技能或伤害事件里响应，必须把 effect 通过 extern.skill 的 clean_effect_record -> make_effect_records -> insert_effect_list(extern.skill, nil) 插回本次战报，否则日志会显示写了但前端战报不展示
11.2 显示层数 Buff / overlying 只允许作为外观展示承载，真实业务层数必须保存在核心 Buff runtime 或明确的状态 Buff 中；BUFF_OVERLYING_EFFECT_FUNC 回调不能把显示 Buff 的 overlying 反写到真实 runtime，避免显示 Buff 被清理/重建成 0 时误清真实层数
12. 单次任务目录统一使用 config/、scripts/、tests/、docs/、repair/、logs/ 子目录；payload 放在 config/temp_excel_payload.json
13. 对层数、指挥失效/恢复、清零但属性保留、驱散、死亡目标、首次/后续触发、战报展示值与内部值分离等机制，在 tests/ 下补充 regression_*.lua 或 mechanism_*.lua 回归测试
14. 生成 temp_excel_payload.json，便于后续写回 Excel
15. 说明每个技能的触发顺序、异常情况、战报展示

额外约束：
{additional_constraints}
""",
    "iterate": """Use $family-battle-skill-writer

这是一次“迭代已有技能”的需求：新技能机制、新配置或新外部影响会改变之前已经开发完成的技能行为。不要从 0 重新开发旧技能。

迭代需求描述：
{skill_description}

已有技能定位信息：
1. 需要被迭代的旧技能脚本 / buff / action / payload / 任务目录：请从上面的描述中提取；如果描述给了路径，必须优先读取这些路径
2. 新机制如何影响旧技能：请从上面的描述中提取影响点，例如触发、概率、层数、阈值、目标、伤害、持续、失效恢复、战报或统计
3. 哪些文件不能修改：{protected_files}

要求：
1. 先定位 battle_root
2. 先读取用户指定的旧技能脚本、旧 temp_excel_payload.json、IMPLEMENTATION.md、测试文件或历史任务目录；如果没有明确路径，再用技能名 / 技能 id 在 temp_skill_workspace、module/actions_new、module/buffs_new 中定向搜索
3. 明确列出“旧逻辑现在怎么跑”和“新机制需要改变哪一段”，不要把旧技能当成新技能重写
4. 优先做最小迭代：能通过配置、buff_add_state、customized_buff_state、script.extern 或已有 provider/consumer 机制表达，就不要新增重复脚本
5. 如果必须改旧生产脚本，只修改被新机制影响的分支；保留旧技能未受影响的行为、战报和统计
6. 如果新增一个 provider 技能去影响旧技能，优先让 provider 写状态，让旧技能原有 consumer 或最小补丁读取状态；不要让两个脚本各自监听同一事件造成重复触发
7. 产物继续放在旧任务目录，或放到 temp_skill_workspace/<旧技能名>_iteration_<short_topic>，并说明为什么选择该目录
8. 单次任务目录统一使用 config/、scripts/、tests/、docs/、repair/、logs/ 子目录；payload 放在 config/temp_excel_payload.json
9. 更新 temp_excel_payload.json：包含新增技能配置、被迭代旧技能受影响的配置行，以及必要的 war_paper 行；未变化的旧配置不要无意义重写
9.0 战报配置准则：不要把战报 ID 写进 buff.param / skill_stage.param；需要插入战报时，在对应生产 buff/action Lua 中用战报配置枚举或常量名引用，war_paper 行的 ID 留空，由 Excel 写回脚本按当前战报表最大 ID 自动续号
9.1 resident buff / 事件触发型 Buff 写战报时，不能只 make_effect_records；如果是在别的技能或伤害事件里响应，必须把 effect 通过 extern.skill 的 clean_effect_record -> make_effect_records -> insert_effect_list(extern.skill, nil) 插回本次战报，否则日志会显示写了但前端战报不展示
9.2 显示层数 Buff / overlying 只允许作为外观展示承载，真实业务层数必须保存在核心 Buff runtime 或明确的状态 Buff 中；BUFF_OVERLYING_EFFECT_FUNC 回调不能把显示 Buff 的 overlying 反写到真实 runtime，避免显示 Buff 被清理/重建成 0 时误清真实层数
9.1 对新旧行为差异补充 tests/regression_*.lua 或 tests/mechanism_*.lua 回归测试，至少覆盖旧逻辑不变和新机制生效两类场景
9. 新增或修改的生产 Lua 必须带详尽中文注释，特别说明兼容旧逻辑、新机制入口、状态读写、失效恢复、战报和统计；每个非平凡 local function / INTERFACE 方法前都要有中文注释；函数内部关键 if/return、层数变化、缓存读写、监听注册、临时失效恢复、战报清理、伤害改写和 provider 状态消费处也必须就地写中文注释；并在真实逻辑行直接补 DEBUG("[技能名]", ...) 排障日志，禁止 debug_log 包装函数
10. 给出回归测试：旧技能无新机制时行为不变；新机制存在时行为按新规则变化；同时覆盖失效、移除、叠层、死亡、空目标等风险

额外约束：
{additional_constraints}
""",
    "fast": """Use $family-battle-skill-writer

技能描述：
{skill_description}

要求：
1. 先读取/利用 battle knowledge index 和 skill references 做复用审计
2. 能复用就不要新增脚本；必须新增时说明原因
3. 简单静态属性/伤害修正优先用 buff_add_attr.lua / buff_add_attr_p.lua 配置，不要直接新增伤害监听脚本
4. 临时文件放到 temp_skill_workspace，续接时沿用同一任务目录
5. 输出配置、脚本、测试；新增生产脚本必须带详尽中文注释，覆盖参数、事件、状态、关键分支、异常保护和战报插入；每个非平凡 local function / INTERFACE 方法前都要有中文注释；函数内部关键 if/return、层数变化、缓存读写、监听注册、临时失效恢复、战报清理、伤害改写和 provider 状态消费处也必须就地写中文注释；并在真实逻辑行直接补 DEBUG("[技能名]", ...) 排障日志，禁止 debug_log 包装函数
6. 若技能描述写了“最大等级为 n / 满级 n / n 级”，skill、skill_stage、buff 必须生成 0-n 共 n+1 条；未写最大等级时默认补齐 0-10 级；skill_stage 主键使用 技能id_阶段_等级
7. 生产 Lua 必须自洽，不能依赖 test_skill_temp.lua 或测试专用 helper
8. 单次任务目录统一使用 config/、scripts/、tests/、docs/、repair/、logs/ 子目录；payload 放在 config/temp_excel_payload.json
9. 战报配置准则：不要把战报 ID 写进 buff.param / skill_stage.param；需要插入战报时，在对应生产 buff/action Lua 中用战报配置枚举或常量名引用，war_paper 行的 ID 留空，由 Excel 写回脚本按当前战报表最大 ID 自动续号
9.1 resident buff / 事件触发型 Buff 写战报时，不能只 make_effect_records；如果是在别的技能或伤害事件里响应，必须把 effect 通过 extern.skill 的 clean_effect_record -> make_effect_records -> insert_effect_list(extern.skill, nil) 插回本次战报，否则日志会显示写了但前端战报不展示
9.2 显示层数 Buff / overlying 只允许作为外观展示承载，真实业务层数必须保存在核心 Buff runtime 或明确的状态 Buff 中；BUFF_OVERLYING_EFFECT_FUNC 回调不能把显示 Buff 的 overlying 反写到真实 runtime，避免显示 Buff 被清理/重建成 0 时误清真实层数
10. 对层数、指挥失效/恢复、清零但属性保留、驱散、死亡目标、首次/后续触发、战报展示值与内部值分离等机制，在 tests/ 下补充 regression_*.lua 或 mechanism_*.lua 回归测试
11. 生成 temp_excel_payload.json，便于后续写回 Excel

保护文件：
{protected_files}

额外约束：
{additional_constraints}
""",
}


def build_prompt(
    template_name: str,
    skill_description: str,
    protected_files: str,
    additional_constraints: str,
) -> str:
    template = TEMPLATE_TEXT.get(template_name, TEMPLATE_TEXT["single"])
    prompt = template.format(
        skill_description=skill_description.strip(),
        protected_files=protected_files.strip() or "无",
        additional_constraints=additional_constraints.strip() or "无",
    )
    return (
        prompt.rstrip()
        + "\n\n"
        + build_level_rule_hint(skill_description)
        + "\n\n"
        + build_battle_report_rule_hint()
        + "\n\n"
        + build_excel_config_format_rule()
    )


def build_battle_report_rule_hint() -> str:
    return "\n".join(
        [
            "战报覆盖硬性规则：",
            "1. 战报是技能机制契约，不是附加装饰；实现前必须在 docs/IMPLEMENTATION.md 写“战报覆盖矩阵”。",
            "2. 覆盖矩阵至少包含：触发入口、成功/失败/无目标、层数增加/减少/转换/当前值、伤害/治疗/减免/分摊、状态添加/消失/临时失效/恢复、首次阈值/后续触发、战报插入时机、war_paper name、num_list 参数顺序。",
            "3. 玩家需要理解的机制变化必须有战报或明确复用已有战报：例如失去/获得层数、每层属性/倒戈/减伤收益、驱散尝试/成功/无可驱散目标、首次达到阈值、状态开始和结束。",
            "4. resident buff 或事件触发 Buff 响应其他技能/伤害事件时，不能只 make_effect_records；必须通过 extern.skill 的 clean_effect_record -> make_effect_records -> insert_effect_list(extern.skill, nil) 插回当前战报。",
            "5. 战报顺序必须贴近实际触发顺序；例如受到伤害时应按减伤说明、实际伤害、层数变化、层数转换、追加攻击/驱散/状态的顺序展示，不能无故延迟到回合结束。",
            "6. 百分比参数使用 RECORD_NUM_DEF.PERCENT_TYPE；war_paper 文本占位符与 Lua num_list 顺序必须一一对应。",
        ]
    )


def template_labels() -> list[str]:
    return [TEMPLATE_LABELS[key] for key in TEMPLATE_OPTIONS]


def template_label_from_key(template_name: str) -> str:
    return TEMPLATE_LABELS.get(template_name, TEMPLATE_LABELS["single"])


def template_key_from_label(value: str) -> str:
    if value in TEMPLATE_TEXT:
        return value
    return TEMPLATE_KEYS_BY_LABEL.get(value, "single")


def build_excel_config_format_rule() -> str:
    return "\n".join(
        [
            "Excel 配置字段格式硬性规则：",
            "1. temp_excel_payload.json 里会写入 Excel 的字段，禁止输出 JSON/Python/Lua table 字面量。",
            "2. 禁止示例：['ATK',10000]、[\"ATK\",10000]、{ATK=10000}、{\"attr\":\"ATK\"}。",
            "3. 一维配置必须写成逗号串：ATK,10000；多组配置必须写成管道分组：ATK,10000|DEF,5000。",
            "4. 属性枚举、目标枚举、事件枚举在 Excel 参数串里不加引号，不带方括号；正式 Lua 导表必须能直接按现有脚本解析。",
        ]
    )


def build_level_rule_hint(skill_description: str) -> str:
    inferred = infer_level_rule(skill_description)
    lines = [
        "等级配置规则（工具自动识别）：",
        "1. 如果描述里明确写了“技能等级:n / 最大等级:n / 满级:n / n级”，以 n 为准，生成 0..n 共 n+1 条。",
        "2. 如果没有明确等级，但写了“技能类别:自带”，默认生成 0..10。",
        "3. 如果没有明确等级，但写了“技能类别:兵书”或“技能类别:装备”，默认生成 0..1。",
        "4. 生成 temp_excel_payload.json 时，请在 skill / skill_stage / buff 相关行写入 max_lv，避免本地编译和 Excel 回写时误判。",
    ]
    if inferred:
        lines.append(f"5. 当前描述推断结果：{inferred}")
    return "\n".join(lines)


def infer_level_rule(skill_description: str) -> str:
    text = skill_description.strip()
    if not text:
        return ""

    explicit_patterns = [
        r"技能等级\s*[:：=]\s*(\d+)",
        r"最大等级\s*[:：=为]?\s*(\d+)",
        r"满级\s*[:：=为]?\s*(\d+)",
        r"等级上限\s*[:：=为]?\s*(\d+)",
    ]
    for pattern in explicit_patterns:
        match = re.search(pattern, text)
        if match:
            level = int(match.group(1))
            return f"明确等级 {level}，配置 0..{level}"

    category_match = re.search(r"技能类别\s*[:：=]\s*([^\s，,。；;]+)", text)
    category = category_match.group(1) if category_match else text
    if "兵书" in category:
        return "技能类别为兵书，未写明确等级，配置 0..1"
    if "装备" in category:
        return "技能类别为装备，未写明确等级，配置 0..1"
    if "自带" in category:
        return "技能类别为自带，未写明确等级，配置 0..10"
    return ""
