# Project Setup Guide — authors an example game-audio project with FmodStudioMCP

This page shows a realistic end-to-end session: building a two-event player
audio project (a footstep loop and a hit one-shot, each with a parameter) and
putting it into a bank. Adapt the names to your project.

## Before you start

- FMOD Studio running with the **Script Server enabled** and a project open
  (see [INSTALLATION.md](INSTALLATION.md)).
- An MCP client configured with the `fmod-studio` server.
- Some short audio files on disk (e.g. `footsteps.wav`, `hit.wav`).

## Authoring session

### 1. Audit what exists

```
List every event in the project
List every bank in the project
```

Use the results so you never duplicate content. Echoed GUIDs/paths are inputs
for the next calls.

### 2. Make folders

```
Create an EventFolder hierarchy: Player
```

### 3. Import audio first

```
Import C:\audio\footsteps.wav
Import C:\audio\hit.wav
```

Each returns an asset `{guid}`. Keep them — you'll attach them next.

### 4. Create the events + tracks + instruments

```
Create an event named "Player/Footsteps" in the Player folder, add a track "Loop", and place a SingleSound instrument on it from 0s to 10s
```

Then attach the imported `footsteps.wav` asset to that instrument
(`sound_set_audio_file` with the two GUIDs you just got back).

Repeat for `Player/Hit` with `hit.wav`.

### 5. Parameter culture

```
Add a "Reverbed" User parameter to Player/Footsteps, range 0-1, initial 0
```

Event parameters become settable by the game at runtime, or an automation
surface on the timeline.

### 6. Routing + mixer

```
Create a mixer group "SFX" and route it to the Master bus
Set SFX volume to -6 dB
Add a LimiterEffect to the master bus
```

> Keep each event's routing inside its own surface. Re-routing a child
> event's master track output into *another* event's mixer is a known Studio
> crash — the tools exist to prevent it, not to tempt it.

### 7. Banks

```
Create a bank "Gameplay"
Assign Player/Footsteps and Player/Hit to it
List the events in Gameplay to confirm
```

An event not assigned to any bank never ships with the build.

### 8. Validate, save, build

```
Run project validation
Save the project
Build the project
```

`project_build` is a long operation — let it finish; a large project can take
minutes. The built banks land in the project's Build folder, ready for your
engine's FMOD integration.

---

## Evolving / interactive music

The flagship game-design workflow: **layered music that changes with the
map**, implemented exactly the way FMOD's documentation prescribes.

1. **Layers as mixer groups.** Create a mixer group per musical layer
   (`SFX`, `Music/Drums`, `Music/Pads`, `Music/Arp`), route to Master.
2. **One looping track per layer.** `event_add_track` per layer on a single
   music event; place a SingleSound instrument looping on each (`import`
   stems → `sound_add_to_track`).
3. **A game parameter.** `parameter_add` an `Intensity` (or `Exploration`)
   parameter, and map it via `parameter_set_initial`.
4. **Automate layer volumes against it.** This is the evolving part:

   ```
   automation_add_curve  "mixer:/Music/Drums"  "volume"  "parameter:/Intensity"  "parameter"  [[0,-80],[0.25,-6],[1,0]]
   automation_add_curve  "mixer:/Music/Pads"   "volume"  "parameter:/Intensity"  "parameter"  [[0,0],[0.5,-6],[1,-80]]
   automation_add_curve  "mixer:/Music/Arp"    "volume"  "parameter:/Intensity"  "parameter"  [[0,-80],[0.75,-6],[1,3]]
   ```

   As the player moves deeper into the map, the game raises `Intensity` and
   the drums/pads/arpeggio crossfade in — a unified score that evolves, not
   hard cuts. For a *time-based* progression instead of parameter-driven, use
   `driver_type="timeline"` with an event driver and time-based points.
5. **Snapshots for whole-mix states.** A "cave cavern" or "underwater"
   reverb/level shift as a `snapshot_create`d state, bound to its buses with
   `snapshot_bind_group`. The game blends it in like a sound; it ships in the
   banks with the build.

## Habits worth keeping

1. **Audit before creating.** Duplication is the most common mistake.
2. **Save explicitly.** Studio applies edits live and there is no terminal
   undo — a crash before `project_save` loses this bridge's edits.
3. **Chain GUIDs, don't path-guess.** Result `{guid}`s are exact; a hand-typed
   `event:/…` path is one typo from a `lookup failed` error.
4. **Import once, reuse assets.** One imported asset can feed many instruments.
5. **Keep the project in VCS.** FMOD Studio projects are file-based and diff
   reasonably well — commit before/after risky batches so you can roll back.