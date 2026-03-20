# AbletonMCP/init.py
from __future__ import absolute_import, print_function, unicode_literals

from _Framework.ControlSurface import ControlSurface
import Live
import socket
import json
import threading
import time
import traceback

# Change queue import for Python 2
try:
    import Queue as queue  # Python 2
except ImportError:
    import queue  # Python 3

# Constants for socket communication
DEFAULT_PORT = 9877
HOST = "localhost"
REMOTE_VERSION = "2.2"

def create_instance(c_instance):
    """Create and return the AbletonMCP script instance"""
    return AbletonMCP(c_instance)

class AbletonMCP(ControlSurface):
    """AbletonMCP Remote Script for Ableton Live"""
    
    def __init__(self, c_instance):
        """Initialize the control surface"""
        ControlSurface.__init__(self, c_instance)
        self.log_message("AbletonMCP Remote Script initializing...")
        
        # Socket server for communication
        self.server = None
        self.client_threads = []
        self.server_thread = None
        self.running = False
        
        # Cache the song reference for easier access
        self._song = self.song()
        
        # Start the socket server
        self.start_server()
        
        self.log_message("AbletonMCP initialized")
        
        # Show a message in Ableton
        self.show_message("AbletonMCP: Listening for commands on port " + str(DEFAULT_PORT))
    
    def disconnect(self):
        """Called when Ableton closes or the control surface is removed"""
        self.log_message("AbletonMCP disconnecting...")
        self.running = False
        
        # Stop the server
        if self.server:
            try:
                self.server.close()
            except:
                pass
        
        # Wait for the server thread to exit
        if self.server_thread and self.server_thread.is_alive():
            self.server_thread.join(1.0)
            
        # Clean up any client threads
        for client_thread in self.client_threads[:]:
            if client_thread.is_alive():
                # We don't join them as they might be stuck
                self.log_message("Client thread still alive during disconnect")
        
        ControlSurface.disconnect(self)
        self.log_message("AbletonMCP disconnected")
    
    def start_server(self):
        """Start the socket server in a separate thread"""
        try:
            self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server.bind((HOST, DEFAULT_PORT))
            self.server.listen(5)  # Allow up to 5 pending connections
            
            self.running = True
            self.server_thread = threading.Thread(target=self._server_thread)
            self.server_thread.daemon = True
            self.server_thread.start()
            
            self.log_message("Server started on port " + str(DEFAULT_PORT))
        except Exception as e:
            self.log_message("Error starting server: " + str(e))
            self.show_message("AbletonMCP: Error starting server - " + str(e))
    
    def _server_thread(self):
        """Server thread implementation - handles client connections"""
        try:
            self.log_message("Server thread started")
            # Set a timeout to allow regular checking of running flag
            self.server.settimeout(1.0)
            
            while self.running:
                try:
                    # Accept connections with timeout
                    client, address = self.server.accept()
                    self.log_message("Connection accepted from " + str(address))
                    self.show_message(f"AbletonMCP {REMOTE_VERSION}: Client connected")
                    
                    # Handle client in a separate thread
                    client_thread = threading.Thread(
                        target=self._handle_client,
                        args=(client,)
                    )
                    client_thread.daemon = True
                    client_thread.start()
                    
                    # Keep track of client threads
                    self.client_threads.append(client_thread)
                    
                    # Clean up finished client threads
                    self.client_threads = [t for t in self.client_threads if t.is_alive()]
                    
                except socket.timeout:
                    # No connection yet, just continue
                    continue
                except Exception as e:
                    if self.running:  # Only log if still running
                        self.log_message("Server accept error: " + str(e))
                    time.sleep(0.5)
            
            self.log_message("Server thread stopped")
        except Exception as e:
            self.log_message("Server thread error: " + str(e))
    
    def _handle_client(self, client):
        """Handle communication with a connected client"""
        self.log_message("Client handler started")
        client.settimeout(None)  # No timeout for client socket
        buffer = ''  # Changed from b'' to '' for Python 2
        
        try:
            while self.running:
                try:
                    # Receive data
                    data = client.recv(8192)
                    
                    if not data:
                        # Client disconnected
                        self.log_message("Client disconnected")
                        break
                    
                    # Accumulate data in buffer with explicit encoding/decoding
                    try:
                        # Python 3: data is bytes, decode to string
                        buffer += data.decode('utf-8')
                    except AttributeError:
                        # Python 2: data is already string
                        buffer += data
                    
                    try:
                        # Try to parse command from buffer
                        command = json.loads(buffer)  # Removed decode('utf-8')
                        buffer = ''  # Clear buffer after successful parse
                        
                        self.log_message("Received command: " + str(command.get("type", "unknown")))
                        
                        # Process the command and get response
                        response = self._process_command(command)
                        
                        # Send the response with explicit encoding
                        try:
                            # Python 3: encode string to bytes
                            client.sendall(json.dumps(response).encode('utf-8'))
                        except AttributeError:
                            # Python 2: string is already bytes
                            client.sendall(json.dumps(response))
                    except ValueError:
                        # Incomplete data, wait for more
                        continue
                        
                except Exception as e:
                    self.log_message("Error handling client data: " + str(e))
                    self.log_message(traceback.format_exc())
                    
                    # Send error response if possible
                    error_response = {
                        "status": "error",
                        "message": str(e)
                    }
                    try:
                        # Python 3: encode string to bytes
                        client.sendall(json.dumps(error_response).encode('utf-8'))
                    except AttributeError:
                        # Python 2: string is already bytes
                        client.sendall(json.dumps(error_response))
                    except:
                        # If we can't send the error, the connection is probably dead
                        break
                    
                    # For serious errors, break the loop
                    if not isinstance(e, ValueError):
                        break
        except Exception as e:
            self.log_message("Error in client handler: " + str(e))
        finally:
            try:
                client.close()
            except:
                pass
            self.log_message("Client handler stopped")
    
    def _process_command(self, command):
        """Process a command from the client and return a response"""
        command_type = command.get("type", "")
        params = command.get("params", {})
        
        # Initialize response
        response = {
            "status": "success",
            "result": {}
        }
        
        try:
            # Route the command to the appropriate handler
            if command_type == "get_session_info":
                response["result"] = self._get_session_info()
            elif command_type == "get_track_info":
                track_index = params.get("track_index", 0)
                response["result"] = self._get_track_info(track_index)
            # Commands that modify Live's state should be scheduled on the main thread
            elif command_type in ["create_midi_track", "set_track_name", 
                                 "create_clip", "add_notes_to_clip", "set_clip_name", 
                                 "set_tempo", "fire_clip", "stop_clip",
                                 "start_playback", "stop_playback", "load_browser_item",
                                 "create_arrangement_clip", "add_notes_to_arrangement_clip",
                                 "set_arrangement_clip_name", "get_arrangement_clips",
                                 "set_track_volume", "set_track_pan", "set_track_send",
                                 "set_track_mute", "set_track_solo", "set_track_arm",
                                 "set_groove_amount", "apply_groove", "apply_groove_arrangement",
                                 "get_notes_arrangement", "replace_notes_arrangement"]:
                # Use a thread-safe approach with a response queue
                response_queue = queue.Queue()
                
                # Define a function to execute on the main thread
                def main_thread_task():
                    try:
                        result = None
                        if command_type == "create_midi_track":
                            index = params.get("index", -1)
                            result = self._create_midi_track(index)
                        elif command_type == "set_track_name":
                            track_index = params.get("track_index", 0)
                            name = params.get("name", "")
                            result = self._set_track_name(track_index, name)
                        elif command_type == "create_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            length = params.get("length", 4.0)
                            result = self._create_clip(track_index, clip_index, length)
                        elif command_type == "add_notes_to_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_clip(track_index, clip_index, notes)
                        elif command_type == "set_clip_name":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            name = params.get("name", "")
                            result = self._set_clip_name(track_index, clip_index, name)
                        elif command_type == "set_tempo":
                            tempo = params.get("tempo", 120.0)
                            result = self._set_tempo(tempo)
                        elif command_type == "fire_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._fire_clip(track_index, clip_index)
                        elif command_type == "stop_clip":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            result = self._stop_clip(track_index, clip_index)
                        elif command_type == "start_playback":
                            result = self._start_playback()
                        elif command_type == "stop_playback":
                            result = self._stop_playback()
                        elif command_type == "load_instrument_or_effect":
                            track_index = params.get("track_index", 0)
                            uri = params.get("uri", "")
                            result = self._load_instrument_or_effect(track_index, uri)
                        elif command_type == "load_browser_item":
                            track_index = params.get("track_index", 0)
                            item_uri = params.get("item_uri", "")
                            result = self._load_browser_item(track_index, item_uri)
                        elif command_type == "create_arrangement_clip":
                            track_index = params.get("track_index", 0)
                            position = params.get("position", 0.0)
                            length = params.get("length", 4.0)
                            result = self._create_arrangement_clip(track_index, position, length)
                        elif command_type == "add_notes_to_arrangement_clip":
                            track_index = params.get("track_index", 0)
                            position = params.get("position", 0.0)
                            notes = params.get("notes", [])
                            result = self._add_notes_to_arrangement_clip(track_index, position, notes)
                        elif command_type == "set_arrangement_clip_name":
                            track_index = params.get("track_index", 0)
                            position = params.get("position", 0.0)
                            name = params.get("name", "")
                            result = self._set_arrangement_clip_name(track_index, position, name)
                        elif command_type == "get_arrangement_clips":
                            track_index = params.get("track_index", 0)
                            result = self._get_arrangement_clips(track_index)
                        elif command_type == "set_track_volume":
                            track_index = params.get("track_index", 0)
                            volume = params.get("volume", 1.0)
                            db = params.get("db", None)
                            result = self._set_track_volume(track_index, volume, db=db)
                        elif command_type == "set_track_pan":
                            track_index = params.get("track_index", 0)
                            pan = params.get("pan", 0.0)
                            result = self._set_track_pan(track_index, pan)
                        elif command_type == "set_track_send":
                            track_index = params.get("track_index", 0)
                            send_index = params.get("send_index", 0)
                            value = params.get("value", 0.0)
                            db = params.get("db", None)
                            result = self._set_track_send(track_index, send_index, value, db=db)
                        elif command_type == "set_track_mute":
                            track_index = params.get("track_index", 0)
                            mute = params.get("mute", False)
                            result = self._set_track_mute(track_index, mute)
                        elif command_type == "set_track_solo":
                            track_index = params.get("track_index", 0)
                            solo = params.get("solo", False)
                            result = self._set_track_solo(track_index, solo)
                        elif command_type == "set_track_arm":
                            track_index = params.get("track_index", 0)
                            arm = params.get("arm", False)
                            result = self._set_track_arm(track_index, arm)
                        elif command_type == "set_groove_amount":
                            amount = params.get("amount", 1.0)
                            result = self._set_groove_amount(amount)
                        elif command_type == "apply_groove":
                            track_index = params.get("track_index", 0)
                            clip_index = params.get("clip_index", 0)
                            groove_index = params.get("groove_index", 0)
                            result = self._apply_groove(track_index, clip_index, groove_index)
                        elif command_type == "apply_groove_arrangement":
                            track_index = params.get("track_index", 0)
                            position = params.get("position", 0.0)
                            groove_index = params.get("groove_index", 0)
                            result = self._apply_groove_arrangement(track_index, position, groove_index)
                        elif command_type == "get_notes_arrangement":
                            track_index = params.get("track_index", 0)
                            position = params.get("position", 0.0)
                            result = self._get_notes_arrangement(track_index, position)
                        elif command_type == "replace_notes_arrangement":
                            track_index = params.get("track_index", 0)
                            position = params.get("position", 0.0)
                            notes = params.get("notes", [])
                            result = self._replace_notes_arrangement(track_index, position, notes)
                        
                        # Put the result in the queue
                        response_queue.put({"status": "success", "result": result})
                    except Exception as e:
                        self.log_message("Error in main thread task: " + str(e))
                        self.log_message(traceback.format_exc())
                        response_queue.put({"status": "error", "message": str(e)})
                
                # Schedule the task to run on the main thread
                try:
                    self.schedule_message(0, main_thread_task)
                except AssertionError:
                    # If we're already on the main thread, execute directly
                    main_thread_task()
                
                # Wait for the response with a timeout
                try:
                    task_response = response_queue.get(timeout=10.0)
                    if task_response.get("status") == "error":
                        response["status"] = "error"
                        response["message"] = task_response.get("message", "Unknown error")
                    else:
                        response["result"] = task_response.get("result", {})
                except queue.Empty:
                    response["status"] = "error"
                    response["message"] = "Timeout waiting for operation to complete"
            elif command_type == "set_clip_envelope_point":
                track_index  = params.get("track_index", 0)
                clip_index   = params.get("clip_index", 0)
                device_index = params.get("device_index", 0)
                param_index  = params.get("param_index", 0)
                points       = params.get("points", [])
                response["result"] = self._set_clip_envelope_point(
                    track_index, clip_index, device_index, param_index, points)
            elif command_type == "clear_clip_envelope":
                track_index  = params.get("track_index", 0)
                clip_index   = params.get("clip_index", 0)
                device_index = params.get("device_index", 0)
                param_index  = params.get("param_index", 0)
                response["result"] = self._clear_clip_envelope(
                    track_index, clip_index, device_index, param_index)
            elif command_type == "set_arrangement_envelope":
                track_index  = params.get("track_index", 0)
                position     = params.get("position", 0.0)
                device_index = params.get("device_index", 0)
                param_index  = params.get("param_index", 0)
                points       = params.get("points", [])
                response["result"] = self._set_arrangement_envelope(
                    track_index, position, device_index, param_index, points)
            elif command_type == "get_groove_amount":
                response["result"] = self._get_groove_amount()
            elif command_type == "get_groove_pool":
                response["result"] = self._get_groove_pool()
            elif command_type == "get_device_parameters":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                response["result"] = self._get_device_parameters(track_index, device_index)
            elif command_type == "set_device_parameter":
                track_index = params.get("track_index", 0)
                device_index = params.get("device_index", 0)
                parameter_index = params.get("parameter_index", 0)
                value = params.get("value", 0.0)
                response["result"] = self._set_device_parameter(track_index, device_index, parameter_index, value)
            elif command_type == "get_browser_item":
                uri = params.get("uri", None)
                path = params.get("path", None)
                response["result"] = self._get_browser_item(uri, path)
            elif command_type == "get_browser_categories":
                category_type = params.get("category_type", "all")
                response["result"] = self._get_browser_categories(category_type)
            elif command_type == "get_browser_items":
                path = params.get("path", "")
                item_type = params.get("item_type", "all")
                response["result"] = self._get_browser_items(path, item_type)
            # Add the new browser commands
            elif command_type == "get_browser_tree":
                category_type = params.get("category_type", "all")
                response["result"] = self.get_browser_tree(category_type)
            elif command_type == "get_browser_items_at_path":
                path = params.get("path", "")
                response["result"] = self.get_browser_items_at_path(path)
            elif command_type == "search_browser":
                query = params.get("query", "")
                category_type = params.get("category_type", "all")
                max_results = params.get("max_results", 20)
                response["result"] = self.search_browser(query, category_type, max_results)
            elif command_type == "get_song_key":
                response["result"] = self._get_song_key()
            elif command_type == "set_song_root_note":
                root_note = params.get("root_note", 0)
                response["result"] = self._set_song_root_note(root_note)
            elif command_type == "get_song_scale":
                response["result"] = self._get_song_scale()
            elif command_type == "set_song_scale":
                scale_name = params.get("scale_name", "major")
                response["result"] = self._set_song_scale(scale_name)
            else:
                response["status"] = "error"
                response["message"] = "Unknown command: " + command_type
        except Exception as e:
            self.log_message("Error processing command: " + str(e))
            self.log_message(traceback.format_exc())
            response["status"] = "error"
            response["message"] = str(e)
        
        return response
    
    # Command implementations
    
    def _get_session_info(self):
        """Get information about the current session"""
        try:
            result = {
                "tempo": self._song.tempo,
                "signature_numerator": self._song.signature_numerator,
                "signature_denominator": self._song.signature_denominator,
                "track_count": len(self._song.tracks),
                "return_track_count": len(self._song.return_tracks),
                "master_track": {
                    "name": "Master",
                    "volume": self._song.master_track.mixer_device.volume.value,
                    "panning": self._song.master_track.mixer_device.panning.value
                }
            }
            return result
        except Exception as e:
            self.log_message("Error getting session info: " + str(e))
            raise
    
    def _get_track_info(self, track_index):
        """Get information about a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            # Get clip slots
            clip_slots = []
            for slot_index, slot in enumerate(track.clip_slots):
                clip_info = None
                if slot.has_clip:
                    clip = slot.clip
                    clip_info = {
                        "name": clip.name,
                        "length": clip.length,
                        "is_playing": clip.is_playing,
                        "is_recording": clip.is_recording
                    }
                
                clip_slots.append({
                    "index": slot_index,
                    "has_clip": slot.has_clip,
                    "clip": clip_info
                })
            
            # Get devices
            devices = []
            for device_index, device in enumerate(track.devices):
                devices.append({
                    "index": device_index,
                    "name": device.name,
                    "class_name": device.class_name,
                    "type": self._get_device_type(device)
                })
            try:
                arm = track.arm
            except (RuntimeError, AttributeError):
                arm = False
                
            result = {
                "index": track_index,
                "name": track.name,
                "is_audio_track": track.has_audio_input,
                "is_midi_track": track.has_midi_input,
                "mute": track.mute,
                "solo": track.solo,
                "arm": arm,
                "volume": track.mixer_device.volume.value,
                "panning": track.mixer_device.panning.value,
                "clip_slots": clip_slots,
                "devices": devices
            }
            return result
        except Exception as e:
            self.log_message("Error getting track info: " + str(e))
            raise
    
    def _create_midi_track(self, index):
        """Create a new MIDI track at the specified index"""
        try:
            # Create the track
            self._song.create_midi_track(index)
            
            # Get the new track
            new_track_index = len(self._song.tracks) - 1 if index == -1 else index
            new_track = self._song.tracks[new_track_index]
            
            result = {
                "index": new_track_index,
                "name": new_track.name
            }
            return result
        except Exception as e:
            self.log_message("Error creating MIDI track: " + str(e))
            raise
    
    
    def _set_track_name(self, track_index, name):
        """Set the name of a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            # Set the name
            track = self._song.tracks[track_index]
            track.name = name
            
            result = {
                "name": track.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting track name: " + str(e))
            raise

    # -------------------------------------------------------------------------
    # dB <-> Ableton value conversion (calibrated empirically)
    # -------------------------------------------------------------------------

    # Calibration table for track fader: list of (db, ableton_value) sorted by db ascending
    VOLUME_CALIBRATION = [
        (-float('inf'), 0.000),
        (-60.0,         0.034),
        (-50.0,         0.091),
        (-40.0,         0.158),
        (-30.0,         0.238),
        (-20.0,         0.360),
        (-10.0,         0.600),
        ( -3.0,         0.775),
        (  0.0,         0.850),
        (  6.0,         1.000),
    ]

    # Calibration table for sends: list of (db, ableton_value) sorted by db ascending
    SEND_CALIBRATION = [
        (-float('inf'), 0.000),
        (-70.0,         0.000),
        (-60.0,         0.068),
        (-50.0,         0.130),
        (-40.0,         0.204),
        (-30.0,         0.302),
        (-20.0,         0.502),
        (-10.0,         0.750),
        (  0.0,         1.000),
    ]

    def _db_to_ableton(self, db, calibration):
        """Convert a dB value to an Ableton internal value using interpolation on a calibration table."""
        # Below minimum: silence
        if db <= calibration[0][0]:
            return calibration[0][1]
        # Above maximum: clamp to max
        if db >= calibration[-1][0]:
            return calibration[-1][1]
        # Find surrounding points and interpolate linearly
        for i in range(len(calibration) - 1):
            db_lo, val_lo = calibration[i]
            db_hi, val_hi = calibration[i + 1]
            if db_lo <= db <= db_hi:
                if db_hi == db_lo or db_lo == -float('inf'):
                    return val_hi
                t = (db - db_lo) / (db_hi - db_lo)
                return val_lo + t * (val_hi - val_lo)
        return calibration[-1][1]

    def _ableton_to_db(self, value, calibration):
        """Convert an Ableton internal value to dB using interpolation on a calibration table."""
        if value <= calibration[0][1]:
            return calibration[0][0]
        if value >= calibration[-1][1]:
            return calibration[-1][0]
        for i in range(len(calibration) - 1):
            db_lo, val_lo = calibration[i]
            db_hi, val_hi = calibration[i + 1]
            if val_lo <= value <= val_hi:
                if val_hi == val_lo:
                    return db_lo
                t = (value - val_lo) / (val_hi - val_lo)
                return db_lo + t * (db_hi - db_lo)
        return calibration[-1][0]

    # -------------------------------------------------------------------------

    def _set_track_volume(self, track_index, volume, db=None):
        """Set the volume of a track. If db is provided, converts dB to Ableton value automatically."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if db is not None:
                volume = self._db_to_ableton(db, self.VOLUME_CALIBRATION)
            track.mixer_device.volume.value = volume
            actual_db = self._ableton_to_db(track.mixer_device.volume.value, self.VOLUME_CALIBRATION)
            return {
                "track_index": track_index,
                "volume": track.mixer_device.volume.value,
                "db": round(actual_db, 1)
            }
        except Exception as e:
            self.log_message("Error setting track volume: " + str(e))
            raise

    def _set_track_pan(self, track_index, pan):
        """Set the panoramique (pan) of a track. pan = ableton_value (-1.0 to 1.0) or use pan_pct (-50 to +50)."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.mixer_device.panning.value = pan
            return {
                "track_index": track_index,
                "pan": track.mixer_device.panning.value,
                "pan_display": round(track.mixer_device.panning.value * 50, 1)
            }
        except Exception as e:
            self.log_message("Error setting track pan: " + str(e))
            raise

    def _set_track_send(self, track_index, send_index, value, db=None):
        """Set the send level of a track to a return bus. If db is provided, converts dB to Ableton value automatically."""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            sends = track.mixer_device.sends
            if send_index < 0 or send_index >= len(sends):
                raise IndexError(
                    "Send index {0} out of range (track has {1} send(s))".format(
                        send_index, len(sends)
                    )
                )
            if db is not None:
                value = self._db_to_ableton(db, self.SEND_CALIBRATION)
            sends[send_index].value = value
            actual_db = self._ableton_to_db(sends[send_index].value, self.SEND_CALIBRATION)
            return {
                "track_index": track_index,
                "send_index": send_index,
                "value": sends[send_index].value,
                "db": round(actual_db, 1)
            }
        except Exception as e:
            self.log_message("Error setting track send: " + str(e))
            raise

    def _set_track_mute(self, track_index, mute):
        """Mute or unmute a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.mute = bool(mute)
            return {"track_index": track_index, "mute": track.mute}
        except Exception as e:
            self.log_message("Error setting track mute: " + str(e))
            raise

    def _set_track_solo(self, track_index, solo):
        """Solo or unsolo a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            track.solo = bool(solo)
            return {"track_index": track_index, "solo": track.solo}
        except Exception as e:
            self.log_message("Error setting track solo: " + str(e))
            raise

    def _set_track_arm(self, track_index, arm):
        """Arm or disarm a track for recording"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if not track.can_be_armed:
                raise Exception("Track {0} cannot be armed".format(track_index))
            track.arm = bool(arm)
            return {"track_index": track_index, "arm": track.arm}
        except Exception as e:
            self.log_message("Error setting track arm: " + str(e))
            raise

    def _create_clip(self, track_index, clip_index, length):
        """Create a new MIDI clip in the specified track and clip slot"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            # Check if the clip slot already has a clip
            if clip_slot.has_clip:
                raise Exception("Clip slot already has a clip")
            
            # Create the clip
            clip_slot.create_clip(length)
            
            result = {
                "name": clip_slot.clip.name,
                "length": clip_slot.clip.length
            }
            return result
        except Exception as e:
            self.log_message("Error creating clip: " + str(e))
            raise
    
    def _add_notes_to_clip(self, track_index, clip_index, notes):
        """Add MIDI notes to a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip = clip_slot.clip
            
            # Convert note data to Live's format (API Live 11+)
            live_notes = []
            for note in notes:
                pitch = note.get("pitch", 60)
                start_time = note.get("start_time", 0.0)
                duration = note.get("duration", 0.25)
                velocity = note.get("velocity", 100)
                mute = note.get("mute", False)
                
                live_notes.append(Live.Clip.MidiNoteSpecification(
                    pitch=pitch,
                    start_time=start_time,
                    duration=duration,
                    velocity=velocity,
                    mute=mute
                ))
            
            # Add the notes using the modern API (Live 11+)
            clip.add_new_notes(tuple(live_notes))
            
            result = {
                "note_count": len(notes)
            }
            return result
        except Exception as e:
            self.log_message("Error adding notes to clip: " + str(e))
            raise
    
    def _set_clip_name(self, track_index, clip_index, name):
        """Set the name of a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip = clip_slot.clip
            clip.name = name
            
            result = {
                "name": clip.name
            }
            return result
        except Exception as e:
            self.log_message("Error setting clip name: " + str(e))
            raise
    
    def _set_tempo(self, tempo):
        """Set the tempo of the session"""
        try:
            self._song.tempo = tempo
            
            result = {
                "tempo": self._song.tempo
            }
            return result
        except Exception as e:
            self.log_message("Error setting tempo: " + str(e))
            raise
    
    def _fire_clip(self, track_index, clip_index):
        """Fire a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            if not clip_slot.has_clip:
                raise Exception("No clip in slot")
            
            clip_slot.fire()
            
            result = {
                "fired": True
            }
            return result
        except Exception as e:
            self.log_message("Error firing clip: " + str(e))
            raise
    
    def _stop_clip(self, track_index, clip_index):
        """Stop a clip"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            if clip_index < 0 or clip_index >= len(track.clip_slots):
                raise IndexError("Clip index out of range")
            
            clip_slot = track.clip_slots[clip_index]
            
            clip_slot.stop()
            
            result = {
                "stopped": True
            }
            return result
        except Exception as e:
            self.log_message("Error stopping clip: " + str(e))
            raise
    
    
    def _start_playback(self):
        """Start playing the session"""
        try:
            self._song.start_playing()
            
            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error starting playback: " + str(e))
            raise
    
    def _stop_playback(self):
        """Stop playing the session"""
        try:
            self._song.stop_playing()
            
            result = {
                "playing": self._song.is_playing
            }
            return result
        except Exception as e:
            self.log_message("Error stopping playback: " + str(e))
            raise
    
    def _get_browser_item(self, uri, path):
        """Get a browser item by URI or path"""
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            result = {
                "uri": uri,
                "path": path,
                "found": False
            }
            
            # Try to find by URI first if provided
            if uri:
                item = self._find_browser_item_by_uri(app.browser, uri)
                if item:
                    result["found"] = True
                    result["item"] = {
                        "name": item.name,
                        "is_folder": item.is_folder,
                        "is_device": item.is_device,
                        "is_loadable": item.is_loadable,
                        "uri": item.uri
                    }
                    return result
            
            # If URI not provided or not found, try by path
            if path:
                # Parse the path and navigate to the specified item
                path_parts = path.split("/")
                
                # Determine the root based on the first part
                current_item = None
                if path_parts[0].lower() == "nstruments":
                    current_item = app.browser.instruments
                elif path_parts[0].lower() == "sounds":
                    current_item = app.browser.sounds
                elif path_parts[0].lower() == "drums":
                    current_item = app.browser.drums
                elif path_parts[0].lower() == "audio_effects":
                    current_item = app.browser.audio_effects
                elif path_parts[0].lower() == "midi_effects":
                    current_item = app.browser.midi_effects
                else:
                    # Default to instruments if not specified
                    current_item = app.browser.instruments
                    # Don't skip the first part in this case
                    path_parts = ["instruments"] + path_parts
                
                # Navigate through the path
                for i in range(1, len(path_parts)):
                    part = path_parts[i]
                    if not part:  # Skip empty parts
                        continue
                    
                    found = False
                    for child in current_item.children:
                        if child.name.lower() == part.lower():
                            current_item = child
                            found = True
                            break
                    
                    if not found:
                        result["error"] = "Path part '{0}' not found".format(part)
                        return result
                
                # Found the item
                result["found"] = True
                result["item"] = {
                    "name": current_item.name,
                    "is_folder": current_item.is_folder,
                    "is_device": current_item.is_device,
                    "is_loadable": current_item.is_loadable,
                    "uri": current_item.uri
                }
            
            return result
        except Exception as e:
            self.log_message("Error getting browser item: " + str(e))
            self.log_message(traceback.format_exc())
            raise   
    
    
    
    def _load_browser_item(self, track_index, item_uri):
        """Load a browser item onto a track by its URI"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            
            track = self._song.tracks[track_index]
            
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            
            # Find the browser item by URI
            item = self._find_browser_item_by_uri(app.browser, item_uri)
            
            if not item:
                raise ValueError("Browser item with URI '{0}' not found".format(item_uri))
            
            # Select the track
            self._song.view.selected_track = track
            
            # Load the item
            app.browser.load_item(item)
            
            result = {
                "loaded": True,
                "item_name": item.name,
                "track_name": track.name,
                "uri": item_uri
            }
            return result
        except Exception as e:
            self.log_message("Error loading browser item: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise
    
    def _find_browser_item_by_uri(self, browser_or_item, uri, max_depth=10, current_depth=0):
        """Find a browser item by its URI - searches ALL browser categories including VST/AU plugins"""
        try:
            # Check if this is the item we're looking for
            if hasattr(browser_or_item, 'uri') and browser_or_item.uri == uri:
                return browser_or_item
            
            # Stop recursion if we've reached max depth
            if current_depth >= max_depth:
                return None
            
            # Check if this is a browser root - collect ALL available categories dynamically
            if hasattr(browser_or_item, 'instruments'):
                # Dynamically enumerate all browser attributes instead of hardcoding 5 categories
                # This ensures VST2, VST3, AU plugins and other categories are included
                skip_attrs = set([
                    'add_filter_type_listener', 'add_full_refresh_listener',
                    'add_hotswap_target_listener', 'filter_type', 'filter_type_has_listener',
                    'full_refresh_has_listener', 'hotswap_target', 'hotswap_target_has_listener',
                    'load_item', 'preview_item', 'relation_to_hotswap_target',
                    'remove_filter_type_listener', 'remove_full_refresh_listener',
                    'remove_hotswap_target_listener', 'stop_preview'
                ])
                categories = []
                for attr in dir(browser_or_item):
                    if attr.startswith('_') or attr in skip_attrs:
                        continue
                    try:
                        item = getattr(browser_or_item, attr)
                        if hasattr(item, 'children') or hasattr(item, 'name'):
                            categories.append(item)
                    except Exception:
                        continue
                
                for category in categories:
                    item = self._find_browser_item_by_uri(category, uri, max_depth, current_depth + 1)
                    if item:
                        return item
                
                return None
            
            # Check if this item has children
            if hasattr(browser_or_item, 'children') and browser_or_item.children:
                for child in browser_or_item.children:
                    item = self._find_browser_item_by_uri(child, uri, max_depth, current_depth + 1)
                    if item:
                        return item
            
            return None
        except Exception as e:
            self.log_message("Error finding browser item by URI: {0}".format(str(e)))
            return None
    
    # Helper methods
    
    def _get_device_type(self, device):
        """Get the type of a device"""
        try:
            # Simple heuristic - in a real implementation you'd look at the device class
            if device.can_have_drum_pads:
                return "drum_machine"
            elif device.can_have_chains:
                return "rack"
            elif "instrument" in device.class_display_name.lower():
                return "instrument"
            elif "audio_effect" in device.class_name.lower():
                return "audio_effect"
            elif "midi_effect" in device.class_name.lower():
                return "midi_effect"
            else:
                return "unknown"
        except:
            return "unknown"
    

    def _get_device_parameters(self, track_index, device_index):
        """Get all parameters of a device on a track"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            parameters = []
            for param_index, param in enumerate(device.parameters):
                parameters.append({
                    "index": param_index,
                    "name": param.name,
                    "value": param.value,
                    "min": param.min,
                    "max": param.max,
                    "is_quantized": param.is_quantized,
                    "value_items": list(param.value_items) if param.is_quantized else []
                })
            return {
                "track_index": track_index,
                "device_index": device_index,
                "device_name": device.name,
                "parameters": parameters
            }
        except Exception as e:
            self.log_message("Error getting device parameters: " + str(e))
            raise

    def _set_device_parameter(self, track_index, device_index, parameter_index, value):
        """Set a parameter value on a device"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            if device_index < 0 or device_index >= len(track.devices):
                raise IndexError("Device index out of range")
            device = track.devices[device_index]
            if parameter_index < 0 or parameter_index >= len(device.parameters):
                raise IndexError("Parameter index out of range")
            param = device.parameters[parameter_index]
            # Clamp value between min and max
            clamped_value = max(param.min, min(param.max, value))
            param.value = clamped_value
            return {
                "track_index": track_index,
                "device_index": device_index,
                "parameter_index": parameter_index,
                "parameter_name": param.name,
                "value": param.value
            }
        except Exception as e:
            self.log_message("Error setting device parameter: " + str(e))
            raise

    # -------------------------------------------------------------------------
    # Arrangement View functions
    # -------------------------------------------------------------------------

    def _get_arrangement_clips(self, track_index):
        """List all clips on a track in the Arrangement view"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            clips = []
            for clip in track.arrangement_clips:
                clips.append({
                    "name": clip.name,
                    "start_time": clip.start_time,
                    "end_time": clip.end_time,
                    "length": clip.length,
                    "is_midi_clip": clip.is_midi_clip
                })
            return {"track_index": track_index, "clips": clips}
        except Exception as e:
            self.log_message("Error getting arrangement clips: " + str(e))
            raise

    def _create_arrangement_clip(self, track_index, position, length):
        """Create a MIDI clip in the Arrangement view at a given position (in beats)"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            clip = track.create_midi_clip(position, length)
            return {
                "name": clip.name,
                "start_time": clip.start_time,
                "length": clip.length
            }
        except Exception as e:
            self.log_message("Error creating arrangement clip: " + str(e))
            raise

    def _add_notes_to_arrangement_clip(self, track_index, position, notes):
        """Add MIDI notes to a clip in the Arrangement view identified by its start position"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]

            # Find the clip at the given position
            clip = None
            for c in track.arrangement_clips:
                if abs(c.start_time - position) < 0.001:
                    clip = c
                    break
            if clip is None:
                raise Exception("No arrangement clip found at position " + str(position))

            # Build notes with modern API
            live_notes = []
            for note in notes:
                live_notes.append(Live.Clip.MidiNoteSpecification(
                    pitch=note.get("pitch", 60),
                    start_time=note.get("start_time", 0.0),
                    duration=note.get("duration", 0.25),
                    velocity=note.get("velocity", 100),
                    mute=note.get("mute", False)
                ))
            clip.add_new_notes(tuple(live_notes))
            return {"note_count": len(notes)}
        except Exception as e:
            self.log_message("Error adding notes to arrangement clip: " + str(e))
            raise

    def _set_arrangement_clip_name(self, track_index, position, name):
        """Rename a clip in the Arrangement view identified by its start position"""
        try:
            if track_index < 0 or track_index >= len(self._song.tracks):
                raise IndexError("Track index out of range")
            track = self._song.tracks[track_index]
            clip = None
            for c in track.arrangement_clips:
                if abs(c.start_time - position) < 0.001:
                    clip = c
                    break
            if clip is None:
                raise Exception("No arrangement clip found at position " + str(position))
            clip.name = name
            return {"name": clip.name}
        except Exception as e:
            self.log_message("Error setting arrangement clip name: " + str(e))
            raise

    def search_browser(self, query, category_type="all", max_results=20):
        """
        Search for browser items (instruments, effects, plugins) by name.
        Searches ALL categories including VST2, VST3, AU plugins.

        Args:
            query: Search string (case-insensitive, partial match)
            category_type: 'all', 'instruments', 'audio_effects', 'midi_effects',
                           'sounds', 'drums', or 'plugins' (VST/AU only)
            max_results: Maximum number of results to return (default 20)

        Returns:
            Dictionary with list of matching items and their URIs
        """
        try:
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available")

            query_lower = query.lower()
            results = []

            skip_attrs = set([
                'add_filter_type_listener', 'add_full_refresh_listener',
                'add_hotswap_target_listener', 'filter_type', 'filter_type_has_listener',
                'full_refresh_has_listener', 'hotswap_target', 'hotswap_target_has_listener',
                'load_item', 'preview_item', 'relation_to_hotswap_target',
                'remove_filter_type_listener', 'remove_full_refresh_listener',
                'remove_hotswap_target_listener', 'stop_preview'
            ])

            plugin_keywords = ['vst', 'plugin', 'au ', 'audio unit', 'plug-in']

            def _search_recursive(item, category_name, depth=0):
                if depth > 12 or len(results) >= max_results:
                    return
                item_name = item.name.lower() if hasattr(item, 'name') else ""
                if (query_lower in item_name and
                        hasattr(item, 'is_loadable') and item.is_loadable):
                    results.append({
                        "name": item.name,
                        "uri": item.uri if hasattr(item, 'uri') else None,
                        "category": category_name,
                        "is_device": hasattr(item, 'is_device') and item.is_device,
                        "is_loadable": True
                    })
                    return
                if hasattr(item, 'children'):
                    for child in item.children:
                        if len(results) >= max_results:
                            break
                        _search_recursive(child, category_name, depth + 1)

            if category_type == "plugins":
                for attr in dir(app.browser):
                    if attr.startswith('_') or attr in skip_attrs:
                        continue
                    if any(kw in attr.lower() for kw in plugin_keywords):
                        try:
                            cat = getattr(app.browser, attr)
                            if hasattr(cat, 'children') or hasattr(cat, 'name'):
                                _search_recursive(cat, attr)
                        except Exception:
                            continue
            else:
                standard_map = {
                    "instruments": ["instruments"],
                    "audio_effects": ["audio_effects"],
                    "midi_effects": ["midi_effects"],
                    "sounds": ["sounds"],
                    "drums": ["drums"],
                }
                target_attrs = standard_map.get(category_type, None)

                for attr in dir(app.browser):
                    if attr.startswith('_') or attr in skip_attrs:
                        continue
                    if target_attrs and attr not in target_attrs:
                        continue
                    try:
                        cat = getattr(app.browser, attr)
                        if hasattr(cat, 'children') or hasattr(cat, 'name'):
                            _search_recursive(cat, attr)
                    except Exception:
                        continue

            self.log_message("search_browser: '{0}' -> {1} results".format(query, len(results)))
            return {
                "query": query,
                "category_type": category_type,
                "count": len(results),
                "results": results
            }
        except Exception as e:
            self.log_message("Error in search_browser: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise

    def get_browser_tree(self, category_type="all"):
        """
        Get a simplified tree of browser categories.
        
        Args:
            category_type: Type of categories to get ('all', 'instruments', 'sounds', etc.)
            
        Returns:
            Dictionary with the browser tree structure
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))
            
            result = {
                "type": category_type,
                "categories": [],
                "available_categories": browser_attrs
            }
            
            # Helper function to process a browser item and its children
            def process_item(item, depth=0):
                if not item:
                    return None
                
                result = {
                    "name": item.name if hasattr(item, 'name') else "Unknown",
                    "is_folder": hasattr(item, 'children') and bool(item.children),
                    "is_device": hasattr(item, 'is_device') and item.is_device,
                    "is_loadable": hasattr(item, 'is_loadable') and item.is_loadable,
                    "uri": item.uri if hasattr(item, 'uri') else None,
                    "children": []
                }
                
                
                return result
            
            # Process based on category type and available attributes
            if (category_type == "all" or category_type == "instruments") and hasattr(app.browser, 'instruments'):
                try:
                    instruments = process_item(app.browser.instruments)
                    if instruments:
                        instruments["name"] = "Instruments"  # Ensure consistent naming
                        result["categories"].append(instruments)
                except Exception as e:
                    self.log_message("Error processing instruments: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "sounds") and hasattr(app.browser, 'sounds'):
                try:
                    sounds = process_item(app.browser.sounds)
                    if sounds:
                        sounds["name"] = "Sounds"  # Ensure consistent naming
                        result["categories"].append(sounds)
                except Exception as e:
                    self.log_message("Error processing sounds: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "drums") and hasattr(app.browser, 'drums'):
                try:
                    drums = process_item(app.browser.drums)
                    if drums:
                        drums["name"] = "Drums"  # Ensure consistent naming
                        result["categories"].append(drums)
                except Exception as e:
                    self.log_message("Error processing drums: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "audio_effects") and hasattr(app.browser, 'audio_effects'):
                try:
                    audio_effects = process_item(app.browser.audio_effects)
                    if audio_effects:
                        audio_effects["name"] = "Audio Effects"  # Ensure consistent naming
                        result["categories"].append(audio_effects)
                except Exception as e:
                    self.log_message("Error processing audio_effects: {0}".format(str(e)))
            
            if (category_type == "all" or category_type == "midi_effects") and hasattr(app.browser, 'midi_effects'):
                try:
                    midi_effects = process_item(app.browser.midi_effects)
                    if midi_effects:
                        midi_effects["name"] = "MIDI Effects"
                        result["categories"].append(midi_effects)
                except Exception as e:
                    self.log_message("Error processing midi_effects: {0}".format(str(e)))
            
            # Try to process other potentially available categories
            for attr in browser_attrs:
                if attr not in ['instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects'] and \
                   (category_type == "all" or category_type == attr):
                    try:
                        item = getattr(app.browser, attr)
                        if hasattr(item, 'children') or hasattr(item, 'name'):
                            category = process_item(item)
                            if category:
                                category["name"] = attr.capitalize()
                                result["categories"].append(category)
                    except Exception as e:
                        self.log_message("Error processing {0}: {1}".format(attr, str(e)))
            
            self.log_message("Browser tree generated for {0} with {1} root categories".format(
                category_type, len(result['categories'])))
            return result
            
        except Exception as e:
            self.log_message("Error getting browser tree: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise
    
    def get_browser_items_at_path(self, path):
        """
        Get browser items at a specific path.
        
        Args:
            path: Path in the format "category/folder/subfolder"
                 where category is one of: instruments, sounds, drums, audio_effects, midi_effects
                 or any other available browser category
                 
        Returns:
            Dictionary with items at the specified path
        """
        try:
            # Access the application's browser instance instead of creating a new one
            app = self.application()
            if not app:
                raise RuntimeError("Could not access Live application")
                
            # Check if browser is available
            if not hasattr(app, 'browser') or app.browser is None:
                raise RuntimeError("Browser is not available in the Live application")
            
            # Log available browser attributes to help diagnose issues
            browser_attrs = [attr for attr in dir(app.browser) if not attr.startswith('_')]
            self.log_message("Available browser attributes: {0}".format(browser_attrs))
                
            # Parse the path
            path_parts = path.split("/")
            if not path_parts:
                raise ValueError("Invalid path")
            
            # Determine the root category
            root_category = path_parts[0].lower()
            current_item = None
            
            # Check standard categories first
            if root_category == "instruments" and hasattr(app.browser, 'instruments'):
                current_item = app.browser.instruments
            elif root_category == "sounds" and hasattr(app.browser, 'sounds'):
                current_item = app.browser.sounds
            elif root_category == "drums" and hasattr(app.browser, 'drums'):
                current_item = app.browser.drums
            elif root_category == "audio_effects" and hasattr(app.browser, 'audio_effects'):
                current_item = app.browser.audio_effects
            elif root_category == "midi_effects" and hasattr(app.browser, 'midi_effects'):
                current_item = app.browser.midi_effects
            else:
                # Try to find the category in other browser attributes
                found = False
                for attr in browser_attrs:
                    if attr.lower() == root_category:
                        try:
                            current_item = getattr(app.browser, attr)
                            found = True
                            break
                        except Exception as e:
                            self.log_message("Error accessing browser attribute {0}: {1}".format(attr, str(e)))
                
                if not found:
                    # If we still haven't found the category, return available categories
                    return {
                        "path": path,
                        "error": "Unknown or unavailable category: {0}".format(root_category),
                        "available_categories": browser_attrs,
                        "items": []
                    }
            
            # Navigate through the path
            for i in range(1, len(path_parts)):
                part = path_parts[i]
                if not part:  # Skip empty parts
                    continue
                
                if not hasattr(current_item, 'children'):
                    return {
                        "path": path,
                        "error": "Item at '{0}' has no children".format('/'.join(path_parts[:i])),
                        "items": []
                    }
                
                found = False
                for child in current_item.children:
                    if hasattr(child, 'name') and child.name.lower() == part.lower():
                        current_item = child
                        found = True
                        break
                
                if not found:
                    return {
                        "path": path,
                        "error": "Path part '{0}' not found".format(part),
                        "items": []
                    }
            
            # Get items at the current path
            items = []
            if hasattr(current_item, 'children'):
                for child in current_item.children:
                    item_info = {
                        "name": child.name if hasattr(child, 'name') else "Unknown",
                        "is_folder": hasattr(child, 'children') and bool(child.children),
                        "is_device": hasattr(child, 'is_device') and child.is_device,
                        "is_loadable": hasattr(child, 'is_loadable') and child.is_loadable,
                        "uri": child.uri if hasattr(child, 'uri') else None
                    }
                    items.append(item_info)
            
            result = {
                "path": path,
                "name": current_item.name if hasattr(current_item, 'name') else "Unknown",
                "uri": current_item.uri if hasattr(current_item, 'uri') else None,
                "is_folder": hasattr(current_item, 'children') and bool(current_item.children),
                "is_device": hasattr(current_item, 'is_device') and current_item.is_device,
                "is_loadable": hasattr(current_item, 'is_loadable') and current_item.is_loadable,
                "items": items
            }
            
            self.log_message("Retrieved {0} items at path: {1}".format(len(items), path))
            return result
            
        except Exception as e:
            self.log_message("Error getting browser items at path: {0}".format(str(e)))
            self.log_message(traceback.format_exc())
            raise


    # -------------------------------------------------------------------------
    #  Groove helpers
    # -------------------------------------------------------------------------

    def _get_groove_amount(self):
        """Retourne le groove amount global de la session."""
        return {
            "groove_amount": self._song.groove_amount if hasattr(self._song, 'groove_amount') else 1.0
        }

    def _set_groove_amount(self, amount):
        """Definit le groove amount global (0.0 - 1.0)."""
        if hasattr(self._song, 'groove_amount'):
            self._song.groove_amount = max(0.0, min(1.0, float(amount)))
        return {"groove_amount": self._song.groove_amount}

    def _get_groove_pool(self):
        """Retourne la liste des grooves disponibles dans le pool."""
        if not hasattr(self._song, 'groove_pool') or not self._song.groove_pool:
            return {"error": "Groove pool not available", "grooves": []}
        grooves = []
        for i, groove in enumerate(self._song.groove_pool.grooves):
            grooves.append({
                "index": i,
                "name": groove.name if hasattr(groove, 'name') else "Groove " + str(i),
                "amount": groove.amount if hasattr(groove, 'amount') else 1.0
            })
        return {"groove_count": len(grooves), "grooves": grooves}

    def _apply_groove(self, track_index, clip_index, groove_index):
        """Applique un groove du pool sur un clip Session View."""
        track = self._song.tracks[track_index]
        slot = track.clip_slots[clip_index]
        if not slot.has_clip:
            raise RuntimeError("No clip in slot")
        clip = slot.clip
        if not hasattr(self._song, 'groove_pool') or not self._song.groove_pool:
            return {"error": "Groove pool not available"}
        grooves = list(self._song.groove_pool.grooves)
        if groove_index < 0 or groove_index >= len(grooves):
            raise IndexError("Groove index out of range: {0}".format(groove_index))
        groove = grooves[groove_index]
        if hasattr(clip, 'groove'):
            clip.groove = groove
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "groove_applied": True,
                "groove_name": groove.name if hasattr(groove, 'name') else "Groove " + str(groove_index)
            }
        return {"error": "Groove assignment not supported on this clip"}

    def _apply_groove_arrangement(self, track_index, position, groove_index):
        """Applique un groove sur un clip Arrangement View."""
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range: {0}".format(track_index))
        track = self._song.tracks[track_index]

        target_clip = None
        for clip in track.arrangement_clips:
            if abs(clip.start_time - position) < 0.01:
                target_clip = clip
                break

        if target_clip is None:
            raise RuntimeError("No arrangement clip found at position {0} on track {1}".format(position, track_index))

        if not hasattr(self._song, 'groove_pool') or not self._song.groove_pool:
            return {"error": "Groove pool not available"}

        grooves = list(self._song.groove_pool.grooves)
        if groove_index < 0 or groove_index >= len(grooves):
            raise IndexError("Groove index out of range: {0}".format(groove_index))

        groove = grooves[groove_index]
        if hasattr(target_clip, 'groove'):
            target_clip.groove = groove
            return {
                "track_index": track_index,
                "clip_position": position,
                "groove_applied": True,
                "groove_name": groove.name if hasattr(groove, 'name') else "Groove " + str(groove_index)
            }
        return {"error": "Groove assignment not supported on this clip"}

    def _get_notes_arrangement(self, track_index, position):
        """Lit toutes les notes MIDI d'un clip Arrangement View."""
        self._song = self.song()
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range: {0}".format(track_index))
        track = self._song.tracks[track_index]
        target_clip = None
        for clip in track.arrangement_clips:
            if abs(clip.start_time - position) < 0.01:
                target_clip = clip
                break
        if target_clip is None:
            raise RuntimeError("No arrangement clip found at position {0} on track {1}".format(position, track_index))

        # get_notes retourne des tuples (pitch, start_time, duration, velocity, mute)
        raw_notes = target_clip.get_notes(0, 0, target_clip.length, 128)
        notes = [
            {
                "pitch":      int(n[0]),
                "start_time": float(n[1]),
                "duration":   float(n[2]),
                "velocity":   int(n[3]),
                "mute":       bool(n[4])
            }
            for n in raw_notes
        ]
        return {
            "track_index":   track_index,
            "clip_position": position,
            "clip_length":   target_clip.length,
            "note_count":    len(notes),
            "notes":         notes
        }

    def _replace_notes_arrangement(self, track_index, position, notes):
        """
        Replace all MIDI notes in an Arrangement clip without touching automation or groove.
        Uses remove_notes_extended (Live 11+) to clear only notes, then add_new_notes to write.
        """
        self._song = self.song()
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range: {0}".format(track_index))

        track = self._song.tracks[track_index]

        # Find the clip at the given position
        target_clip = None
        for clip in track.arrangement_clips:
            if abs(clip.start_time - position) < 0.01:
                target_clip = clip
                break

        if target_clip is None:
            raise RuntimeError("No arrangement clip found at position {0} on track {1}".format(position, track_index))

        if not target_clip.is_midi_clip:
            raise RuntimeError("Clip at position {0} is not a MIDI clip".format(position))

        # Remove all existing notes (Live 11 API)
        # time_span = length + 1 pour couvrir toutes les notes sans exception
        target_clip.remove_notes_extended(from_time=0, from_pitch=0, time_span=target_clip.length + 1, pitch_span=128)

        # Build new notes and write them (Live 11 API)
        new_notes = tuple(
            Live.Clip.MidiNoteSpecification(
                pitch=int(n.get("pitch", 60)),
                start_time=float(n.get("start_time", 0.0)),
                duration=float(n.get("duration", 0.25)),
                velocity=int(n.get("velocity", 100)),
                mute=bool(n.get("mute", False))
            )
            for n in notes
        )
        target_clip.add_new_notes(new_notes)

        return {
            "replaced": True,
            "track_index": track_index,
            "clip_position": position,
            "note_count": len(new_notes)
        }

    # -------------------------------------------------------------------------
    #  Automation helpers
    # -------------------------------------------------------------------------

    def _get_param_for_envelope(self, track_index, device_index, param_index):
        """
        Retourne un Live.DeviceParameter pour l'automation.
        device_index :
            -1  -> volume
            -2  -> pan
            -3  -> send (param_index = index du send)
            >=0 -> device index normal (récursif dans les racks)
        """

        # --- Vérification piste ---
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError(f"Track index out of range: {track_index}")

        track = self._song.tracks[track_index]

        # --- Volume ---
        if device_index == -1:
            return track.mixer_device.volume

        # --- Pan ---
        if device_index == -2:
            return track.mixer_device.panning

        # --- Sends ---
        if device_index == -3:
            if param_index < 0 or param_index >= len(track.mixer_device.sends):
                raise IndexError(f"Send index out of range: {param_index}")
            return track.mixer_device.sends[param_index]

        # --- Devices normaux ---
        if device_index < 0:
            raise IndexError(f"Invalid device index: {device_index}")

        # Récupération device (avec support des racks)
        device = self._get_device_recursive(track.devices, device_index)

        if param_index < 0 or param_index >= len(device.parameters):
            raise IndexError(f"Parameter index out of range: {param_index}")

        return device.parameters[param_index]

    def _get_device_recursive(self, devices, index):
        """
        Retourne un device en parcourant récursivement les racks.
        """
        flat = []

        def flatten(dev_list):
            for d in dev_list:
                flat.append(d)
                if hasattr(d, "chains"):
                    for chain in d.chains:
                        flatten(chain.devices)

        flatten(devices)

        if index < 0 or index >= len(flat):
            raise IndexError(f"Device index out of range (recursive): {index}")

        return flat[index]

    def _set_clip_envelope_point(self, track_index, clip_index, device_index, param_index, points):
        """
        Definit une liste de points d'automation pour un parametre dans un clip Session View.
        Si 'points' est vide, efface l'enveloppe.
        """
        self._song = self.song()
        track = self._song.tracks[track_index]
        slot = track.clip_slots[clip_index]

        if not slot.has_clip:
            return {"error": "No clip in slot"}

        clip = slot.clip
        param = self._get_param_for_envelope(track_index, device_index, param_index)

        try:
            clip.view.show_envelope()
        except:
            pass

        env = clip.automation_envelope(param)
        if env is None:
            if hasattr(clip, 'create_automation_envelope'):
                env = clip.create_automation_envelope(param)

        if env is None:
            return {
                "error": "Parameter '{0}' cannot be automated in this clip.".format(param.name),
                "track_index": track_index,
                "clip_index": clip_index,
                "param_name": param.name
            }

        # Effacer les points existants
        if hasattr(env, 'clear'):
            env.clear()
        else:
            try:
                env.delete_events_in_range(-100.0, clip.length + 100.0)
            except:
                pass

        if not points:
            return {
                "track_index": track_index,
                "clip_index": clip_index,
                "param_name": param.name,
                "cleared": True
            }

        # Inserer les points avec insert_value si disponible, sinon insert_step
        if hasattr(env, 'insert_value'):
            for p in points:
                env.insert_value(p["time"], p["value"])
        else:
            for p in reversed(points):
                env.insert_step(p["time"], 0.0, p["value"])

        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "param_name": param.name,
            "points_written": len(points)
        }
    def _clear_clip_envelope(self, track_index, clip_index, device_index, param_index):
        """
        Efface l'enveloppe d'automation d'un parametre dans un clip Session View.
        """
        self._song = self.song()
        track = self._song.tracks[track_index]
        slot = track.clip_slots[clip_index]

        if not slot.has_clip:
            return {"error": "No clip in slot"}

        clip = slot.clip
        param = self._get_param_for_envelope(track_index, device_index, param_index)
        env = clip.automation_envelope(param)

        if env is None:
            return {
                "error": "Parameter '{0}' cannot be automated in this clip.".format(param.name),
                "track_index": track_index,
                "clip_index": clip_index,
                "param_name": param.name
            }

        try:
            env.delete_events_in_range(0.0, clip.length)
        except:
            pass

        return {
            "track_index": track_index,
            "clip_index": clip_index,
            "param_name": param.name,
            "cleared": True
        }
    def _set_arrangement_envelope(self, track_index, position, device_index, param_index, points):
        """
        Ecrit des points d'automation dans un clip Arrangement View.
        """
        self._song = self.song()
        if track_index < 0 or track_index >= len(self._song.tracks):
            raise IndexError("Track index out of range: {0}".format(track_index))
        track = self._song.tracks[track_index]

        target_clip = None
        for clip in track.arrangement_clips:
            if abs(clip.start_time - position) < 0.01:
                target_clip = clip
                break

        if target_clip is None:
            raise RuntimeError("No arrangement clip found at position {0} on track {1}".format(position, track_index))

        param = self._get_param_for_envelope(track_index, device_index, param_index)
        envelope = target_clip.automation_envelope(param)

        if envelope is None:
            raise RuntimeError("Cannot get automation envelope for param '{0}' - envelope is None".format(param.name))

        try:
            envelope.delete_events_in_range(0.0, target_clip.length)
        except:
            pass

        for pt in points:
            t = float(pt.get("time", 0.0))
            v = float(pt.get("value", 0.0))
            envelope.insert_step(t, 0.0, v)

        return {
            "track_index":    track_index,
            "clip_position":  position,
            "device_index":   device_index,
            "param_index":    param_index,
            "points_written": len(points),
            "param_name":     param.name
        }

    # -------------------------------------------------------------------------
    #  Song key / scale helpers
    # -------------------------------------------------------------------------

    def _get_song_key(self):
        """Get the song's root note and scale"""
        try:
            root_note = self._song.root_note if hasattr(self._song, 'root_note') else None
            scale_name = self._song.scale_name if hasattr(self._song, 'scale_name') else "Unknown"
            NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
            return {
                "root_note": root_note,
                "root_name": NOTE_NAMES[root_note % 12] if root_note is not None else None,
                "scale_name": scale_name
            }
        except Exception as e:
            self.log_message("Error getting song key: " + str(e))
            return {"error": str(e)}

    def _set_song_root_note(self, root_note):
        """Set the song's root note (0-11, C=0)"""
        try:
            self._song.root_note = root_note % 12
            return {"success": True, "root_note": self._song.root_note}
        except Exception as e:
            self.log_message("Error setting song root note: " + str(e))
            return {"error": str(e)}

    def _get_song_scale(self):
        """Get the song's scale mode"""
        try:
            scale_mode = self._song.scale_mode if hasattr(self._song, 'scale_mode') else None
            scale_name = self._song.scale_name if hasattr(self._song, 'scale_name') else "Unknown"
            return {
                "scale_mode": scale_mode,
                "scale_name": scale_name
            }
        except Exception as e:
            self.log_message("Error getting song scale: " + str(e))
            return {"error": str(e)}

    def _set_song_scale(self, scale_name):
        """Set the song's scale by name"""
        try:
            self._song.scale_name = scale_name
            return {
                "success": True,
                "scale_name": self._song.scale_name
            }
        except Exception as e:
            self.log_message("Error setting song scale: " + str(e))
            return {"error": str(e)}
