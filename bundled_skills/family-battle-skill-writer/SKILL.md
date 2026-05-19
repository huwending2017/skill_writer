---
name: family-battle-skill-writer
description: Use this skill when you are given battle skill descriptions, buff requirements, action requirements, linked-skill requirements, cross-skill dependency requirements, or war-report/statistics requirements for a repo that contains `xgame_server/service/battle`. It auto-locates the current battle server in the active workspace, decomposes trigger timing and dependency chains, handles multi-skill and multi-buff interactions, generates temporary config structures for testing, drafts the needed Lua scripts, and validates trigger, conflict, report, and statistics behavior without modifying formal Excel-exported config tables.
---

# Family Battle Skill Writer

## Scope

This is a global skill for any workspace that contains a battle server with this shape:

- `<repo_root>/xgame_server/service/battle`

Use it when the user provides any of the following:

- a natural-language skill description
- multiple independent skill descriptions that should be developed in one batch but not linked together
- multiple linked skill descriptions that must be designed and implemented together
- a new mechanism that must iterate or patch an already generated skill, buff, action, payload, or task folder
- a new buff behavior
- a new action effect
- a linked skill, dependent skill, passive enhancer, or external buff influence
- a war-paper or statistics requirement tied to a skill
- a request to turn design text into config structure plus Lua scripts

Quick input template:

- `references/usage_template.md`
  Use this when the user wants a ready-to-fill prompt template for single-skill, independent batch, linked bundle, existing-skill iteration, or fast-path generation.
- `references/excel_payload_template.json`
  Use this when the user also wants the generated temp config to be writable back into Excel through a structured payload.

## Repository Resolution

Before doing any battle work, resolve these two paths from the current workspace:

- `<repo_root>`
  The current repository root that contains `xgame_server/service/battle`
- `<battle_root>`
  `<repo_root>/xgame_server/service/battle`

Resolution rule:

1. Search the current workspace for `xgame_server/service/battle`.
2. If only one match exists, use it.
3. If multiple matches exist, prefer the one nearest to the current working directory.
4. If the nearest match is still ambiguous, tell the user which candidate you are using.

After resolution, all repo-local file references in this skill should be interpreted relative to `<battle_root>`, not to any hardcoded machine path.

## Guide Fallback Rule

Preferred reference order:

1. `<battle_root>/SKILL_DEV_GUIDE.md`
2. `references/battle_mechanism_catalog.md`
3. `references/battle_action_catalog.md`
4. `references/battle_state_key_catalog.md`
5. `references/battle_event_reuse_map.md`
6. direct code inspection under `<battle_root>/module/`

If `<battle_root>/SKILL_DEV_GUIDE.md` exists:

- read it first
- use it as the primary battle-flow explanation
- still verify concrete reuse points in code before implementing

If `<battle_root>/SKILL_DEV_GUIDE.md` does not exist:

- do not stop
- fall back to the reference catalogs in this skill
- inspect the core runtime files directly
- reconstruct the needed event flow, buff lifecycle, and action flow from code

Missing-guide fallback must still cover:

- actor order flow
- skill stage execution flow
- buff event registration and execution
- damage and cure paths
- war-report insertion points
- statistic update paths

## Battle Knowledge Cache Mode

This skill should not behave as "re-read the whole battle engine on every request" once the battle runtime has already been summarized.

The cache is repo-local, not account-local. Switching Codex login method, API key, or model profile must not force a full rescan when the files below are still present and fresh. Prefer the existing `<battle_root>/SKILL_DEV_GUIDE.md`, knowledge index, task folder, payload, and generated Lua artifacts before doing broad exploration again.

Primary cache layers, in order:

1. `<battle_root>/SKILL_DEV_GUIDE.md`
   Treat this as the first-party battle knowledge cache for this repo.
2. `<battle_root>/temp_skill_workspace/_global/_battle_knowledge_cache/battle_knowledge_index.json`
   Machine-readable action/buff capability index. Use `lookups.by_capability`, `lookups.by_event`, `lookups.by_state_key`, `lookups.by_extern_key`, and `lookups.by_keyword` to shortlist reusable files.
3. `<battle_root>/temp_skill_workspace/_global/_battle_knowledge_cache/battle_knowledge_index.md`
   Human-readable quick lookup grouped by capability, event, state key, extern payload, and family hint.
4. `references/battle_mechanism_catalog.md`
5. `references/battle_action_catalog.md`
6. `references/battle_state_key_catalog.md`
7. `references/battle_event_reuse_map.md`
8. targeted code reads for the exact mechanic being touched

Default behavior after the first full梳理:

- read the guide and the knowledge index first
- assume the global runtime flow is already known from the guide
- shortlist candidate actions/buffs from the knowledge index lookup sections before reading code
- do not re-read every core runtime file unless one of the refresh conditions below is hit
- only inspect the exact producer, consumer, transport, lifecycle, and report/stat files relevant to the current mechanic

Refresh the cache only when at least one of these is true:

- `<battle_root>/SKILL_DEV_GUIDE.md` is missing
- the knowledge index is missing
- the knowledge index is older than any file under `module/actions_new/`, `module/buffs_new/`, or the core runtime file set
- the request touches a mechanism not covered by the guide or catalogs
- a core runtime file changed after the guide was last updated
- the user explicitly asks for a full re-audit
- the current implementation result suggests the guide is stale or incomplete

Core files for staleness check:

- `<battle_root>/module/object/actor.lua`
- `<battle_root>/module/fight/skill.lua`
- `<battle_root>/module/fight/buff.lua`
- `<battle_root>/module/fight/action.lua`
- `<battle_root>/module/fight/damage.lua`
- `<battle_root>/module/scene/battle_scene.lua`
- `<battle_root>/module/battle_def.lua`

When cache refresh is not required:

- do not do a full-engine audit
- do not bulk-read `module/buffs_new/` or `module/actions_new/`
- use the knowledge index to shortlist concrete candidate files
- only inspect the concrete files matched by the current reuse audit

When cache refresh is required:

- rebuild the knowledge index with `scripts/build_battle_knowledge_index.py`
- re-read the changed core files
- update `<battle_root>/SKILL_DEV_GUIDE.md` if the battle flow understanding changed materially
- update the catalogs only for newly confirmed reusable mechanisms or event contracts

## Search Policy

Before writing code:

1. Resolve `<battle_root>`.
2. Read `<battle_root>/SKILL_DEV_GUIDE.md` if it exists and treat it as the default runtime summary.
3. Check whether cache refresh is required under `Battle Knowledge Cache Mode`.
   If the knowledge index is missing or stale, rebuild it with:
   `python <skill_dir>/scripts/build_battle_knowledge_index.py --battle-root <battle_root>`
4. Prefer `mcp__fast_context__fast_context_search` for exploratory search and call-chain discovery.
5. If `fast_context_search` is unavailable, fall back to `rg` plus direct file reads. Do not guess code locations.
6. Read `references/battle_mechanism_catalog.md` before deciding to add any new script.
7. Read `references/battle_action_catalog.md` before deciding to add any new action script.
8. Read `references/battle_state_key_catalog.md` when the design might use `customized_buff_state`.
9. Read `references/battle_event_reuse_map.md` when choosing the listener event for a new or reused buff.
10. Query the knowledge index to shortlist candidate `action` / `buff` files.
   Use this order:
   - `lookups.by_capability` for broad behavior such as damage, cure, add_buff, launch_chance, state_provider, round_listener, or followup.
   - `lookups.by_event` when the timing is already known.
   - `lookups.by_state_key` when the design is a linked-skill/provider-consumer problem.
   - `lookups.by_extern_key` when the effect mutates the current payload.
   - `lookups.by_keyword` for literal design words or filename-like hints.
11. Read only the exact existing files that match the mechanic before deciding whether to reuse or add code.
12. If the index is too coarse for the current design, improve the index extraction rules after validating the missing reusable pattern.
13. If a matched production script already implements the canonical consumer/provider shape, treat it as the primary design pattern. Generate config/state providers around it instead of cloning the consumer.
14. When a production script is reused unchanged, state "no net production Lua change" explicitly. When it is patched, verify the real diff before claiming a code change.

Only inspect all core runtime files when one of these is true:

- `<battle_root>/SKILL_DEV_GUIDE.md` is missing
- the guide is stale against changed core runtime files
- the user explicitly asks for a full runtime audit
- the requested mechanic cannot be mapped confidently from the guide plus catalogs

If none of the above is true, do not force a full read of:

- `<battle_root>/module/object/actor.lua`
- `<battle_root>/module/fight/skill.lua`
- `<battle_root>/module/fight/buff.lua`
- `<battle_root>/module/fight/action.lua`
- `<battle_root>/module/fight/damage.lua`
- `<battle_root>/module/scene/battle_scene.lua`
- `<battle_root>/module/battle_def.lua`

Inspect these folders as needed:

- `<battle_root>/module/actions_new/`
- `<battle_root>/module/buffs_new/`

Useful reference patterns:

- `<battle_root>/module/buffs_new/buff_add_state.lua`
- `<battle_root>/module/buffs_new/buff_add_buffs_after_all_active.lua`
- `<battle_root>/module/buffs_new/buff_times_active_skill_launch_rate.lua`
- `<battle_root>/module/buffs_new/buff_fearless_love.lua`
- `<battle_root>/module/buffs_new/buff_extend_after_control.lua`
- `<battle_root>/module/buffs_new/buff_ks_2.lua`

Temporary workspace root:

- `<battle_root>/temp_skill_workspace/`

## Mandatory Rules

- Follow the real battle flow in the repo. Do not invent a parallel skill framework.
- Reuse existing `action` / `buff` / event / report / stat entry points whenever possible.
- Reuse existing `action` / `buff` / helper / state-provider patterns before writing any new script.
- For simple static attribute or damage modifiers, especially per-stack effects like "each layer increases weapon damage by X%" or "each layer reduces received damage by Y%", try `buff_add_attr.lua` / `buff_add_attr_p.lua` configuration first. Do not create a new damage listener script unless the effect cannot be expressed by battle attributes.
- For overlying stack buffs, remember that `buff_add_attr.lua` can add one copy of configured attributes on each new layer and subtract `script.overlying` copies on removal. This makes it the preferred solution for visible stack buffs that only carry static per-layer attributes.
- Treat command/passive/equipment resident buffs as temporarily disable-able. Skills such as `buff_lost_mind.lua`, `buff_lost_self.lua`, immune-control, and equipment-break flows may call `uninit_script(buff, true)`, set `work_state` to `LOSE`, and later call `init_script(buff, true)` after restoring `WORK`.
- Any production buff or action that has persistent runtime state, event listeners, overlying layers, or applied attributes must handle temporary disable and restore symmetrically. Do not clear long-lived actor state or listener bookkeeping during temporary shut-work unless the buff is truly ending.
- When `init_script(script, is_shut_work, is_cover)` is called with `is_shut_work == true`, restore exactly the state that `uninit_script(..., true)` removed. First verify how the existing carrier already restores. Do not modify broad shared scripts such as `buff_add_attr.lua` or `buff_add_buff.lua` for one skill's edge case; prefer a skill-local compensation, a dedicated buff script, or a config-level carrier change.
- When `uninit_script` is used by both real removal and temporary invalidation, distinguish them with the runtime convention: after `set_work_state(WROK_STATE_DEF.LOSE)`, `script:is_work_state()` is false. Temporary invalidation should pause behavior and keep reusable runtime state; real lifecycle end should clean the actor-level state.
- After generating or changing a command/passive/equipment resident buff, test or reason through both normal execution and temporary invalidation recovery: applied attrs, `customized_buff_state`, event listeners, stack counts, war reports, and statistic side effects must all recover consistently.
- When generating new Lua skill scripts, detailed Chinese comments are mandatory, not optional.
- A new production `action_*.lua` or `buff_*.lua` must include Chinese comments for the file purpose, config parameter meaning, trigger event timing, state read/write lifecycle, key branch purpose, exception guard logic, damage/cure/stat path, and war-report insertion point.
- Comments must explain both "what this code does" and "why this branch exists" when the branch is related to battle timing, buff conflict, linked-skill dependency, cleanup order, report order, or statistic correctness.
- Do not leave large blocks of non-trivial Lua as bare logic. A reviewer should be able to read the production script top-down and understand the mechanism without opening the temporary test fixture.
- Before claiming a generated skill is ready, run the local artifact audit. The audit should fail task-owned production Lua that has too few Chinese comments or lacks parameter/event/report explanations.
- Never modify formal Excel-exported config tables just for development or testing.
- For testing, create temporary config files or isolated test fixtures instead of editing generated production config.
- Place all generated temporary config, test, and note files inside a dedicated subfolder under `<battle_root>/temp_skill_workspace/`.
- Do not place new temporary config files directly in `<battle_root>/`.
- Production Lua scripts must be self-contained against the real battle runtime. Do not make a production `action` or `buff` depend on helpers that only exist in `test_skill_temp.lua`, temporary fixtures, or `temp_skill_workspace`.
- Test fixtures may mock only real runtime APIs that exist in the repo. For example, mock `scene:num_random(...)` if the real scene provides it, but never invent `scene:roll_skill_dice(...)` and then call that invented API from production code.
- Before claiming a generated skill is ready, scan the production Lua output for temporary-only references such as `test_skill_temp`, `temp_skill_workspace`, `roll_skill_dice`, or fixture-specific helpers. If any are found, move the logic into the production script or replace the call with a real runtime API.
- Do not modify any file the user marked as protected.
- If a user says a running implementation file must not be used as a reference, avoid using it as the design basis and only compare behavior if explicitly asked.
- When a mechanic depends on another skill or buff, model the dependency explicitly. Do not silently fold it into one script if the runtime actually treats it as multiple parts.
- A new script is only allowed after a failed reuse audit proves the existing `action`, `buff`, `buff_add_state`, `script.extern` mutation, and config composition patterns cannot express the requirement cleanly.
- When a new reusable mechanism is added, update the mechanism catalog after implementation so later invocations can discover it quickly.
- When an existing production implementation is judged mature, update the mechanism or state-key catalog with its reusable method. Do not leave that knowledge only in the current conversation.
- After adding or materially changing any reusable production `BUFF` or `ACTION`, update the skill knowledge base before final response. This includes the relevant reference catalog and the generated battle knowledge index when the changed script affects capabilities, events, state keys, extern payloads, config slots, or reuse routing.
- The `skill_writer` bundled copy is the source of truth for this skill. Do not update only `%USERPROFILE%\.codex\skills\family-battle-skill-writer`; apply skill-rule/catalog/script changes to `G:\skill_writer\bundled_skills\family-battle-skill-writer` first, then sync to the Codex runtime directory.
- For linked-skill bundles, prefer one stable consumer script plus provider-only buffs/actions. A dependent skill that only changes an existing resident buff should usually use `buff_add_state.lua` and a documented `customized_buff_state` key.
- Do not let temporary tests define production architecture. If the generated production Lua only works because `test_skill_temp.lua` contains a helper, move the logic into the production script or replace it with a real runtime API.

## Generic Dependency Rule

Do not pre-classify the request as "tactic-book affects self skill", "passive affects active", or any other fixed category before analysis.

Default mental model:

- mechanism A may affect mechanism B

Where A and B can each be:

- a skill
- a buff
- a direct-stage action
- a resident listener buff
- a state provider
- a payload modifier

Valid dependency examples:

- skill A affects skill B
- buff A affects skill B
- skill A affects buff B
- buff A affects buff B
- skill A writes state and buff B reads it
- buff A writes state and action B reads it
- buff A modifies payload and downstream skill or buff B consumes it

Required rule:

- always identify the dependency relationship first
- only identify the concrete skill category after the dependency chain is clear

Implementation order:

1. identify producer
2. identify consumer
3. identify transport
   Transport means direct config composition, `customized_buff_state`, `script.extern`, shared event chain, or existing helper path.
4. identify lifecycle
5. identify whether existing mechanisms already cover the producer-consumer pair

Never reject a reuse path only because the producer skill and consumer skill belong to different gameplay labels.

## Real Runtime Model

Do not think in terms of "one skill script does everything".

The real runtime is a composition of:

- `data_skill`
- `data_skill_stage`
- `data_buff`
- `action_xxx.lua`
- `buff_xxx.lua`
- event payloads in `script.extern`
- actor-side persistent state in `customized_buff_state`
- war-paper records and statistic updates

Typical composition modes:

- direct cast stage -> `action`
- stage applies resident buff -> resident buff listens on events
- support buff writes actor state -> another action or buff reads that state later
- earlier buff mutates `script.extern` -> downstream cast/damage/cure logic changes
- buff listens on self
- buff registers extra listeners on allies or enemies through `script:add_event(target, EVENT_DEF.xxx)`

## Multi-Skill Request Mode

When the user provides multiple skill descriptions at once, classify the request before designing:

- **Independent batch**: multiple skills are provided for convenience, but the descriptions do not say that they affect, depend on, listen to, enhance, consume, or modify each other.
- **Linked bundle**: one skill, buff, state, or action changes another skill's trigger, probability, target, stack, damage, lifecycle, report, or config behavior.

If the tool prompt says `单技能` or `多个互不关联的独立技能`, default to **independent batch** unless the descriptions explicitly contain cross-skill dependency language.

### Independent Batch Mode

For an independent batch:

1. Split the input into separate skill requests.
2. Create one work lane per skill with disjoint config/script ownership.
3. When the execution environment supports parallel work, run reuse audit, targeted implementation, and per-skill tests for those independent lanes in parallel.
4. Reuse the same existing generic action/buff mechanisms where appropriate, but do not introduce cross-skill runtime state or dependency chains between independent skills.
5. Keep artifacts in one batch temp folder for review and cleanup, unless the user explicitly requests separate folders.
6. Generate one merged `temp_excel_payload.json` that contains all independent skills, stages, buffs, and war-paper rows only after the lanes are individually ready.
7. Run a final batch-level merge check before Excel preview: id collision, buff/action name collision, payload row ordering, report-id collision, and generated-file overwrite risk.
8. Test each skill independently and report each skill's result separately; then run one final summary validation for the merged batch payload.
9. If one skill fails or needs clarification, isolate that failure instead of blocking unrelated skills that can be completed safely.

### Linked Bundle Mode

When the request is a linked bundle, treat the provided descriptions as one dependency bundle rather than separate isolated tasks.

Always do this first:

1. Separate direct effect skills, provider skills, consumer skills, passive enhancements, and cross-trigger skill pieces.
2. Build a shared dependency graph across all provided descriptions.
3. Identify shared mechanisms that should be reused by multiple skills in the bundle.
4. Decide whether one mechanism is only a state provider for another.
5. Minimize the number of new scripts across the whole bundle, not per skill.

Bundle-level goals:

- prefer one shared reusable mechanism over multiple nearly identical new scripts
- prefer one state provider buff plus config differences over multiple custom buffs
- prefer existing readers and writers if the mechanism already exists
- make sure all linked skills are tested together, not only separately
- keep all bundle artifacts in one dedicated temp folder so they can be reviewed and cleaned up together

## Temporary Folder Convention

Every concrete implementation request must create or use one dedicated temp folder under:

- `<battle_root>/temp_skill_workspace/`

Recommended folder name:

- `<skill_id_or_bundle_name>_<short_topic>`

Examples:

- `52321_echo_of_fate`
- `liubang_bundle_active_followup`

Put all temporary artifacts for that request into the same folder:

- `config/temp_skill_config.lua`
- `config/temp_excel_payload.json`
- `tests/test_skill_temp.lua`
- `docs/IMPLEMENTATION.md`
- any temporary war-paper injection helper or supporting fixture

If multiple independent skills are developed together, they may share one batch folder and one payload, but their runtime logic must remain independent. If multiple linked skills are developed together, they must share one bundle folder unless there is a strong reason to split them.

## Resume And Repair Mode

When the user reports a problem after a generated skill is finished, treat the request as a continuation of that skill task when history, task folder, payload, or session metadata is available.

Repair flow:

1. Reuse the original temp folder, `temp_excel_payload.json`, generated Lua, tests, and implementation notes.
2. Read the user's battle log, screenshot description, or repro notes first.
3. Check whether the problem is caused by config values, generated levels, Excel writeback, or row ordering before changing production Lua.
4. If config is not the cause, inspect only the relevant BUFF/ACTION implementation and its direct producer/consumer chain.
5. Make the smallest repair and keep the existing task artifacts updated.

Do not restart from a full-engine scan in repair mode unless the cached guide or index is missing/stale, or the bug proves the cache is materially wrong.

## Existing Skill Iteration Mode

Use this mode when the user says a new skill, buff, configuration, or mechanism will affect a previously developed skill, or when the description names an existing production script such as `buff_xxx.lua`, `action_xxx.lua`, an old `temp_excel_payload.json`, or a prior `temp_skill_workspace/<task>` folder that must be iterated.

This is different from new linked-bundle development:

- The old skill already exists and must remain backward-compatible when the new mechanism is absent.
- The first task is to understand the old implementation and its generated config, not to design a replacement.
- The output is a minimal iteration plan plus targeted code/config changes.

Iteration flow:

1. Read the exact existing script, payload, implementation notes, and tests named by the user.
2. If the user only gives a skill name/id, search narrowly in `temp_skill_workspace`, `module/actions_new`, and `module/buffs_new` before opening broad code.
3. Summarize the old skill's current trigger, state, config, report, and statistics behavior.
4. Identify the new mechanism's entry point and the exact old behavior it changes.
5. Prefer a provider-state design (`buff_add_state`, `customized_buff_state`, `script.extern`, or an existing state key) over duplicating old listeners or rewriting the old skill.
6. Patch the old production script only where the new mechanism must be consumed; keep unrelated branches, report ids, statistics, and cleanup behavior unchanged.
7. Update `temp_excel_payload.json` only for new rows and rows whose behavior actually changed.
8. Test both modes: old skill without the new mechanism, and old skill with the new mechanism active.
9. Document whether the iteration should happen in the old task folder or in a new `<old_skill>_iteration_<topic>` folder.

Do not treat iteration mode as ordinary repair unless the user reports a bug. Do not treat it as ordinary bundle mode unless the old skill is not already implemented.

## Excel Writeback Support

When the user wants temporary config to be written back into the original Excel workbooks, do not rely on ad-hoc manual copy.

Preferred flow:

1. Generate the normal temporary Lua config for battle testing.
2. Generate `temp_excel_payload.json` in the same temp folder.
3. Write Excel through `scripts/write_temp_skill_excel.py`.
4. Prefer writing into workbook copies first or creating backups before touching the real workbook path.

The writeback payload should target:

- skill workbook
  Usually the workbook that owns sheets such as `skill`, `skill_stage`, and `buff`
- war-paper workbook
  Usually the workbook that owns sheet `war_paper`

Rules:

- workbook paths must stay configurable and must not be hardcoded to one project forever
- `skill` / `skill_stage` / `buff` rows should use Lua-side runtime field names where possible
- if the design text states an explicit skill level or maximum skill level `n` (`技能等级:n`, `最大等级:n`, `满级:n`, or equivalent), generate rows for levels `0..n`
- if no explicit level is stated, use the skill category as the default level range: `技能类别:自带` generates `0..10`, while `技能类别:兵书` and `技能类别:装备` generate `0..1`
- `skill_stage` rows follow the owning skill's maximum level
- `buff` rows should use explicit `max_lv` when the payload provides it; otherwise follow the same explicit-level/category rule when the payload carries `skill_category`, `category`, `source_type`, `skill_source`, `skill_kind`, or `kind`; if none is available, default to levels `0..10`
- for `skill`, `skill_stage`, and `buff`, writeback should keep each generated level group contiguous and insert the new id group after the nearest lower id group, such as inserting `30322` immediately after the last level row of `30321` when it exists
- `war_paper` rows should use Excel-side row fields directly
- nested arrays should be serialized into Excel-friendly comma or pipe formats
- the skill should always show the user the generated payload path and the exact writeback command

## Linked Skill And External Buff Analysis

For every request, build a dependency map first.

At minimum, decide whether the mechanic uses any of these:

1. Self-contained effect
2. Resident listener buff
3. External state provider
   Example shape: `buff_add_state.lua` writes to `owner.customized_buff_state`
4. External state consumer
   Example shape: `buff_echo_of_fate.lua` reads `attacker.customized_buff_state`
5. Event payload modifier
   Example shape: buffs that modify `script.extern.add_chance`, `script.extern.damage`, `script.extern.target`, `script.extern.cure_val`
6. Cross-skill trigger
   Example shape: one active skill success triggers another buff or recast
7. Cross-buff lifecycle dependency
   Example shape: add buff, immune buff, remove buff, extend life, refresh, overlying, disable by immune

When one mechanism is influenced by another mechanism, always answer these:

1. Who produces the state or trigger
2. Where that state is stored
3. Who consumes it
4. What happens when the producer is absent
5. What happens when the producer buff expires or is removed
6. Whether the dependency must appear in battle report

Also answer these when the user gives multiple descriptions:

1. Which descriptions are only config-level variants of the same mechanism
2. Which descriptions can share one resident buff or one helper pattern
3. Which descriptions must stay split because their trigger timing or lifecycle differs

## Reuse Audit

Before adding any new script, run this audit explicitly and report the result.

1. Existing action audit
   Can `data_skill_stage + existing action` already express the direct effect
2. Existing listener buff audit
   Is there already a buff that triggers on the same event and performs the same shape of work
3. Existing state-provider audit
   Can this be expressed by adding `buff_add_state` or an existing state-writing buff
4. Existing state-consumer audit
   Is there already a consumer buff or action that reads the same state key
5. Existing payload-mutation audit
   Can the effect be achieved by modifying `script.extern.add_chance`, `script.extern.damage`, `script.extern.cure_val`, `script.extern.target`, `script.extern.target_list`, or `script.extern.skill_info`
6. Existing attribute/config audit
   Can static flat/percent attributes, weapon damage increase, weapon/intellect received damage reduction, or per-stack visible attributes be expressed with `buff_add_attr.lua`, `buff_add_attr_p.lua`, `action_add_attr.lua`, or existing `data_attr_id` fields
7. Existing lifecycle audit
   Can add/remove/refresh/immune/extend behavior be achieved by existing buff types and add-type rules

Only after all seven checks fail should you add a new script.

When the answer is "reuse exists", prefer:

- config only
- temp config plus existing scripts
- one extra state-provider buff with existing consumer
- existing action with different stage params

over:

- new buff script
- new action script
- duplicated scripts that differ only by parameters

## Indexed Reuse Gate

The knowledge index is not a replacement for code verification. It is the routing layer that prevents unnecessary full scans and prevents low-confidence duplicate scripts.

Required flow before any new script is allowed:

1. Query the knowledge index for candidate `action` files by:
   - trigger shape
   - effect tags
   - event usage
   - `script.extern` keys
   - report/stat helper usage
2. Query the knowledge index for candidate `buff` files by:
   - listener event
   - effect tags
   - `customized_buff_state` keys
   - `script.extern` keys
   - lifecycle tags such as refresh, stack, immune, remove
3. Select a short candidate set, not the whole directory.
4. Read the exact candidate files plus the minimal producer/consumer runtime files needed to verify fit.
5. For every rejected candidate, state the concrete mismatch.

Allowed rejection reasons:

- wrong trigger timing
- wrong carrier
- wrong transport
- wrong target selection timing
- wrong lifecycle or add-type behavior
- wrong report/stat side effects
- only partially reusable and would still require more invasive change than a new script

Not allowed as a rejection reason:

- "did not know the file existed"
- "index summary was unclear" without opening the candidate file
- "probably not suitable" without naming the mismatch

New script rule:

- if the index returns plausible candidates, at least the top candidate files must be opened and checked before writing new code
- if the index returns no plausible candidates, you may proceed to targeted fallback search
- only after indexed candidates and targeted fallback search both fail may a new script be introduced

## Implementation Heuristics

Choose the implementation path by effect shape:

- Immediate one-shot effect during cast: prefer `action`.
- Ongoing effect across rounds: prefer `buff`.
- Event-driven follow-up after cast/base attack/hit/control/death: prefer `buff` bound to the matching event.
- Target replacement, cast chance adjustment, prepare interruption, recast, cooldown bypass, follow-up triggers: locate the exact event hook in the battle guide first, then implement through the existing event flow.
- If the effect exists only because another mechanism is present, first check whether it should be `customized_buff_state`, `script.extern` mutation, or an additional listener buff.

Always decide these items explicitly:

1. Trigger timing
2. Carrier
   Carrier means skill stage action, applied buff, passive buff, external state provider, or existing reusable component.
3. Target selection timing
4. Damage/cure/control/stat/report side effects
5. Whether the effect must be visible in battle report
6. Whether it depends on another mechanism being present

Prefer these existing implementation families before inventing a new one:

- direct stage actions: see `references/battle_action_catalog.md`
- state provider: `buff_add_state.lua`
- post-active follow-up add buff: `buff_add_buff_after_active.lua`, `buff_add_buffs_after_all_active.lua`
- chance modifiers: `buff_active_skill_launch_rate.lua`, `buff_times_active_skill_launch_rate.lua`, related launch-rate buffs
- damage modifiers: `buff_active_skill_harm_rate.lua`, `buff_assault_skill_harm_rate.lua`, `buff_normal_attack_harm_rate.lua`, related harm-rate buffs
- target rewrite or inherited target: `buff_lock.lua`, buffs reading `script.extern.target` or `script.extern.target_list`
- recast / extra cast / cooldown path: `buff_fearless_love.lua`, `buff_jisu.lua`, `buff_ml_1.lua`, `buff_stunt_arl.lua`
- add-on after control or add-buff lifecycle: `buff_extend_after_control.lua`, `buff_ks_2.lua`, related `BUFF_ADD_START` / `BUFF_IMMUGE_SUCCESS` listeners
- persistent keyed state: `customized_buff_state` writers and readers such as `buff_add_state.lua` and `buff_echo_of_fate.lua`

## Multi-Buff And Conflict Checklist

Before coding, check all of these:

- `data_buff.add_type`
  Check whether the buff is `COVER`, `LIFE`, `LOSE`, `OVERLYING`, `LIFE_OVERLYING`, or `ALONE`.
- `add_max`
  Check max stack and whether hitting cap should still show battle report.
- `type` and `type_id`
  Check whether the buff participates in control, attribute, dot, or custom conflict logic.
- `is_dispel`
  Check whether removal or cleanse can affect it.
- `is_dead_clear`
  Check whether attacker death or owner death should invalidate it.
- immune control / immune buff flow
  Check `BUFF_ADD_START`, `BUFF_IMMUGE_SUCCESS`, shut-work-by-immune, and restore-on-order-start behavior.
- refresh and cover behavior
  `cover()` resets some runtime data, so confirm whether custom counters must be preserved or reset.
- overlying behavior
  If the buff uses layers, verify `init_script` on each new layer and layer cap behavior.
- removal chaining
  If a buff removal can affect current trigger skill, ensure battle report effect lists are still inserted correctly.
- dead target / dead attacker
  Many scripts guard with `target:is_dead()` and `attacker:is_dead()`. Preserve that behavior.
- empty target set
  Decide whether this is silent no-op or should generate fail/no-effect records.
- config table mutation
  Clone config slices before modifying them at runtime if the value is only a temporary computed variant.

## `script.extern` And `customized_buff_state`

Treat these as first-class design choices.

Use `script.extern` when:

- the change only matters inside the current event chain
- a buff needs to modify the ongoing cast, damage, cure, or targeting payload
- the change should disappear after the current event finishes

Use `customized_buff_state` when:

- a buff needs to expose persistent state to later actions or later turns
- another skill or buff reads that state outside the current event payload
- the effect is logically "a runtime switch", "special mode", "stored parameter", or "conditional enhancement"

When using either one, always define:

1. Writer
2. Reader
3. Lifetime
4. Reset point
5. Missing-state fallback
6. Removal behavior

## War Report And Statistic Rules

Do not hand-wave battle report.

For every new mechanic, explicitly check:

- start record
- trigger success record
- trigger fail record if the mechanic commonly shows one
- custom record ids if the mechanic has unique textual display
- buff add / refresh / invalid / go-on / remove records
- damage or cure records
- extra trigger records such as dice roll, cooldown clear, recast, immunity success
- whether statistics already update through existing damage/cure paths

Prefer existing helpers such as:

- `make_buff_word_records`
- `make_buff_trigger_fall_records`
- `make_effect_records`
- `make_confuse_records`
- `insert_effect_list`
- actor-side `insert_statistic`

If the mechanic needs a custom war-paper entry, add it only in the temporary config path for testing.

## Output Contract

When this skill is invoked for a concrete request, produce the following in order:

1. Skill decomposition card
   Include trigger timing, source actor, target rules, probability rules, scaling rules, duration, stacking, and report/stat requirements.
2. Dependency graph
   State the producer and consumer chain for linked skills, linked buffs, cross-mechanism effects, `script.extern`, and `customized_buff_state`.
3. Reuse audit result
   State which existing `action` / `buff` / state-provider / payload-mutation path can be reused, what can be solved by config only, what candidate files were checked from the knowledge index, why rejected candidates do not fit, and what truly requires new code.
4. Event contract
   State the exact event names and the payload fields that will be read or modified.
5. Multi-skill implementation map
   If multiple independent skills were provided, list each skill separately and state that no runtime dependency is introduced. If linked skills were provided, state shared mechanisms, per-skill config differences, dependency order, and shared tests.
6. Temporary config plan
   Provide the temporary config structure needed for testing, including skill, stage, buff, and war-paper/stat-related items if applicable, and specify the temp folder path.
7. Script implementation
   Draft or implement the required `action_xxx.lua` / `buff_xxx.lua` and any minimal supporting code. New scripts must include detailed Chinese comments, ideally aligned to the runtime steps.
8. Risk and exception list
   Call out immune, refresh, cover, stack cap, dead target, empty target, removal-order, and report-order risks.
9. Validation plan
   Verify trigger timing, dependency behavior, conflict behavior, target count, probability gates, buff lifecycle, damage/cure/control results, battle report behavior, and statistics hooks.
10. Knowledge-base update
   If a new reusable mechanism was added, update the mechanism catalog and mention the new entry.
11. Bundled skill sync
   If the implementation added or materially changed a reusable `BUFF` / `ACTION`, update the `skill_writer` bundled skill first, then sync it to the Codex runtime skill directory before final response.

## Development Checklist

For each new request, walk through this checklist:

1. Parse the description into atomic effects.
2. Decide whether the request is new skill work, independent batch work, linked bundle work, repair mode, or existing-skill iteration mode.
3. Group effects by shared reusable mechanism only when that does not create unintended cross-skill runtime coupling.
4. Separate self-contained effects from dependent effects.
5. Decide whether the guide plus catalogs already cover the current mechanic or whether cache refresh is required.
6. Query the knowledge index for candidate actions, buffs, state writers, state readers, and payload modifiers.
7. Run the reuse audit against those indexed candidates and targeted fallback search results.
8. Map each atomic effect to a battle event or stage execution point.
9. Determine whether each atomic effect should live in `action`, `buff`, `customized_buff_state`, `script.extern` mutation, or existing reusable logic.
10. Identify required config fields and parameter payloads.
11. Check add-type, stack, refresh, immune, removal, and death behavior.
12. Create one dedicated temp folder for the request under `<battle_root>/temp_skill_workspace/`.
13. Inside each task folder use the stable layout `config/`, `scripts/`, `tests/`, `docs/`, `repair/`, and `logs/`. Keep payload/config files in `config/`, temporary task-owned Lua drafts in `scripts/`, tests in `tests/`, implementation notes in `docs/`, and repair chat/attachments in `repair/`.
14. For mechanics involving stack counters, command-skill disable/restore, cleared stacks with persistent attributes, dispel, dead targets, first-trigger versus later-trigger behavior, or war-report values that differ from internal state, add focused regression scripts under `tests/` named `regression_*.lua` or `mechanism_*.lua`.
15. Implement with the smallest change set that fits the current framework.
14. Test with temporary config only.
15. Check battle report and statistics behavior.
16. If a new mechanism was added, record it in the mechanism catalog.
17. If a new or changed `BUFF` / `ACTION` affects reuse lookup, rebuild the battle knowledge index with `scripts/build_battle_knowledge_index.py`.
18. If skill instructions, catalogs, or helper scripts changed, edit the `skill_writer` bundled skill copy first and sync it to `%USERPROFILE%\.codex\skills`.
19. If battle-flow understanding changed materially, update `<battle_root>/SKILL_DEV_GUIDE.md`.
20. Summarize any remaining uncertainty or assumptions.

## Testing Expectations

Testing should verify at least:

- skill can be cast at the intended timing
- dependent behavior works both when the linked producer exists and when it does not
- chance modification is applied at the correct event
- target selection matches config
- buff add/remove/refresh/expire behavior is correct
- immune and invalid flows behave correctly
- max stack and cover behavior are correct
- dead target and empty target cases do not break the chain
- damage, cure, control, or attribute change matches config parameters
- battle report output is present where expected and in the correct order
- statistics are counted through existing paths rather than ad-hoc fields

If full automated execution is not available, still prepare:

- temporary config skeleton
- temporary war-paper injection if needed
- manual verification steps
- expected trigger sequence
- expected battle report checkpoints
- expected producer-on / producer-off comparison

## Output Style

Keep outputs practical and implementation-oriented.

Prefer:

- direct decomposition
- concrete config keys
- concrete script names
- exact event names
- exact module entry points
- explicit dependency and conflict notes
- Chinese inline comments in newly generated Lua scripts that make each important execution step understandable to later developers

Avoid:

- abstract design talk detached from this repo
- rewriting existing engine architecture
- pretending linked skills are single-script features
- adding dev-only logic into formal generated config tables
