from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Sequence


@dataclass(frozen=True)
class ModelPreset:
    key: str
    label: str
    vendor: str
    model_name: str
    preset_args: Sequence[str]
    release_date: str
    source_url: str
    summary: str
    support_note: str
    recommended_for: str


@dataclass(frozen=True)
class ProfileShortcut:
    key: str
    label: str
    extra_args: str
    note: str


MODEL_PRESETS: List[ModelPreset] = [
    ModelPreset(
        key="openai_gpt54",
        label="OpenAI GPT-5.4",
        vendor="OpenAI",
        model_name="gpt-5.4",
        preset_args=(),
        release_date="2026-03-05",
        source_url="https://openai.com/index/introducing-gpt-5-4/",
        summary="当前 OpenAI 主力高质量模型，适合复杂技能开发、长流程调试和多文件改造。",
        support_note="Codex 原生可用，推荐作为默认开发模型。",
        recommended_for="默认技能开发、稳定主力、复杂技能脚本",
    ),
    ModelPreset(
        key="openai_gpt54_pro",
        label="OpenAI GPT-5.4 Pro",
        vendor="OpenAI",
        model_name="gpt-5.4-pro",
        preset_args=(),
        release_date="2026-03-05",
        source_url="https://openai.com/index/introducing-gpt-5-4/",
        summary="更偏极致质量，适合复杂联动技能、疑难战报与机制排查。",
        support_note="Codex 原生可用，但通常成本更高、速度更慢。",
        recommended_for="复杂联动、难题排查、最终收口",
    ),
    ModelPreset(
        key="openai_gpt53_codex",
        label="OpenAI GPT-5.3-Codex",
        vendor="OpenAI",
        model_name="gpt-5.3-codex",
        preset_args=(),
        release_date="2026-02-05",
        source_url="https://openai.com/index/introducing-gpt-5-3-codex/",
        summary="强 agentic coding 模型，适合持续迭代式开发、重构和工具链联动。",
        support_note="Codex 原生可用，适合偏代码执行和改动推进。",
        recommended_for="代码推进、重构、长回路修正",
    ),
    ModelPreset(
        key="openai_gpt53_codex_spark",
        label="OpenAI GPT-5.3-Codex-Spark",
        vendor="OpenAI",
        model_name="gpt-5.3-codex-spark",
        preset_args=(),
        release_date="2026-02-12",
        source_url="https://openai.com/index/introducing-gpt-5-3-codex-spark/",
        summary="偏极速响应，适合快速试错、小步修复和短回路迭代。",
        support_note="Codex 原生可用，质量通常不如 GPT-5.4 / GPT-5.3-Codex。",
        recommended_for="快速试错、小步迭代、轻量改动",
    ),
    ModelPreset(
        key="anthropic_claude_sonnet4",
        label="Anthropic Claude Sonnet 4",
        vendor="Anthropic",
        model_name="claude-sonnet-4-20250514",
        preset_args=(),
        release_date="2025-05-14",
        source_url="https://docs.anthropic.com/en/docs/about-claude/models/all-models",
        summary="高性能平衡型 Claude 4 模型，代码和推理兼顾。",
        support_note="通常需要你的 Codex profile/provider 接到 Anthropic；可配合 profile 快捷按钮使用。",
        recommended_for="平衡质量与速度、长文本阅读、多人协作脚本",
    ),
    ModelPreset(
        key="anthropic_claude_opus41",
        label="Anthropic Claude Opus 4.1",
        vendor="Anthropic",
        model_name="claude-opus-4-1-20250805",
        preset_args=(),
        release_date="2025-08-05",
        source_url="https://docs.anthropic.com/en/docs/about-claude/models/all-models",
        summary="Anthropic 当前更强的高端推理与编码模型。",
        support_note="通常需要你的 Codex profile/provider 接到 Anthropic；更适合高难度分析，速度和成本更高。",
        recommended_for="超复杂机制分析、长链路复盘、最终评审",
    ),
    ModelPreset(
        key="google_gemini_25_pro",
        label="Google Gemini 2.5 Pro",
        vendor="Google",
        model_name="gemini-2.5-pro",
        preset_args=(),
        release_date="2025-06",
        source_url="https://ai.google.dev/gemini-api/docs/models",
        summary="长上下文和复杂代码分析能力强，适合大技能包、长配置链路阅读。",
        support_note="需要你的 Codex provider/profile 已支持 Gemini；通常需在额外参数中补 `-p <profile>`。",
        recommended_for="大仓库阅读、长上下文、复杂配置链路",
    ),
    ModelPreset(
        key="deepseek_chat",
        label="DeepSeek Chat (V3.1-Terminus)",
        vendor="DeepSeek",
        model_name="deepseek-chat",
        preset_args=(),
        release_date="2025-09-22",
        source_url="https://api-docs.deepseek.com/updates/",
        summary="偏高性价比的通用编码模型，适合日常开发与批量小改动。",
        support_note="需要你的 Codex provider/profile 指向 DeepSeek OpenAI-compatible 网关。",
        recommended_for="性价比日常开发、批量改动、常规编码",
    ),
    ModelPreset(
        key="deepseek_reasoner",
        label="DeepSeek Reasoner (V3.1-Terminus)",
        vendor="DeepSeek",
        model_name="deepseek-reasoner",
        preset_args=(),
        release_date="2025-09-22",
        source_url="https://api-docs.deepseek.com/updates/",
        summary="偏推理链路和分析，适合复杂技能拆解、事件流核对与复盘。",
        support_note="需要你的 Codex provider/profile 指向 DeepSeek；速度通常慢于 chat。",
        recommended_for="技能拆解、事件流核对、逻辑复盘",
    ),
    ModelPreset(
        key="kimi_code_custom",
        label="Kimi Code / Moonshot（自定义模型名）",
        vendor="Moonshot AI",
        model_name="",
        preset_args=("-p", "kimi"),
        release_date="N/A",
        source_url="https://platform.moonshot.cn/",
        summary="通过 Codex profile 接入 Moonshot / Kimi Code 的 OpenAI-compatible 网关，适合试用 Kimi 系编码模型。",
        support_note="需要先在 Codex profile 中配置 kimi provider/base_url 和 API key；选择此预设会自动追加 `-p kimi`，只需填写实际模型名。",
        recommended_for="Kimi Code 试用、成本/效果对比、替代模型编码流程",
    ),
    ModelPreset(
        key="xai_grok_420",
        label="xAI Grok 4.20",
        vendor="xAI",
        model_name="grok-4.20",
        preset_args=(),
        release_date="2026-04",
        source_url="https://docs.x.ai/developers/models",
        summary="当前 xAI 旗舰模型，偏速度与 agentic tool calling。",
        support_note="需要你的 Codex provider/profile 已支持 xAI；如果未配置会直接报错。",
        recommended_for="工具联动、速度优先、探索式推进",
    ),
    ModelPreset(
        key="xai_grok_420_multi",
        label="xAI Grok 4.20 Multi-Agent",
        vendor="xAI",
        model_name="grok-4.20-multi-agent",
        preset_args=(),
        release_date="2026-04",
        source_url="https://docs.x.ai/developers/model-capabilities/text/multi-agent",
        summary="偏多智能体协作和复杂研究流程，适合超长链路分析。",
        support_note="需要你的 Codex provider/profile 已支持 xAI；通常成本与延迟更高。",
        recommended_for="超长链路、研究型任务、多阶段分析",
    ),
    ModelPreset(
        key="local_ollama_custom",
        label="本地 OSS / Ollama（自定义模型名）",
        vendor="Local",
        model_name="",
        preset_args=("--oss", "--local-provider", "ollama"),
        release_date="N/A",
        source_url="https://github.com/QwenLM/Qwen3-Coder",
        summary="适合内网、本地试验或低成本流程。可配合 Qwen3-Coder 等本地模型。",
        support_note="选择后请手动填写模型名，例如你本地真实安装的 Ollama tag。",
        recommended_for="本地离线、低成本、内网环境",
    ),
    ModelPreset(
        key="local_lmstudio_custom",
        label="本地 OSS / LM Studio（自定义模型名）",
        vendor="Local",
        model_name="",
        preset_args=("--oss", "--local-provider", "lmstudio"),
        release_date="N/A",
        source_url="https://github.com/QwenLM/Qwen3-Coder",
        summary="适合本地 GUI 模型服务场景，便于切换不同开源 coder 模型。",
        support_note="选择后请手动填写模型名，并确保 LM Studio 本地服务已启动。",
        recommended_for="本地 GUI 服务、快速试模型、开源 coder",
    ),
]


MODEL_PRESET_BY_KEY: Dict[str, ModelPreset] = {preset.key: preset for preset in MODEL_PRESETS}

PROFILE_SHORTCUTS: List[ProfileShortcut] = [
    ProfileShortcut("clear", "清空", "", "清空额外参数"),
    ProfileShortcut("openai", "OpenAI", "", "OpenAI 原生通常无需额外 profile"),
    ProfileShortcut("anthropic", "Anthropic", "-p anthropic", "通过 Codex profile 接 Anthropic"),
    ProfileShortcut("gemini", "Gemini", "-p gemini", "通过 Codex profile 接 Google Gemini"),
    ProfileShortcut("deepseek", "DeepSeek", "-p deepseek", "通过 Codex profile 接 DeepSeek"),
    ProfileShortcut("kimi", "Kimi", "-p kimi", "通过 Codex profile 接 Moonshot / Kimi Code"),
    ProfileShortcut("xai", "xAI", "-p xai", "通过 Codex profile 接 xAI"),
    ProfileShortcut("ollama", "Ollama", "--oss --local-provider ollama", "走本地 Ollama provider"),
    ProfileShortcut("lmstudio", "LM Studio", "--oss --local-provider lmstudio", "走本地 LM Studio provider"),
]

SCENE_TO_PRESET_KEY: Dict[str, str] = {
    "默认开发": "openai_gpt54",
    "复杂联动": "openai_gpt54_pro",
    "长上下文阅读": "google_gemini_25_pro",
    "代码推进/重构": "openai_gpt53_codex",
    "快速试错": "openai_gpt53_codex_spark",
    "性价比开发": "deepseek_chat",
    "逻辑拆解/复盘": "deepseek_reasoner",
    "Kimi Code": "kimi_code_custom",
    "Claude 平衡型": "anthropic_claude_sonnet4",
    "Claude 高强度": "anthropic_claude_opus41",
    "本地离线": "local_ollama_custom",
}


def get_preset(key: str) -> ModelPreset:
    return MODEL_PRESET_BY_KEY.get(key, MODEL_PRESETS[0])


def preset_labels() -> List[str]:
    return [preset.label for preset in MODEL_PRESETS]


def scene_labels() -> List[str]:
    return list(SCENE_TO_PRESET_KEY.keys())


def label_to_key_map() -> Dict[str, str]:
    return {preset.label: preset.key for preset in MODEL_PRESETS}


def build_preset_note(preset: ModelPreset) -> str:
    return (
        f"模型：{preset.label}\n"
        f"厂商：{preset.vendor}\n"
        f"模型名：{preset.model_name or '请手填'}\n"
        f"发布日期：{preset.release_date}\n"
        f"摘要：{preset.summary}\n"
        f"推荐场景：{preset.recommended_for}\n"
        f"执行说明：{preset.support_note}\n"
        f"来源：{preset.source_url}\n"
    )


def build_recommendation_text() -> str:
    return (
        "推荐搭配：\n"
        "1. 默认技能开发：OpenAI GPT-5.4\n"
        "2. 复杂联动 / 最终收口：OpenAI GPT-5.4 Pro 或 Claude Opus 4.1\n"
        "3. 大量代码阅读 / 长上下文：Gemini 2.5 Pro\n"
        "4. 代码推进 / 重构：GPT-5.3-Codex\n"
        "5. 快速试错：GPT-5.3-Codex-Spark\n"
        "6. 性价比日常开发：DeepSeek Chat\n"
        "7. 逻辑拆解 / 复盘：DeepSeek Reasoner\n"
        "8. 工具联动 / 探索式推进：Grok 4.20\n"
        "9. 本地内网：Ollama / LM Studio + 你本地实际模型名\n"
    )
