# Battle Action Catalog

This file is the direct-stage action reuse catalog for:

- `<battle_root>/module/actions_new/`

Use it before creating any new `action_xxx.lua`.

## Reuse Order

For direct stage effects, check these in order:

1. Existing attack action
2. Existing cure action
3. Existing add-buff action
4. Existing attr-change action
5. Existing state-gated or conditional action
6. Existing multi-hit or follow-up direct action

Only create a new action if the direct stage behavior cannot be expressed by one of the existing families plus config.

## Family 1: Basic Attack Actions

Use when the stage directly deals damage.

Core references:

- `action_attack.lua`
- `action_attack_random.lua`
- `action_attack_times.lua`
- `action_attack_with_crit.lua`
- `action_attack_with_debuff.lua`
- `action_attack_general.lua`
- `action_attack_target_hp.lua`
- `action_attack_rate_self_hp.lua`
- `action_attack_rate_target_hp.lua`
- `action_attack_two_max_attr.lua`

Good fit:

- one-shot damage
- random-target direct attack
- multi-hit direct attack
- damage scaled by hp or target hp
- conditional crit or debuff-linked damage

Avoid new action if:

- the requested direct damage is still an existing attack variant with only parameter differences

## Family 2: Basic Cure Actions

Use when the stage directly heals.

Core references:

- `action_cure.lua`
- `action_cure_by_hp.lua`
- `action_cure_general.lua`

Good fit:

- direct heal
- heal scaled by hp
- direct support stage without extra listener logic

## Family 3: Add-Buff Actions

Use when the stage only needs to apply buff(s) directly.

Core references:

- `action_add_buff.lua`
- `action_add_buff_random.lua`
- `action_add_buff_target_select.lua`
- `action_add_buff_target_attr.lua`
- `action_add_buff_target_hp.lua`
- `action_add_buff_target_general.lua`
- `action_add_buff_general.lua`
- `action_add_buff_enemy_type.lua`
- `action_add_buff_self_hp.lua`
- `action_add_buff_random_check_target.lua`

Good fit:

- direct add buff in skill stage
- target chosen by attr, hp, general type, or random
- self, enemy, or special-target buff application

Avoid new action if:

- the requested behavior is still "choose target and add buff"

## Family 4: State-Gated Or State-Switched Actions

Use when the direct stage changes behavior based on `customized_buff_state`.

Core references:

- `action_attack_with_state_active.lua`
- `action_add_buff_state_switch.lua`

Good fit:

- if state exists, use one attack/buff path
- if state exists, choose alternate buff id
- consumer-side direct stage depending on a prior state provider

This family is important for any provider-skill plus consumer-skill bundle design.

If a bundle can be solved by:

- one provider buff using `buff_add_state.lua`
- one consumer action from this family

then do not add a new action.

## Family 5: Attr Change Actions

Use when the stage directly changes attributes rather than attaching a resident listener.

Core references:

- `action_add_attr.lua`
- `action_add_attr_p.lua`
- `action_add_attr_star.lua`
- `action_steal_attr.lua`
- `action_steal_attr_general.lua`
- `action_dead_rate.lua`
- `action_private_dead_rate.lua`
- `action_morale.lua`
- `action_set_morale.lua`

Good fit:

- direct flat attr up/down
- direct percent attr up/down
- direct morale adjustment
- direct attr steal

## Family 6: Add Buff Plus Immediate Damage

Use when the stage both adds buff(s) and deals direct harm in one atomic action.

Core references:

- `action_add_buff_and_harm.lua`
- `action_attack_round_add_buff_disarm.lua`

Good fit:

- attack plus apply status
- add-buff plus immediate direct hit

Avoid new action if:

- the effect is still one direct stage combining already-supported subeffects

## Family 7: Conditional Target Or Environment Gating

Use when the action only works under certain scene, camp, equip, unit-type, or target-status conditions.

Core references:

- `action_check_scene_type.lua`
- `action_check_camp_add_buff.lua`
- `action_check_target_buff_attack.lua`
- `action_check_team_status.lua`
- `action_add_buff_has_equip.lua`
- `action_add_buff_scene_type.lua`
- `action_add_buff_cell_mode.lua`
- `action_add_buff_huaxia.lua`
- `action_add_buff_marks.lua`
- `action_add_buff_when_general.lua`

Good fit:

- "only in this scene/cell mode"
- "only if target has buff"
- "only if camp/team status matches"
- "only if attacker has equip or marker"

Avoid new action if:

- the mechanic is just an existing direct effect with an environment gate

## Family 8: Multi-Hit, Combined Attack, Or Follow-Up Direct Stage

Use when the stage itself contains multiple direct strikes or combined attacks.

Core references:

- `action_attack_times.lua`
- `action_attack_together.lua`
- `action_at_one_fight.lua`
- `action_duel_bq.lua`
- `action_attack_sec_crit.lua`
- `action_attack_no_ready.lua`

Good fit:

- multi-strike stage
- cooperative or duel-like direct action
- direct stage with built-in repeated hit pattern

## Family 9: Special Direct Effect Families

These are more specific, but still worth checking before inventing new code:

- movement or displacement: `action_move.lua`, `action_move_hp.lua`
- cooldown manipulation: `action_clean_first_skill_cd.lua`
- type conversion or skill-type setup: `action_set_skill_type_byo.lua`
- special scripted package actions: `action_tian_ce.lua`, `action_atrocities.lua`, `action_dark_war.lua`, `action_world_awe.lua`

Use these when the mechanic is clearly already modeled by one named direct action family.

## Bundle Guidance

In multi-skill bundle design, prefer:

- direct stage with existing action
- plus an existing resident buff if needed
- plus `buff_add_state.lua` if a later stage or later buff needs persistent state

Prefer this over writing a custom action for every hero.

## New Entry Template

When a new reusable action family is added, append:

### Family N: <short name>

- Purpose:
- Primary action paths:
- Typical config shape:
- Good fit:
- When not to reuse:
