# Ableton-MCP-Server-XTouch
Advanced MCP Server for Ableton x XTouch with CLAUDE AI DESKTOP

---

## 🚀 Project Pitch

A new project designed to connect **Anthropic’s Claude AI** to **Ableton Live**, with the long‑term goal of integrating it seamlessly with my **Behringer XTouch Mini** control surface.  
The system builds on solid foundations:  
- **uisato / MCP Server for Ableton**

**Please, for my server installation, see uisato repository. I will do a complete manual later**

---

With an **MPC server**, you can query and control Ableton Live using artificial intelligence.  
Just speak naturally, and the system will create or modify your session for you.

For example, you can say:

> **“Create a guitar track with two bars of MIDI notes in the style of Radiohead’s *Creep*, add a long reverb, and load the Nylon Guitar instrument.”**
> 
> **“Change the song’s key to E Dorian for all MIDI tracks, excluding any tracks containing a Drum Rack.”**

The server will automatically:
- create the track,  
- generate the MIDI,  
- load the instrument,  
- apply the effects,  
- and configure everything instantly.

---

For now, my MCP server runs independently with CLAUDE AI. The XTouch part will only be considered later and will remain optional.

The idea is to extend uisato’s script by adding:  
- missing features,  
- internal optimizations (including caching),  
- while preserving the existing socket‑based communication.

The final step will be adapting the server so it can communicate directly with the **XTouch Mini**.
Honestly… I still don’t know where i am going. Just exploring, experimenting, and seeing how far this AI + Ableton + hardware hybrid can go.

---

# ✨ Features (v2.4)

- Full session control (tempo, playback, time signature)
- Track management (volume, pan, sends, mute/solo/arm, colors)
- MIDI clip creation in Session & Arrangement View
- Device parameter access (internal & external plugins)
- Drum Rack & instrument loading
- Browser search (instruments, effects, presets, VST2/VST3/AU)
- Automation writing (Session & Arrangement)
- Groove Pool integration
- Key & scale reading and transformation
- Modal transposition (major, minor, dorian, phrygian, melodic minor modes, harmonic minor modes, diminished, whole tone, pentatonics, blues…)
- Arrangement clip batch processing
- Precise dB curves for volume & sends
- Auto‑shutdown when Ableton closes
- Thread‑safe main‑thread scheduling
- Reliability improvements and watchdog monitoring

---

## 🚀 A New Hybrid Instrument: X‑Touch Mini × MCP Server × AI × Ableton Live

I’m developing a groundbreaking system that connects a physical **X‑Touch Mini** controller with an **MCP server** and an **AI engine** directly linked to **Ableton Live**.  
This fusion creates a completely new category of musical tool — a **hybrid instrument** where hardware, software, and intelligence work together in real time.

By combining tactile control, deep session access through MCP, and the creative power of AI, this project opens the door to **a new generation of music‑making workflows**: adaptive controls, intelligent automation, context‑aware mappings, real‑time analysis, and creative suggestions that evolve with the music.

This is more than a controller setup.  
It’s the beginning of a **smart, responsive, AI‑augmented instrument** — and the possibilities are enormous.


![Demo](https://github.com/Ricky-Fr/Ableton-MCP-Server-XTouch/blob/main/demo-1.png?raw=true)

---
