# Battle Event Reuse Map

This file maps common battle events to existing buff families in:

- `<battle_root>/module/buffs_new/`

Use it before adding a new listener buff.

## How To Use

1. Find the trigger timing in the skill description.
2. Find the matching event below.
3. Check whether an existing family already matches the effect shape.
4. Reuse the family if the only difference is numeric config, target rules, duration, or condition details.

## `BUFF_CAST_SKILL_BEFORE`

Typical purpose:

- active or ready skill launch-rate modification
- cast gating before actual launch

Existing families:

- `buff_active_skill_byo_launch_rate.lua`
- `buff_active_skill_byo_launch_rate_ycg.lua`
- `buff_active_skill_launch_rate.lua`
- `buff_active_skill_launch_rate_by_hp.lua`
- `buff_active_skill_rate_by_attr.lua`
- `buff_ready_skill_byo_launch_rate.lua`
- `buff_ready_skill_launch_rate.lua`
- `buff_stacking.lua`
- `buff_times_active_or_assault_rate.lua`
- `buff_times_active_skill_launch_rate.lua`

## `BUFF_CAST_SKILL_OVER`

Typical purpose:

- after active skill follow-up
- extra buff, heal, recast trigger, or add-on attack

Existing families:

- `buff_active_after_add_buff_and_cure.lua`
- `buff_add_buff_after_active.lua`
- `buff_add_buff_after_byo_active.lua`
- `buff_add_buffs_after_all_active.lua`
- `buff_attack_after_target_active_skill.lua`
- `buff_cure_after_active_skill.lua`
- `buff_fearless_love.lua`
- `buff_strategy.lua`
- `buff_stunt_adn.lua`
- `buff_times_active_skill_harm_rate.lua`
- `buff_unyielding.lua`

## `BUFF_CAST_SKILL_OVER_AGAIN`

Typical purpose:

- recast or extra cast chain

Existing families:

- `buff_fearless_love.lua`

## `BUFF_ORDER_START`

Typical purpose:

- periodic per-round work
- branch logic, periodic add buff, dot/hot work, periodic heal or attack

Existing families include:

- round add-buff families:
  `buff_add_buff_all_round.lua`
  `buff_add_buff_round.lua`
  `buff_add_buff_round_alone.lua`
  `buff_add_buff_round_chance.lua`
  `buff_add_buff_round_self.lua`
- round attack or reflect families:
  `buff_attack_round.lua`
  `buff_attack_round_blood.lua`
  `buff_attack_round_light.lua`
  `buff_thorns.lua`
- round cure families:
  `buff_cure_round.lua`
  `buff_cure_self_and_friend.lua`
  `buff_round_clean_cure_all.lua`
- branch/random families:
  `buff_echo_of_fate.lua`
  `buff_strong_wind_and_rain.lua`
  `buff_tyrant.lua`
- many other resident round listeners already exist, so check this event carefully before adding a new buff

## `BUFF_ORDER_OVER`

Typical purpose:

- end-of-turn reset
- per-round count cleanup
- state expiry helpers

Existing families:

- `buff_disarm.lua`
- `buff_double_hit.lua`
- `buff_sand_bless.lua`
- `buff_silence.lua`
- `buff_times_active_or_assault_rate.lua`
- `buff_times_active_skill_launch_rate.lua`
- `buff_times_assault_skill_launch_rate.lua`
- `buff_yuchigong_menshen.lua`

## `BUFF_ADD_START`

Typical purpose:

- intercept an incoming buff before it lands
- extend or modify incoming buff life or handling

Existing families:

- `buff_extend_after_control.lua`

## `BUFF_ADD_OVER`

Typical purpose:

- after buff successfully lands on source side
- add follow-up buff, extend life, dot extension

Existing families:

- `buff_add_buff_after_control.lua`
- `buff_add_buff_after_debuff.lua`
- `buff_add_buff_after_type_id.lua`
- `buff_add_life_by_type.lua`
- `buff_add_life_by_type_id.lua`
- `buff_dot_extend.lua`
- `buff_no_dead_man.lua`
- `buff_putrefaction.lua`
- `buff_ysf_1.lua`

## `BUFF_ADDED_OVER`

Typical purpose:

- after buff successfully lands on target side
- target-side reactive add-buff, attack, cure, move, or attr response

Existing families:

- `buff_add_attr_by_double_hit.lua`
- `buff_add_buff_after_controlled.lua`
- `buff_attack_after_debuff.lua`
- `buff_attack_control.lua`
- `buff_cure_after_control.lua`
- `buff_fight_spirit.lua`
- `buff_ice.lua`
- `buff_move_by_debuff.lua`
- `buff_ragsa_hannu_listener.lua`

Extra note:

- when the requirement is "enemy successfully gets a debuff -> self stacks -> threshold burst later", prefer a resident cross-camp listener plus a separate self overlying buff instead of forcing all behavior into one target-side script
- if that self stack only provides static per-layer attributes, such as "each stack increases weapon damage" or "each stack reduces received damage", prefer making the stack buff use `buff_add_attr.lua` with `HARM_PHY_P` / `INJURED_PHY_P` / `INJURED_INTELLECT_P` configs instead of generating a separate `BUFF_ATTACK_DAMAGE` / `BUFF_ATTACKED_DAMAGE` consumer script
- when linked passives only change the threshold or extra stack count of that same mechanic, prefer `buff_add_state.lua` providers consumed by `buff_ragsa_hannu_listener.lua` instead of creating a second `BUFF_ADDED_OVER` listener

## `BUFF_IMMUGE_SUCCESS`

Typical purpose:

- follow-up after immunity or invalidation success

Existing families:

- `buff_ks_2.lua`

## `BUFF_ATTACK_DAMAGE`

Typical purpose:

- attacker-side damage modification

Existing families include:

- active damage families:
  `buff_active_harm_by_int.lua`
  `buff_active_harm_rate_by_hp.lua`
  `buff_active_harm_rate_by_maxhp.lua`
  `buff_active_skill_byo_harm_rate.lua`
  `buff_active_skill_harm_rate.lua`
  `buff_active_skill_harm_rate_overlying.lua`
  `buff_active_skill_harm_up_control.lua`
- assault damage families:
  `buff_assault_skill_byo_harm_rate.lua`
  `buff_assault_skill_harm_rate.lua`
- generic or conditional damage families:
  `buff_harm.lua`
  `buff_harm_rate_by_maxhp.lua`
  `buff_harm_rate_by_minhp.lua`
  `buff_harm_rate_by_more_hp.lua`
  `buff_harm_rate_by_target_hp.lua`
  `buff_harm_rate_by_target_posistion.lua`
  `buff_harm_up_by_hp.lua`
  `buff_harm_up_to_target_camp.lua`
  `buff_times_harm_rate.lua`
- times-based or special:
  `buff_fearless_love.lua`
  `buff_stacking.lua`
  `buff_times_active_skill_harm_rate.lua`
  `buff_times_assault_skill_harm_rate.lua`
  `buff_ragsa_hannu_state.lua`

## `BUFF_ATTACKED_DAMAGE`

Typical purpose:

- defender-side damage modification
- injured-after logic

Existing families:

- `buff_add_buff_before_injured.lua`
- `buff_bi_si_mai.lua`
- `buff_diaochan.lua`
- `buff_first_injured_round.lua`
- `buff_han_wu_di.lua`
- `buff_injured_active_skill_rate.lua`
- `buff_injured_assualt_skill_rate.lua`
- `buff_injured_by_hp.lua`
- `buff_injured_dot.lua`
- `buff_injured_harm_rate_army_type.lua`
- `buff_injured_move_and_cure.lua`
- `buff_injured_normal_attack_rate.lua`
- `buff_injured_rate_by_debuff.lua`
- `buff_injury_free.lua`
- `buff_injury_free_nomarl_attack.lua`
- `buff_qinqiong_first_target.lua`
- `buff_qinqiong_menshen.lua`
- `buff_state_change_harm.lua`
- `buff_thunder_sigil.lua`
- `buff_times_injured_rate.lua`
- `buff_zhanbei.lua`
- `buff_ragsa_hannu_state.lua`

Extra note:

- when the requirement combines "self large-hit threshold", "ally share transfer", and "lost-stack follow-up" in one ordered runtime, check whether one resident bundle listener should own `BUFF_ATTACKED_DAMAGE` together with `BUFF_ATTACKED_SHARE` and `BUFF_LOSE_LIFE`; `buff_yuefei_jingzhong.lua` is the reference for this combined shape
- if a linked skill only says "each current stack further reduces received damage", prefer a provider state consumed by that canonical listener when transferred damage via `change_hp(...)` must also be reduced, instead of assuming `buff_add_attr.lua` alone will cover every entrance

## `BUFF_ATTACKED_SHARE`

Typical purpose:

- intercept ally damage before final hp loss
- cache redirected/share amounts for a later owner-side transfer

Existing families:

- `buff_share.lua`
- `buff_share_for_target.lua`
- `buff_guard.lua`
- `buff_yuefei_jingzhong.lua`

Extra note:

- if the owner should only really lose hp after the protected ally confirms hp loss, pair this event with `BUFF_LOSE_LIFE` instead of directly calling `change_hp(...)` here

## `BUFF_LOSE_LIFE`

Typical purpose:

- react after the target really loses hp
- convert a previously cached share amount into owner-side hp change

Existing families:

- `buff_share.lua`
- `buff_share_for_target.lua`
- `buff_yuefei_jingzhong.lua`

## `BUFF_CURE_EFFECT`

Typical purpose:

- modify final cure amount

Existing families:

- `buff_cure_effect.lua`
- `buff_diaochan.lua`

## `BUFF_BEFORE_CURE`

Typical purpose:

- pre-cure multiplier or pre-cure condition check

Existing families:

- `buff_cure_rate_up_hot.lua`
- `buff_slmdd_1.lua`

## `BUFF_BEFORE_CURED`

Typical purpose:

- target-side pre-cure multiplier

Existing families:

- `buff_cure_rate_up_hot.lua`

## `BUFF_CLEAN_CD`

Typical purpose:

- cooldown clear or cooldown handling interception

Existing families:

- `buff_fearless_love.lua`
- `buff_jisu.lua`
- `buff_ml_1.lua`
- `buff_stunt_arl.lua`

## `BUFF_REMOVE_OVER`

Typical purpose:

- cleanup or reverse effect after buff removal

Existing families:

- `buff_add_attr_by_double_hit.lua`
- `buff_gemstone_radiance.lua`

## Practical Rule

If the trigger timing matches one of the events above, default assumption should be:

- reuse an existing family

not:

- create a new buff

Create a new listener buff only when:

- the event is truly new for the desired effect shape
- the payload handling is new
- the lifecycle is materially different from existing families
