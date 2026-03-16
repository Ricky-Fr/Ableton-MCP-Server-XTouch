---

# 🚧 MCP Server — Work in Progress

## 📦 Version **1.7** (stable, in progress)

### ✨ New Features & Improvements
- 📌 **Added versioning**
- 🛑 **Server now automatically stops** when Ableton is not running or has been closed
- 🎛️ **Clip creation in Arrangement View**
- 🔧 **Access to plugin parameters**
- 🎚️ **Mute, Solo & Arm control**
- 🎛️ **Load & manage internal and external plugins**
- 📈 **Precise volume and send curves handling (in dB)**
- 🐞 **Minor bug fixes**

---
Available  functions

**Session**
- `get_session_info` — tempo, signature, nombre de tracks
- `set_tempo` — changer le BPM
- `start_playback` / `stop_playback` — play/stop global

**Tracks**
- `get_track_info` — détails d'une track (devices, clips, paramètres)
- `create_midi_track` — créer une nouvelle track MIDI
- `set_track_name` — renommer une track
- `set_track_volume` — volume en dB ou valeur raw
- `set_track_pan` — panoramique (-1.0 à 1.0)
- `set_track_mute` / `set_track_solo` / `set_track_arm` — mute, solo, arm
- `set_track_send` — niveau d'un send (en dB ou valeur raw)

**Devices & Paramètres**
- `get_device_parameters` — lister tous les paramètres d'un device
- `set_device_parameter` — modifier un paramètre (valeur normalisée 0.0–1.0)
- `load_instrument_or_effect` — charger un instrument/effet via URI
- `load_drum_kit` — charger un drum rack + kit

**Clips (Session View)**
- `create_clip` — créer un clip MIDI dans un slot
- `add_notes_to_clip` — ajouter des notes MIDI
- `fire_clip` / `stop_clip` — déclencher/stopper un clip
- `set_clip_name` — renommer un clip
- `set_clip_envelope_points` — automatiser un paramètre dans un clip
- `clear_clip_envelope` — effacer une automation de clip

**Clips (Arrangement View)**
- `create_arrangement_clip` — créer un clip à une position timeline
- `add_notes_to_arrangement_clip` — ajouter des notes
- `set_arrangement_clip_name` — renommer
- `set_arrangement_envelope` — écrire des points d'automation

**Browser**
- `search_browser` — chercher instruments/effets/VSTs
- `get_browser_tree` — arborescence du browser
- `get_browser_items_at_path` — items à un chemin précis
