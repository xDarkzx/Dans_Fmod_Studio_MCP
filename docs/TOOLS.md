# Tools Reference

Every tool in FmodStudioMCP, grouped by module. All tools run in the **live** project — call `project_save` when you want it on disk.

## Conventions

- **References:** paths (`event:/UI/Hover`, `bank:/Master`) or `{guid}`. Echoed results chain straight into the next call.
- **`execute_long`** operations (bank build, audio import) wait up to 600 s.
- **All list tools are capped** (see `constants.py`).

## Project (`project_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `project_get_info` | `()` | Open project's `.fspro` file path + display name. |
| `project_save` | `()` | Save the project. |
| `project_save_all` | `()` | Save project + every edited file (assets, banks, plugins). |
| `project_build` | `(banks?, platforms?)` | **long** — build banks for the selected platform(s); optionally scope to specific bank name(s)/platform name(s). |
| `project_get_modified` | `()` | Whether the project has unsaved changes. |

## Events (`event_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `event_create` | `(name, folder?)` | Create an event (optionally under an `event:/…` folder). |
| `event_delete` | `(target)` | Delete an event. |
| `event_info` | `(target)` | guid/name/path + maxVoices. |
| `event_list` | `()` | List every event (capped). |
| `event_lookup` | `(target)` | Resolve to canonical path + guid. |
| `event_set_name` | `(target, name)` | Rename. |
| `event_set_folder` | `(target, folder)` | Move into a folder / to the root. |
| `event_add_track` | `(target, name?)` | Add a group (audio) track. Returns `trackGuid` (for `sound_add_to_track`) and `mixerGroupGuid` (for `automation_add_curve`/`mixer_group_volume`/`mixer_effect_add`) — different objects, don't mix them up. |
| `event_list_tracks` | `(target, include_master?)` | List group tracks (+ master), each with `trackGuid` and `mixerGroupGuid`. |
| `event_set_max_voices` | `(target, max_voices)` | Cap simultaneous instances (1–1000). |
| `event_timeline_cursor` | `(target, position)` | Scrub the timeline cursor (seconds). |

## Audition (`audition_tools.py`) — hear the result, don't just read the event tree

| Tool | Signature | What it does |
|------|-----------|--------------|
| `event_play` | `(target)` | Play an event instance. |
| `event_stop` | `(target, immediate?)` | Stop a playing instance (immediate, or let release/tails finish). |
| `event_toggle_pause` | `(target)` | Toggle pause on a playing instance. |
| `event_key_off` | `(target)` | Send keyoff (releases a pending sustain point). |
| `event_return_to_start` | `(target)` | Return playback to the cursor/timeline start. |
| `event_playback_status` | `(target)` | isPlaying/isPaused/isStopping + playhead position. |

## Markers (`marker_tools.py`) — timeline logic markers for interactive music

| Tool | Signature | What it does |
|------|-----------|--------------|
| `event_add_marker_track` | `(target)` | Add a marker (logic) track — required once before placing markers. |
| `marker_add_named` | `(track_target, name, position)` | Add a named destination marker. |
| `marker_add_region` | `(track_target, name, position, length, loop_mode?)` | Add a destination (loop) region. |
| `marker_add_sustain_point` | `(track_target, position)` | Add a sustain point (holds until `event_key_off`). |
| `marker_add_transition` | `(track_target, position, destination_target)` | Add a transition marker (jumps to a NamedMarker/LoopRegion). |
| `marker_add_transition_region` | `(track_target, position, length, destination_target)` | Add a transition region. |
| `marker_list` | `(track_target)` | List a track's markers/regions/transitions, tagged by type (capped). |
| `marker_rename` | `(target, name)` | Rename a marker/region. |
| `marker_set_position` | `(target, position)` | Move a point-type marker. |
| `marker_set_region` | `(target, position, length)` | Move/resize a region-type marker. |
| `marker_delete` | `(target)` | Delete a marker/region (**destructive**, backed up). |

## Sounds (`sound_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `audio_import` | `(file_path)` | **long** — import a .wav/.aiff/.flac/.mp3/.ogg as an asset; returns `{guid}`. |
| `audio_assets` | `()` | List imported audio assets (capped). |
| `sound_add_to_track` | `(event_target, track_target, sound_type, start, length?, name?)` | Place a Single/Multi/Programmer/Scatterer/Event instrument on a track timeline. |
| `sound_create` | `(sound_type, name?)` | Stand-alone instrument (e.g. for a Multi's playlist). |
| `sound_set_audio_file` | `(target, audio)` | Assign an imported asset to an instrument. |
| `sound_set_owner` | `(target, owner)` | Nest instruments (SingleSound into a Multi, …). |
| `sound_set_name` | `(target, name)` | Rename an instrument. |
| `sound_info` | `(target)` | Instrument guid/name/path. |

## Parameters (`parameter_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `parameter_add` | `(event_target, name, param_type?, min?, max?)` | Add a game parameter (User/UserEnumeration/Distance/Direction/Elevation/EventConeAngle/EventOrientation). |
| `parameter_list` | `(event_target)` | List an event's parameters. |
| `parameter_set_initial` | `(event_target, parameter_name, value)` | Set the initial value. |
| `parameter_set_labels` | `(event_target, parameter_name, labels)` | Set enumeration labels on a UserEnumeration. |

## Banks (`bank_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `bank_create` | `(name)` | Create a bank. |
| `bank_list` | `()` | List every bank (capped). |
| `bank_info` | `(target)` | guid/name/path. |
| `bank_rename` | `(target, name)` | Rename. |
| `bank_delete` | `(target)` | Delete a bank + contents. |
| `bank_add_event` | `(bank_target, event_target)` | Assign an event to a bank. |
| `bank_remove_event` | `(bank_target, event_target)` | Remove an event from a bank. |
| `bank_list_events` | `(bank_target)` | Events assigned to the bank (capped). |

## Mixer (`mixer_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `mixer_group_create` | `(name, output_target?)` | Create a group (Master out by default). |
| `mixer_group_list` | `()` | List mixer groups (capped). |
| `mixer_group_info` | `(target)` | guid/name/path/volume. |
| `mixer_group_rename` | `(target, name)` | Rename. |
| `mixer_group_delete` | `(target)` | Delete a group. |
| `mixer_group_route` | `(target, output_target)` | Set a group's output bus/group. |
| `mixer_group_volume` | `(target, db)` | Volume in dB (-80…+10). |
| `mixer_effect_add` | `(target, effect)` | Add an effect (23 types, e.g. `CompressorEffect`, `LimiterEffect`). |
| `mixer_effect_list` | `(target)` | List effects on a group's chain (tagged with `entity` type — includes built-in `MixerBusFader`/`MixerBusPanner` alongside any effects added). |
| `mixer_master_info` | `()` | Master bus guid/name/volume. |
| `mixer_master_volume` | `(db)` | Set master volume in dB. |
| `vca_create` | `(name)` | Create a VCA (scales every strip assigned to it). |
| `vca_list` | `()` | List every VCA (capped). |
| `vca_info` | `(target)` | guid/name/volume. |
| `vca_volume` | `(target, db)` | Set a VCA's volume in dB. |
| `vca_assign` | `(vca_target, strip_target)` | Assign a mixer strip to a VCA. |
| `mixer_send_create` | `(event_target, source_group_target, return_name, level_db?)` | Create a return track + send within one event's mixer (e.g. a reverb bus). Per-event only — FMOD has no cross-event send in this API. |

## Automation (`automation_tools.py`) — the heart of evolving/interactive music

| Tool | Signature | What it does |
|------|-----------|--------------|
| `automation_add_curve` | `(target, property, driver, driver_type, points)` | Bind a property to a curve; as the driver moves, the property follows. |
| `automation_add` | `(target, property, driver, driver_type, position, value)` | Add one point to an existing curve. |
| `automation_list` | `(target)` | Report whether an object supports automators. |

- `property` = `volume` | `pitch` | `gain`. `target` is the automated object
  (mixer group, bus, VCA, event, effect).
- `driver_type="parameter"` → `driver` is `parameter:/Intensity`; points are
  `[parameterValue, mappedValue]`.
- `driver_type="timeline"` → `driver` is `event:/…`; points are `[seconds, value]`.

**Vertical layering example** — three music layers crossfading with an
"Intensity" game parameter:

```
parameter_add "event:/Music/CombatDrums" params...
automation_add_curve "group:/Music/Drums" "volume" "parameter:/Intensity" "parameter" [[0,-100],[0.4,-6],[1,0]]
automation_add_curve "group:/Music/Pads"   "volume" "parameter:/Intensity" "parameter" [[0,0],[0.6,-6],[1,-80]]
```

## Snapshots (`snapshot_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `snapshot_create` | `(name)` | Create a mixer snapshot. |
| `snapshot_list` | `()` | List every snapshot (capped). |
| `snapshot_info` | `(target)` | guid/name/path. |
| `snapshot_rename` | `(target, name)` | Rename. |
| `snapshot_delete` | `(target)` | Delete a snapshot. |
| `snapshot_bind_group` | `(snapshot_target, group_target)` | Bind a mixer group's captured settings to a snapshot. |

Snapshots are activated by the game like a sound (they ship in banks); the
authoring side here creates and organises them.

## Folders (`folder_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `folder_create` | `(kind, path)` | Find-or-create a folder chain (`"UI/HUD"`); kind = `EventFolder`/`AssetFolder`. `AssetFolder` isn't creatable in FMOD Studio 2.03.14 — errors clearly rather than silently no-op'ing. |
| `folder_list` | `(kind?)` | List folders (optionally filtered by kind). |

## Workspace (`workspace_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `workspace_info` | `()` | Roots: event/asset/bank folders + master bus. |
| `workspace_browser_current` | `()` | Object selected in the project browser. |
| `workspace_navigate` | `(target)` | Open the object in its editor. |
| `workspace_editor_selection` | `()` | Object selected in the open editor. |

## Utility (`utility_tools.py`)

| Tool | Signature | What it does |
|------|-----------|--------------|
| `utility_lookup` | `(target)` | Resolve any object to guid/name/path. |
| `utility_list` | `(obj_type)` | List a type: Event/Bank/MixerGroup/MixerBus/MixerVCA/Snapshot/Folder/Preset. |
| `utility_is_valid` | `(target)` | Whether the object is valid. |
| `utility_delete` | `(target)` | Delete any object (**destructive**). |
| `utility_dump` | `(target)` | Real introspection: every plain settable property (with value) + every relationship (cardinality + count). **Use this before concluding a capability doesn't exist** — FMOD's own `dump()` only logs to Studio's own console, invisible to this bridge, and is not what this tool calls. |
| `utility_validate` | `()` | Run project validation and report issues. |