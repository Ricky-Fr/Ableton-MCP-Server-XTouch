

---

# 🚀 MCP Server for Ableton Live  
**Version 2.2 — Stable (Work in Progress)**

A lightweight, fast, and fully scriptable **MCP server** for Ableton Live.  
It exposes a complete set of tools (44 total) to control Live: session, tracks, clips, devices, browser, groove, automation, and more.

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
- Auto‑shutdown when Ableton closes
- Stable versioning system
- Precise dB curves for volume & sends
- Adds full key transposition, allowing you to shift any key to another—including modal transformations such as Dorian, Mixolydian, Lydian, and more—applied either to a single track or to the entire song.
- Many bug fixes and reliability improvements

---

# 🧰 Available Tools (44 total)

Below is the complete list of tools exposed by the MCP server.

---

## 🎛️ Session

| Tool | Description |
|---|---|
| `get_session_info` | Tempo, time signature, number of tracks, return tracks, master |
| `set_tempo` | Sets the tempo in BPM |
| `start_playback` | Starts playback |
| `stop_playback` | Stops playback |

---

## 🎹 Key & Scale

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
| `get_track_info` | Name, type, devices, and clip slots of a track |
| `create_midi_track` | Creates a new MIDI track |
| `set_track_name` | Renames a track |
| `set_track_volume` | Sets volume in dB or raw value (0.85 = 0 dB) |
| `set_track_pan` | Pan (-1.0 left … 0.0 center … 1.0 right) |
| `set_track_send` | Sets a send to a return bus (in dB or raw value) |
| `set_track_mute` | Mute / unmute |
| `set_track_solo` | Solo / unsolo |
| `set_track_arm` | Arms / disarms the track for recording |

---

## 🎼 Clips — Session View

| Tool | Description |
|---|---|
| `create_clip` | Creates a MIDI clip in a slot |
| `set_clip_name` | Renames a clip |
| `add_notes_to_clip` | Adds MIDI notes to a clip |
| `fire_clip` | Launches clip playback |
| `stop_clip` | Stops clip playback |

---

## 🎼 Clips — Arrangement View

| Tool | Description |
|---|---|
| `get_arrangement_clips` | Lists all MIDI clips on a track |
| `create_arrangement_clip` | Creates a MIDI clip at a position on the timeline |
| `set_arrangement_clip_name` | Renames a clip |
| `get_notes_arrangement` | Reads all notes from a clip |
| `add_notes_to_arrangement_clip` | Adds notes to an existing clip |
| `replace_notes_arrangement` | Replaces all notes (preserves automation & groove) |

---

## 📈 Automation & Envelopes

| Tool | Description |
|---|---|
| `set_clip_envelope_point` | Writes automation points in a Session View clip |
| `set_arrangement_envelope` | Writes automation points in an Arrangement View clip |
| `clear_clip_envelope` | Clears the envelope of a parameter in a Session View clip |

---

## 🎛️ Devices & Instruments

| Tool | Description |
|---|---|
| `get_device_parameters` | Lists all parameters of a device |
| `set_device_parameter` | Changes the value of a device parameter |
| `load_instrument_or_effect` | Loads an instrument or effect via its browser URI |
| `load_drum_kit` | Loads a Drum Rack and a specific kit |

---

## 🔍 Browser

| Tool | Description |
|---|---|
| `search_browser` | Searches instruments, effects, presets, and plugins (VST2/VST3/AU) |
| `get_browser_tree` | Returns the browser category tree |
| `get_browser_items_at_path` | Lists items at a given browser path |

---

## 🎶 Groove

| Tool | Description |
|---|---|
| `get_groove_pool` | Lists all grooves available in the Groove Pool |
| `get_groove_amount` | Reads the global groove amount (0.0 – 1.0) |
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

