# Battle Mechanism Catalog

This file is a reuse-first catalog for the resolved battle root:

- `<battle_root>`

Use it before adding any new `action_xxx.lua` or `buff_xxx.lua`.

If a new reusable mechanism is implemented later, append a new entry here.

## How To Use

For each requested skill or skill bundle:

1. Find the trigger timing.
2. Find whether the effect is direct, resident, state-based, or payload-mutation based.
3. Match the requirement against an existing family below.
4. Prefer config composition and existing scripts.
5. Add a new script only if no existing family can express the mechanic cleanly.

## Family 1: State Provider Through `customized_buff_state`

Use when one skill or buff should expose a persistent keyed state that another skill or buff reads later.

Primary reference:

- `<battle_root>/module/buffs_new/buff_add_state.lua`

Common pattern:

- provider buff writes `owner.customized_buff_state[key] = config`
- consumer buff or action checks `attacker.customized_buff_state[key]`
- provider removal clears the key in `uninit_script`

Known readers:

- `buff_echo_of_fate.lua`
- `buff_add_buffs_after_all_active.lua`
- `buff_debt.lua`
- `buff_sand_bless.lua`
- `buff_zhanbei.lua`
- `buff_qinqiong_menshen.lua`
- `buff_yuchigong_menshen.lua`

Good fit:

- one skill only adds a keyed mode or parameter for another mechanism
- one special rule changes another skill's branch, chance, extra damage, or extra buff list
- the dependent effect must survive beyond one event payload

Avoid new script if:

- the requirement is only "add a keyed parameter/state so another existing buff can read it"

## Family 2: Launch Chance Modification Through `script.extern.add_chance`

Use when the effect changes active, assault, or ready skill launch chance during the cast decision chain.

Common references:

- `buff_active_skill_launch_rate.lua`
- `buff_times_active_skill_launch_rate.lua`
- `buff_active_skill_rate_by_attr.lua`
- `buff_ready_skill_launch_rate.lua`
- `buff_assault_skill_launch_rate.lua`

Common payload:

- `script.extern.skill_info`
- `script.extern.add_chance`

Good fit:

- increase or decrease launch chance
- conditional chance change based on attr, hp, count, or skill family

Avoid new script if:

- the only difference is chance formula or count cap

## Family 3: Damage Modification Through `script.extern.damage`

Use when the effect modifies damage in the current damage chain.

Common references:

- `buff_active_skill_harm_rate.lua`
- `buff_assault_skill_harm_rate.lua`
- `buff_normal_attack_harm_rate.lua`
- `buff_times_harm_rate.lua`
- `buff_state_change_harm.lua`

Common payload:

- `script.extern.skill`
- `script.extern.damage`

Good fit:

- active damage up/down
- assault damage up/down
- normal attack damage up/down
- conditional damage modification by hp, target state, count, or attr

Avoid new script if:

- the effect is still "multiply or add damage under an existing condition family"

## Family 4: Cure Modification Through `script.extern.cure_val`

Use when the effect modifies treatment amount in the current cure chain.

Common references:

- `buff_cure_effect.lua`
- `buff_diaochan.lua`
- `buff_add_attr.lua`

Common payload:

- `script.extern.skill`
- `script.extern.cure_val`
- `script.extern.extar_cure_val`
- `script.extern.continue`

Good fit:

- cure increase or reduce
- cure reversal or cancel
- cure converts into another effect

## Family 5: Target Rewrite Or Target Reuse

Use when the effect changes or consumes selected targets.

Common references:

- `buff_lock.lua`
- `buff_find_flaw.lua`
- buffs reading `script.extern.target`
- buffs reading `script.extern.target_list`

Common payload:

- `script.extern.target`
- `script.extern.target_list`

Good fit:

- lock target
- inherit original target
- use last target list for add-buff follow-up

## Family 6: Post-Trigger Add Buff Follow-Up

Use when a skill or buff should add another buff after active, assault, attack, aoe, harm, or control events.

Common references:

- `buff_add_buff_after_active.lua`
- `buff_add_buffs_after_all_active.lua`
- `buff_add_buff_after_assault.lua`
- `buff_add_buff_after_attack.lua`
- `buff_add_buff_after_harm.lua`
- `buff_add_buff_after_control.lua`

Good fit:

- "after ally active skill succeeds, add buff"
- "after dealing damage, add control or attribute buff"
- "after target gets debuffed, attach follow-up effect"

Avoid new script if:

- the requested mechanic is still a standard "after event, apply buff" flow

Extended subfamilies:

- after active: `buff_add_buff_after_active.lua`, `buff_add_buff_after_byo_active.lua`
- after assault: `buff_add_buff_after_assault.lua`, `buff_round_add_buff_after_assault.lua`
- after normal attack: `buff_add_buff_after_attack.lua`, `buff_add_buff_after_attack_miss.lua`
- after aoe or damage: `buff_add_buff_after_aoe.lua`, `buff_add_buff_after_harm.lua`
- after control/debuff lifecycle: `buff_add_buff_after_control.lua`, `buff_add_buff_after_controlled.lua`, `buff_add_buff_after_debuff.lua`, `buff_add_buff_after_type_id.lua`
- round resident add-buff families: `buff_add_buff_all_round.lua`, `buff_add_buff_round.lua`, `buff_add_buff_round_chance.lua`, `buff_add_buff_round_self.lua`

## Family 7: Add-Buff Lifecycle Interception

Use when the effect reacts to buff add/remove/immune/extend timing rather than direct damage.

Common references:

- `buff_extend_after_control.lua`
- `buff_ks_2.lua`
- `buff_add_buff_after_control.lua`
- `buff_add_attr_by_double_hit.lua`

Key events:

- `BUFF_ADD_START`
- `BUFF_ADD_OVER`
- `BUFF_ADDED_OVER`
- `BUFF_IMMUGE_SUCCESS`
- `BUFF_REMOVE_OVER`

Good fit:

- control extension
- immune success follow-up
- add-buff success trigger
- remove-buff cleanup trigger

## Family 8: Recast, Extra Cast, And Cooldown Manipulation

Use when a skill can cast again, skip ready, or alter cooldown.

Common references:

- `buff_fearless_love.lua`
- `buff_jisu.lua`
- `buff_ml_1.lua`
- `buff_stunt_arl.lua`
- `buff_skip_round.lua`

Key events:

- `BUFF_CAST_SKILL_OVER_AGAIN`
- `BUFF_CAST_SKILL_FAIL`
- `BUFF_CLEAN_CD`

Good fit:

- recast active skill
- skip preparation round
- clear or alter cooldown
- cast-again with modified damage

## Family 9: Over-Time Or Resident Round Listener

Use when the effect triggers on round start, order start, round over, or resident periodic timing.

Common references:

- `buff_echo_of_fate.lua`
- `buff_add_buff_all_round.lua`
- `buff_strong_wind_and_rain.lua`

Key events:

- `BUFF_ORDER_START`
- `BUFF_ORDER_OVER`
- `BUFF_ROUND_START_RESET`
- `BATTLE_ROUND_START`
- `BATTLE_ROUND_OVER`

Good fit:

- per-round random effect
- periodic heal or damage
- round-based state reset

## Family 10: Cross-Camp Debuff Listener With Threshold Burst

Use when one resident buff must listen to enemies successfully receiving debuffs, stack a self buff, and trigger a burst once a dynamic threshold is reached.

Common references:

- `buff_fight_spirit.lua`
- `buff_ragsa_hannu_listener.lua`
- `buff_ragsa_hannu_state.lua`

Common composition:

- one resident listener buff registers `BUFF_ADDED_OVER` on enemy units
- one self overlying buff carries the visible stack count and damage modifiers
- one `customized_buff_state` key stores threshold state that must survive stack clear
- threshold burst damage is executed through the normal `buff_cal_damage(...)` path
- stack clear is done after burst damage resolves so the burst can still use the current layers

Good fit:

- "enemy gains debuff -> self gains stack"
- stack count triggers an AOE or follow-up burst
- next trigger threshold changes after each burst
- stack visual and stack math should be separated into listener and stack buffs

Common round resident families:

- round add buff: `buff_add_buff_all_round.lua`, `buff_add_buff_round.lua`, `buff_add_buff_round_self.lua`
- round cure or hybrid: `buff_add_buff_and_cure_round.lua`, `buff_round_clean_cure_all.lua`
- round attack or reflection: `buff_attack_round.lua`, `buff_attack_round_blood.lua`, `buff_attack_round_light.lua`, `buff_thorns.lua`
- round random or branch logic: `buff_echo_of_fate.lua`, `buff_strong_wind_and_rain.lua`, `buff_tyrant.lua`

## Family 10: Target Lock, Share, Guard, And Redirection

Use when the mechanic changes who receives damage, buffs, or follow-up effects.

Common references:

- `buff_lock.lua`
- `buff_guard.lua`
- `buff_share.lua`
- `buff_share_for_target.lua`
- `buff_share_off.lua`
- `buff_share_off_other.lua`
- `buff_surrender.lua`
- `buff_viiking_shield.lua`

Good fit:

- lock a target for future stages or future buff work
- guard or intercept damage for teammates
- share damage among linked targets
- redirect effect target through existing payload fields

Avoid new script if:

- the requirement is still target redirection, sharing, guarding, or locked follow-up

## Family 11: Control, Dot, And State-Application Buffs

Use when the skill mostly applies an existing status rather than inventing a new runtime mechanism.

Common references:

- control state buffs: `buff_chaos.lua`, `buff_dizzy.lua`, `buff_disarm.lua`, `buff_no_cure.lua`, `buff_silence.lua`, `buff_taunt.lua`, `buff_week.lua`, `buff_lost_mind.lua`, `buff_lost_self.lua`
- dot state buffs: `buff_dot.lua`, `buff_dot_harm.lua`, `buff_dot_real.lua`, `buff_hot.lua`
- support modifiers: `buff_dot_extend.lua`, `buff_extend_after_control.lua`, `buff_immune_control.lua`

Good fit:

- the effect is "apply existing control"
- the effect is "apply existing dot"
- the effect is "extend or react to existing control/dot"

Avoid new script if:

- the only change is chance, target count, duration, or the particular status chosen from an existing set

## Family 12: Counter, Limit, And Times-Based Mechanisms

Use when the mechanic works for a limited number of times, layers, or rounds.

Common references:

- `buff_times_active_skill_launch_rate.lua`
- `buff_times_active_skill_harm_rate.lua`
- `buff_times_assault_skill_launch_rate.lua`
- `buff_times_assault_skill_harm_rate.lua`
- `buff_times_harm_rate.lua`
- `buff_times_injured_rate.lua`
- `buff_stacking.lua`

Good fit:

- first N times
- per-round limited trigger count
- limited trigger count over buff lifetime
- layer-based effect growth or decay

Avoid new script if:

- the mechanic is still "times-limited modifier" and only differs in the trigger event or numeric formula

## Family 13: Triggered Extra Attack, Follow-Up Attack, Or Recast

Use when a trigger causes an attack, extra strike, or extra cast after another event.

Common references:

- `buff_attack_after_active_injured.lua`
- `buff_attack_after_assault.lua`
- `buff_attack_after_attack.lua`
- `buff_attack_after_target_active_skill.lua`
- `buff_attack_after_times_normal_attack.lua`
- `buff_fearless_love.lua`

Good fit:

- extra attack after another attack or skill
- triggered follow-up strike
- recast active skill
- re-entry into the cast path through an existing event

Avoid new script if:

- the mechanic is structurally a follow-up attack or recast and only differs in target rules or numeric params

## Family 14: Immune, Resist, Cancel, And No-Effect Flows

Use when the mechanic is about preventing, invalidating, resisting, or cancelling effects.

Common references:

- `buff_immune.lua`
- `buff_immune_control.lua`
- `buff_immune_after_debuff.lua`
- `buff_immune_by_type.lua`
- `buff_resist.lua`
- `buff_remove_self_by_resist.lua`
- `buff_no_harm.lua`
- `buff_no_normal_attack.lua`

Good fit:

- chance to ignore control or buff
- chance to resist damage or debuff
- cancel current effect chain
- convert trigger into fail/no-effect report

## Family 15: Attribute Buff, Attr Percent Buff, And Attr Steal

Use when the skill is fundamentally about adding, reducing, or stealing attributes.

Common references:

- `buff_add_attr.lua`
- `buff_add_attr_p.lua`
- `buff_attr_change.lua`
- `buff_steal_after_harm.lua`
- `action_add_attr.lua`
- `action_add_attr_p.lua`
- `action_steal_attr.lua`
- `action_steal_attr_general.lua`

Good fit:

- flat attr up/down
- percent attr up/down
- attr steal after hit or event
- cure/damage side paths that read changed attrs through existing combat formulas
- per-layer static damage attribute buffs, for example "each stack increases weapon damage by X%" or "each stack reduces received weapon/intellect damage by Y%"

Important reuse rule:

- Before adding a custom `BUFF_ATTACK_DAMAGE` or `BUFF_ATTACKED_DAMAGE` script for simple per-stack damage modifiers, first check whether `buff_add_attr.lua` can express the effect through battle attributes.
- `buff_add_attr.lua` is valid for overlying buffs: when an existing buff gains a layer, the runtime calls `init_script` again and the script adds one more copy of the configured attr; when the buff is removed, `uninit_script` subtracts `script.overlying` copies.
- For "each stack increases weapon damage by 4%", prefer an overlying `buff_add_attr.lua` buff configured with `data_attr_id.HARM_PHY_P = 400`.
- For "each stack reduces received weapon damage by 1%", prefer an overlying `buff_add_attr.lua` buff configured with `data_attr_id.INJURED_PHY_P = -100`.
- If the design says "received all damage", configure both `data_attr_id.INJURED_PHY_P = -100` and `data_attr_id.INJURED_INTELLECT_P = -100` in the same `buff_add_attr.lua` buff, unless fixed/real damage must also be affected.
- Temporary invalidation recovery matters for overlying attr buffs. `buff_lost_mind.lua`, `buff_lost_self.lua`, equipment-break, and immune-control style effects may call `uninit_script(buff, true)` while setting the buff to `WROK_STATE_DEF.LOSE`, then call `init_script(buff, true)` after restoring `WORK`. Before changing code, compare with a known normal skill such as 50160 and verify whether the existing carrier already restores correctly. Do not patch broad shared scripts for one generated skill; if a generated skill's carrier loses layers, fix the generated skill with local compensation, a dedicated buff script, or a config carrier change.
- Only add a custom listener damage script when the requirement needs event-local behavior that attributes cannot express, such as modifying only one current skill payload, using non-attribute conditions, inserting special custom war reports, consuming stacks on hit, or changing the modifier by target/skill at runtime.

## Family 16: Multi-Skill Bundle Design

Use when multiple linked skills are designed together and one mechanism may affect another.

Preferred pattern:

- keep the core mechanic in its primary skill or resident buff
- let dependent skills act as provider, enhancer, trigger adapter, or consumer
- if possible, let the provider side use an existing provider like `buff_add_state.lua`
- do not duplicate the same mechanism in multiple linked scripts

Bundle design checklist:

- can the dependent side be config only
- can the provider side be only `add_state`
- can both skills share one resident listener buff
- can the extra effect be expressed by existing post-event add-buff families

## Family 17: Dice Branch Resident Consumer

Use when a skill keeps one resident buff that randomly selects a branch each round, and other linked skills only modify that resident buff through state payloads.

Canonical script:

- `module/buffs_new/buff_echo_of_fate.lua`

Preferred pattern:

- keep the dice/branch execution in the canonical resident consumer buff
- let linked skills provide state through `buff_add_state.lua`
- use `customized_buff_state` keys such as `dice_damage` or `dice_diff_pre` instead of creating duplicate dice consumers
- do not add scene or skill helpers that only exist in temporary tests

Canonical flow:

1. Listen on `EVENT_DEF.BUFF_ORDER_START`.
2. Gate execution with `b_const.cal_effect(...)` and `scene:can(...)`.
3. On chance failure, emit the failure report and still insert the effect list.
4. Build a valid branch pool from the configured branch count.
5. If `dice_diff_pre` is present, exclude the previous branch before rolling.
6. Roll through real runtime random APIs only.
7. Emit the dice result through war-paper effect records.
8. Dispatch to branch functions such as `exec_effect_1`, `exec_effect_2`, and so on.
9. Inside branch functions, use existing entrances: `buff_find_targets`, `make_confuse_records`, `cal_damage`, `cure_target`, and `add_buffs_target`.
10. Update `last_effect` after a branch is selected.
11. Apply provider state such as `dice_damage` after the branch if configured.
12. Insert the accumulated effect list at the end.

Quality gates:

- The production buff must be self-contained against the real runtime.
- Branch behavior must not depend on `test_skill_temp.lua`, `temp_skill_workspace`, or invented APIs such as `roll_skill_dice`.
- Target loops must guard dead attackers or targets according to the existing script style.
- Group cure branches must call `cure_target` with the loop target when the design says each selected target is healed.
- Report order matters: trigger/failure, dice result, branch records, extra provider effects, final effect-list insert.
- If the current repository already has the same implementation, report that there is no net production Lua diff instead of implying new code was written.

## Family 18: Temporary Skill Invalidation And Restore

Use when a resident command/passive/equipment buff can be disabled by another effect and later restored.

Common references:

- `buff_lost_mind.lua`
- `buff_lost_self.lua`
- `buff_equip_broken.lua`
- `buff_immune.lua`
- `buff_immune_control.lua`
- `buff_add_attr.lua`

Runtime shape:

- invalidation side sets the target buff `work_state` to `WROK_STATE_DEF.LOSE`
- invalidation side calls `buff.script:uninit_script(buff, true)`
- restore side sets `work_state` back to `WROK_STATE_DEF.WORK`
- restore side calls `buff.script:init_script(buff, true)`
- event callbacks registered by `g_buff:add_event(...)` already ignore disabled buffs because the wrapper checks `not self:is_work_state()`

Design rules:

- Treat `is_shut_work == true` as temporary pause, not permanent removal.
- `uninit_script(..., true)` should remove or pause only the runtime effect that must disappear while disabled.
- `init_script(..., true)` must restore the exact removed effect, including all existing stack layers and listener readiness.
- Actor-level long-lived state such as `owner.customized_buff_state[key]` should usually survive temporary disable if it represents battle progress rather than the active stat effect.
- For overlying `buff_add_attr.lua`-style effects, compare the disable and restore deltas. If a specific generated skill loses layers after restore, keep broad shared scripts untouched and fix that generated skill's carrier or resident listener locally.
- For resident listener buffs, restore must ensure event listeners are present without registering duplicates. A safe pattern is to track a listener-ready flag and also check whether `script.listen_list` is empty.

Quality gates:

- Test the normal lifecycle and the temporary invalidation lifecycle separately.
- Confirm war reports show both "temporarily invalid" and "continue effective" with attributes/stacks returning to the pre-disable value.
- Confirm no old state leaks into the next battle or next real buff application after actual lifecycle end.
- Check command skills, passive skills, and equipment effects explicitly when the new buff is resident or has persistent state.

## Family 19: Resident Self-Damage Threshold Plus Ally Share Transfer Bundle

Use when one canonical resident buff must own all of the following in one runtime:

- self-side `BUFF_ATTACKED_DAMAGE` threshold judgment
- ally-side share interception through `BUFF_ATTACKED_SHARE`
- delayed transfer to the owner after the ally actually loses life through `BUFF_LOSE_LIFE`
- linked provider skills that only add extra reduction or dispel behavior
- one visible stack family and one follow-up stack family with ordered report output

Primary references:

- `module/buffs_new/buff_yuefei_jingzhong.lua`
- `module/buffs_new/buff_share.lua`
- `module/buffs_new/buff_share_for_target.lua`
- `module/buffs_new/buff_injured_by_hp.lua`
- `module/buffs_new/buff_add_state.lua`

Canonical composition:

- one resident listener buff stores long-lived runtime such as loyalty layers, lost-layer progress, follow-up stack count, one-time trigger flags, and per-target share cache
- a display-only overlying buff carries the visible self stack count when the visible stack should not itself own the full mechanic
- static per-stack gains reuse `buff_add_attr.lua` / `buff_add_attr_p.lua`
- linked skills that only add "per current stack extra reduction" or "every N lost stacks dispel once" use `buff_add_state.lua`
- the resident consumer reads provider state in real time so temporary invalidation and restore can pause and resume cleanly

Trigger ordering rules:

1. Resolve direct self damage reduction in `BUFF_ATTACKED_DAMAGE` before checking whether the same hit should consume a stack.
2. Cache ally share amount in `BUFF_ATTACKED_SHARE`, but do not immediately damage the owner there.
3. After the ally actually loses life, transfer the cached value to the owner in `BUFF_LOSE_LIFE`.
4. If transferred damage should benefit from the same linked received-damage reduction, consume that provider state again in the transfer entrance.
5. Do not run the self-threshold stack-loss judgment a second time for the transferred damage unless the design explicitly says so.

Good fit:

- "self has X initial loyalty layers"
- "when self takes a big enough hit, lose one layer and reduce this hit"
- "while loyalty is above threshold, take part of ally damage"
- "every N lost loyalty layers, gain another stack family and immediately attack"
- "linked skills only add per-stack reduction or dispel after loyalty loss"

Why a new script may be required:

- existing `buff_share.lua` and `buff_injured_by_hp.lua` each solve only one side of the chain
- the bundle needs one ordered runtime that spans direct self damage, ally transfer, stack conversion, one-time trigger flags, custom reports, and linked provider consumption
- a pure attr-buff implementation cannot reliably cover transferred damage paths that are applied later through `change_hp(...)`

## Battle Report Coverage Method

Use this method before implementing any mechanic that changes state, damage, healing, control, dispel, or visible stacks. Battle reports are a player-facing contract, so the implementation must design them alongside the runtime logic instead of adding them at the end.

Required coverage matrix in `docs/IMPLEMENTATION.md`:

- Trigger entrance: which event or action inserts the report, and whether it is written into the current skill, `extern.skill`, or a resident buff effect list.
- Success and non-success branches: probability success, probability fail, no target, immune/invalid, cap reached, already active, no removable buff, and no-op branches.
- State mutation: stack gain, stack loss, stack conversion, current visible value, internal runtime value when different from display, state add, state expire, temporary invalidation, and restore.
- Numeric result: damage dealt, damage reduced, damage shared, healing, shield, attribute gain, lifesteal/counterattack/drain gain, and any per-layer total that players need to understand.
- Threshold behavior: first time reaching a threshold, later reaches, one-time flags, cooldown/round limits, and reset timing.
- Ordering: the report must appear next to the mechanic that caused it. Damage-triggered stack consumption should report around the damage event, not deferred to a later round-end batch unless the design explicitly says it is delayed.
- Placeholder mapping: list each `war_paper` text placeholder and the exact Lua `num_list` order. Use `RECORD_NUM_DEF.PERCENT_TYPE` for percentage placeholders and avoid hardcoding percent signs in Lua values.

Runtime insertion rules:

- Action-owned reports can usually remain on `script.skill`.
- Resident buffs that respond to another skill or damage event must insert through the current `extern.skill` flow: clean the resident effect list, add the buff word if needed, call `make_effect_records(...)`, then `insert_effect_list(extern.skill, nil)`.
- A debug line saying the report was created is not enough. Verify that the front-end battle report shows the line in the intended order.
- When one runtime operation triggers several player-visible effects, write reports in the same order as the mechanic: for example damage reduction -> final damage -> stack loss/current stack -> stack conversion -> follow-up attack/dispel/state.

## Event Lookup Shortlist

Use this shortlist to reduce search time before inventing a new listener script.

- `BUFF_CAST_SKILL_BEFORE`
  Launch-rate modification, cast gating, skip/extra-chance logic
- `BUFF_CAST_SKILL_OVER`
  After-active follow-up add-buff, attack, or heal
- `BUFF_CAST_SKILL_OVER_AGAIN`
  Recast or cast-again logic
- `BUFF_ATTACK_DAMAGE`
  Attacker-side damage modification
- `BUFF_ATTACKED_DAMAGE`
  Defender-side damage modification or hurt-trigger follow-up
- `BUFF_CURE_EFFECT`
  Final cure-value modification
- `BUFF_ORDER_START`
  Round resident work, periodic effects, round buffs
- `BUFF_ORDER_OVER`
  Per-round counter reset or limit cleanup
- `BUFF_ADD_START`
  Intercept add-buff and extend/alter incoming buff life
- `BUFF_ADD_OVER` / `BUFF_ADDED_OVER`
  Follow-up after buff successfully lands
- `BUFF_IMMUGE_SUCCESS`
  Follow-up after immunity or invalidation
- `BUFF_CLEAN_CD`
  Cooldown manipulation

## New Entry Template

When a new reusable mechanism is created, append:

### Family N: <short name>

- Purpose:
- Trigger events:
- Payload fields used:
- Persistent state used:
- Primary script paths:
- Typical config shape:
- When to reuse:
- When not to reuse:
