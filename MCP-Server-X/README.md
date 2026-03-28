# 🚀 MCP Server for Ableton Live  
**Version 2.3 — Stable**

A lightweight, fast, and fully scriptable **MCP server** for Ableton Live.  
It exposes a complete set of tools to control Live: session, tracks, clips, devices, browser, groove, automation, and more.

Designed for AI agents, control surfaces, and advanced automation workflows.

---

# ✨ Features

- Full session control (tempo, playback, time signature)
- Track management (volume, pan, sends, mute/solo/arm)
- MIDI clip creation in Session & Arrangement View
- Device parameter access (internal & external plugins)
- Drum Rack & instrument loading
- Browser search (instruments, effects, presets, VST2/VST3/AU)
- Automation writing (Session & Arrangement)
- Groove Pool integration
- Key & scale reading and transformation
- Modal transposition (Dorian, Mixolydian, Lydian…)
- Auto‑shutdown when Ableton closes
- Stable versioning system
- Precise dB curves for volume & sends
- Reliability improvements and watchdog monitoring

---

# 🧰 Available Tools (v2.3)

Below is the complete list of tools exposed by the MCP server.

---

## 🎛️ Session

| Tool | Description |
|---|---|
| `get_session_info` | Tempo, time signature, tracks, returns, master |
| `set_tempo` | Sets the tempo in BPM |
| `start_playback` | Starts playback |
| `stop_playback` | Stops playback |

---

## 🎹 Key & Scale  
*(Supported by Remote Script — exposed via MCP)*

| Tool | Description |
|---|---|
| `get_song_key` | Reads the root note and scale name |
| `set_song_root_note` | Sets the root note (0=C … 11=B) |
| `get_song_scale` | Reads the mode and scale name |
| `set_song_scale` | Sets the scale by name (`major`, `minor`, `dorian`…) |

---

## 🎚️ Tracks

| Tool | Description |
|---|---|
| `get_track_info` | Full track info (name, type, devices, clips) |
| `create_midi_track` | Creates a new MIDI track |
| `set_track_name` | Renames a track |
| `set_track_volume` | Sets volume (dB or raw) |
| `set_track_pan` | Sets pan (-1.0 to 1.0) |
| `set_track_send` | Sets send level (dB or raw) |
| `set_track_mute` | Mute / unmute |
| `set_track_solo` | Solo / unsolo |
| `set_track_arm` | Arm / disarm for recording |

---

## 🎼 Clips — Session View

| Tool | Description |
|---|---|
| `create_clip` | Creates a MIDI clip |
| `add_notes_to_clip` | Adds MIDI notes |
| `set_clip_name` | Renames a clip |
| `fire_clip` | Launches clip playback |
| `stop_clip` | Stops clip playback |

---

## 🎼 Clips — Arrangement View

| Tool | Description |
|---|---|
| `get_arrangement_clips` | Lists arrangement clips |
| `create_arrangement_clip` | Creates a clip on the timeline |
| `set_arrangement_clip_name` | Renames a clip |
| `add_notes_to_arrangement_clip` | Adds notes |
| `replace_notes_arrangement` | Replaces all notes |
| `set_arrangement_envelope` | Writes automation |
| `set_arrangement_clips_color` | Colors clips |
| `transpose_arrangement_clips` | Chromatic or modal transposition |

---

## 📈 Automation & Envelopes

| Tool | Description |
|---|---|
| `set_clip_envelope_point` | Writes automation points in a Session View clip |
| `clear_clip_envelope` | Clears a Session View clip envelope |
| `set_arrangement_envelope` | Writes automation in Arrangement View |

---

## 🎛️ Devices & Instruments

| Tool | Description |
|---|---|
| `get_device_parameters` | Lists all device parameters |
| `set_device_parameters` | Sets multiple parameters at once |
| `load_instrument_or_effect` | Loads an instrument/effect via URI |

---

## 🔍 Browser

| Tool | Description |
|---|---|
| `search_browser` | Searches instruments, effects, presets, plugins |
| `get_browser_tree` | Returns the browser category tree |
| `get_browser_items_at_path` | Lists items at a given path |

---

## 🎶 Groove

| Tool | Description |
|---|---|
| `get_groove_pool` | Lists all grooves in the Groove Pool |
| `get_groove_amount` | Reads the global groove amount |
| `set_groove_amount` | Sets the global groove amount |
| `apply_groove` | Applies a groove to a Session View clip |
| `apply_groove_arrangement` | Applies a groove to an Arrangement View clip |

---

# 📦 Installation

*(Add your installation steps here — Python, WebSocket, etc.)*

---

# 🧪 Example Usage

*Change the song’s key to E Dorian for all MIDI tracks, excluding any tracks containing a Drum Rack.*

---

# 🛠️ Roadmap

- Audio clip support  
- Warp markers  
- Device preset loading  
- Track freeze/flatten  
- Return track creation  

---
