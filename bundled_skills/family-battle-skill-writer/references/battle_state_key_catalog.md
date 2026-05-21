# Battle State Key Catalog

This file catalogs known `customized_buff_state` keys used in:

- `<battle_root>/module/`

Use this before adding a new persistent state key.

Preferred pattern:

- if an existing key already models the same mechanism family, reuse that family
- if a key is only a provider-side data slot, prefer `buff_add_state.lua`
- only add a new key when no existing provider/consumer family fits

## Generic Provider Pattern

Primary writer:

- `<battle_root>/module/buffs_new/buff_add_state.lua`

Typical shape:

- writer stores `owner.customized_buff_state[key] = config`
- consumer checks `attacker.customized_buff_state[key]` or `owner.customized_buff_state[key]`

## Key List

### `clean_cd_tactic`

Used by:

- `action_clean_first_skill_cd.lua`
- `buff_jisu.lua`

Mechanism family:

- cooldown chance enhancement

### `dafeng_unique`

Used by:

- `buff_lbws_dafeng.lua`

Mechanism family:

- unique trigger guard / duplicate prevention

### `debt_store_rate`

Used by:

- `buff_debt.lua`

Mechanism family:

- stored rate affecting later damage or debt conversion

### `dice_damage`

Used by:

- `buff_echo_of_fate.lua`

Mechanism family:

- extra damage payload for dice branch skills

Provider:

- usually `buff_add_state.lua`

Consumer contract:

- shape: `{ "dice_damage", target_camp, target_def, harm_type, base_rate }`
- consumer reads indexes `[2]` to `[5]`
- target lookup uses the configured camp and target definition
- damage is applied with the configured harm type and base rate through the normal damage path

Use when:

- a linked skill adds extra damage after the canonical dice branch resident buff executes
- the linked skill does not need its own resident consumer script

### `dice_diff_pre`

Used by:

- `buff_echo_of_fate.lua`

Mechanism family:

- branch exclusion or branch-difference constraint

This is the exact family where a provider skill can often be only:

- one `add_state` buff
- one config payload

without needing a new consumer buff

Provider:

- usually `buff_add_state.lua`

Consumer contract:

- shape: `{ "dice_diff_pre", enabled_flag }`
- presence/enabled flag means the current dice roll should exclude the previous selected branch when possible
- consumer compares against `script.last_effect` and the branch-to-dice mapping table

Use when:

- a linked skill says the next/current dice branch should differ from the previous branch
- the base resident buff already owns branch selection and reporting

### `duel_extra`

Used by:

- `action_duel_bq.lua`

Mechanism family:

- duel extra behavior bundle

### `empire_base_chance`

Used by:

- `buff_add_buffs_after_all_active.lua`

Mechanism family:

- extra trigger base chance for post-active follow-up

### `jisu_tactic`

Writer:

- `buff_jisu_tactic.lua`

Mechanism family:

- tactic-side provider for cooldown-related logic

### `jlssy_tactic`

Used by:

- `buff_jls_shenyu.lua`

Mechanism family:

- trigger chance enhancement through persistent state

### `menshen_qq`

Writer:

- `buff_menshen_qq.lua`

Consumers:

- `buff_qinqiong_menshen.lua`

Mechanism family:

- linked bodyguard / menshen pairing

### `menshen_ycg`

Writer:

- `buff_menshen_ycg.lua`

Consumers:

- `buff_yuchigong_menshen.lua`

Mechanism family:

- linked bodyguard / menshen pairing

### `yuefei_baoguo_hurt_reduce`

Used by:

- `buff_yuefei_jingzhong.lua`

Mechanism family:

- linked provider that contributes per-stack received-damage reduction into one existing resident listener

Provider:

- usually `buff_add_state.lua`

Consumer contract:

- shape: `{ "yuefei_baoguo_hurt_reduce", reduce_per_report_country_layer }`
- consumer still owns the canonical loyalty/report-country runtime state
- provider only contributes a per-layer reduction coefficient and does not create its own damage listener
- consumer may apply the same reduction in more than one damage entrance, for example direct self damage and transferred share damage

Use when:

- one linked skill says "each existing stack additionally reduces received damage by X%"
- the base resident listener already owns the stack count, threshold logic, and report order
- the reduction must also apply to damage paths that are not cleanly covered by a standalone attr buff, such as transferred damage via `change_hp(...)`

### `yuefei_loyalty_dispel`

Used by:

- `buff_yuefei_jingzhong.lua`

Mechanism family:

- linked provider that adds a follow-up dispel whenever the core resident listener consumes enough loyalty layers

Provider:

- usually `buff_add_state.lua`

Consumer contract:

- shape: `{ "yuefei_loyalty_dispel", target_def, remove_num }`
- consumer still owns the canonical loyalty-loss counting
- provider only contributes target rule and dispel count
- actual target finding, confuse records, and `remove_debuff_num(...)` stay inside the main resident listener

Use when:

- one linked skill says "every N consumed/lost layers, dispel ally debuffs"
- the base resident listener already owns the stack-loss timing and should remain the single source of truth
- creating a second listener would risk double counting or report-order drift

### `ragsa_hannu_bonus_stack`

Used by:

- `buff_ragsa_hannu_listener.lua`

Mechanism family:

- linked provider that adds extra stack count into the same debuff-trigger chain

Provider:

- usually `buff_add_state.lua`

Consumer contract:

- shape: `{ "ragsa_hannu_bonus_stack", chance, extra_layers, bonus_record_id }`
- consumer still owns the canonical `BUFF_ADDED_OVER` listener
- provider only contributes extra layers inside the same trigger chain
- `chance` is per-trigger chance in wan-percent
- `extra_layers` is the extra stack count added on top of the base layer
- `bonus_record_id` is optional and used only when an extra trigger report is desired

Use when:

- one linked passive should enhance an existing debuff-stack listener without creating a second competing listener
- the extra layers must share the same threshold, clear, and burst ordering as the base stack mechanic

### `ragsa_hannu_threshold_adjust`

Used by:

- `buff_ragsa_hannu_listener.lua`

Mechanism family:

- linked provider that changes the initial threshold of a resident stack listener

Provider:

- usually `buff_add_state.lua`

Consumer contract:

- shape: `{ "ragsa_hannu_threshold_adjust", flat_reduce }`
- consumer reads it during `init_script`
- `flat_reduce` reduces only the initial threshold before the listener enters runtime
- the reduced threshold is still clamped by the listener's own minimum threshold config

Use when:

- one linked skill only reduces the burst threshold of an existing stack/burst mechanic
- the consumer already owns the runtime state and only needs a start-of-battle modifier

### `sand_bless_1`

Used by:

- `buff_sand_bless.lua`

Mechanism family:

- extra add-buff payload

### `sand_bless_2`

Used by:

- `buff_sand_bless.lua`

Mechanism family:

- cure enhancement payload

### `tian_ce_extra`

Used by:

- `action_tian_ce.lua`

Mechanism family:

- extra trigger chance plus buff payload

### `tian_ce_layer`

Used by:

- `action_tian_ce.lua`
- `buff_tian_ce_tactic.lua`

Mechanism family:

- persistent layer counter

### `xxml_tactic`

Used by:

- `buff_xuezhu.lua`

Mechanism family:

- persistent modifier for later trigger rate

### `zgd_txgx`

Used by:

- `buff_zhougongdan.lua`

Mechanism family:

- linked extra buff payload provider

### `zhanbei_cure`

Used by:

- `buff_zhanbei.lua`

Mechanism family:

- stored cure payload

### `zhanbei_cure_chance`

Used by:

- `buff_zhanbei.lua`

Mechanism family:

- stored cure trigger chance payload

## Reuse Guidance

Before adding a new state key, ask:

1. Is this just a stored chance, damage, cure, layer, extra buff id, or branch constraint
2. Can an existing key family express the same kind of dependency
3. Can the producer be only `buff_add_state.lua`
4. Does an existing action or buff already consume the desired shape

If yes, prefer:

- temp config
- existing consumer
- `buff_add_state.lua`

over adding:

- a new consumer buff
- a new action
- a new state key
