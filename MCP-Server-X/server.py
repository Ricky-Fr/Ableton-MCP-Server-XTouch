# ableton_mcp_server.py
from mcp.server.fastmcp import FastMCP, Context
import socket
import json
import logging
import asyncio
import sys
import os
import signal
from dataclasses import dataclass
from contextlib import asynccontextmanager
from typing import AsyncIterator, Dict, Any, List, Union

# Configure logging
logging.basicConfig(level=logging.INFO, 
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AbletonMCPServer")

SERVER_VERSION = "2.3"
print(f"==========================================")
print(f"  AbletonMCP Server - Version {SERVER_VERSION}")
print(f"==========================================")
logger.info(f"AbletonMCP Server version {SERVER_VERSION} starting...")

@dataclass
class AbletonConnection:
    host: str
    port: int
    sock: socket.socket = None
    
    def connect(self) -> bool:
        """Connect to the Ableton Remote Script socket server"""
        if self.sock:
            return True
            
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.connect((self.host, self.port))
            logger.info(f"Connected to Ableton at {self.host}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Ableton: {str(e)}")
            self.sock = None
            return False
    
    def disconnect(self):
        """Disconnect from the Ableton Remote Script"""
        if self.sock:
            try:
                self.sock.close()
            except Exception as e:
                logger.error(f"Error disconnecting from Ableton: {str(e)}")
            finally:
                self.sock = None

    def receive_full_response(self, sock, buffer_size=8192):
        """Receive the complete response, potentially in multiple chunks"""
        chunks = []
        sock.settimeout(15.0)  # Increased timeout for operations that might take longer
        
        try:
            while True:
                try:
                    chunk = sock.recv(buffer_size)
                    if not chunk:
                        if not chunks:
                            raise Exception("Connection closed before receiving any data")
                        break
                    
                    chunks.append(chunk)
                    
                    # Check if we've received a complete JSON object
                    try:
                        data = b''.join(chunks)
                        json.loads(data.decode('utf-8'))
                        logger.info(f"Received complete response ({len(data)} bytes)")
                        return data
                    except json.JSONDecodeError:
                        # Incomplete JSON, continue receiving
                        continue
                except socket.timeout:
                    logger.warning("Socket timeout during chunked receive")
                    break
                except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Socket connection error during receive: {str(e)}")
                    raise
        except Exception as e:
            logger.error(f"Error during receive: {str(e)}")
            raise
            
        # If we get here, we either timed out or broke out of the loop
        if chunks:
            data = b''.join(chunks)
            logger.info(f"Returning data after receive completion ({len(data)} bytes)")
            try:
                json.loads(data.decode('utf-8'))
                return data
            except json.JSONDecodeError:
                raise Exception("Incomplete JSON response received")
        else:
            raise Exception("No data received")

    def send_command(self, command_type: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Send a command to Ableton and return the response"""
        if not self.sock and not self.connect():
            raise ConnectionError("Not connected to Ableton")
        
        command = {
            "type": command_type,
            "params": params or {}
        }
        
        # Check if this is a state-modifying command
        is_modifying_command = command_type in [
            "create_midi_track", "create_audio_track", "set_track_name",
            "create_clip", "add_notes_to_clip", "set_clip_name",
            "set_tempo", "fire_clip", "stop_clip", "set_device_parameter",
            "start_playback", "stop_playback", "load_instrument_or_effect",
            "create_arrangement_clip", "add_notes_to_arrangement_clip",
            "set_arrangement_clip_name", "get_arrangement_clips",
            "set_track_volume", "set_track_pan", "set_track_send",
            "set_clip_envelope_point", "clear_clip_envelope", "set_arrangement_envelope",
            "replace_notes_arrangement",
            "get_notes_clip", "replace_notes_clip", "get_view_mode"
        ]

        # Commandes lentes (browser) : timeout étendu à 30s
        is_slow_command = command_type in [
            "search_browser", "get_browser_tree", "get_browser_items_at_path",
            "load_browser_item"
        ]
        
        try:
            logger.info(f"Sending command: {command_type} with params: {params}")
            
            # Send the command
            self.sock.sendall(json.dumps(command).encode('utf-8'))
            logger.info(f"Command sent, waiting for response...")
            
            # For state-modifying commands, add a small delay to give Ableton time to process
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay
            
            # Set timeout based on command type
            timeout = 30.0 if is_slow_command else (15.0 if is_modifying_command else 10.0)
            self.sock.settimeout(timeout)
            
            # Receive the response
            response_data = self.receive_full_response(self.sock)
            logger.info(f"Received {len(response_data)} bytes of data")
            
            # Parse the response
            response = json.loads(response_data.decode('utf-8'))
            logger.info(f"Response parsed, status: {response.get('status', 'unknown')}")
            
            if response.get("status") == "error":
                logger.error(f"Ableton error: {response.get('message')}")
                raise Exception(response.get("message", "Unknown error from Ableton"))
            
            # For state-modifying commands, add another small delay after receiving response
            if is_modifying_command:
                import time
                time.sleep(0.1)  # 100ms delay
            
            return response.get("result", {})
        except socket.timeout:
            logger.error("Socket timeout while waiting for response from Ableton")
            self.sock = None
            raise Exception("Timeout waiting for Ableton response")
        except (ConnectionError, BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Socket connection error: {str(e)}")
            self.sock = None
            raise Exception(f"Connection to Ableton lost: {str(e)}")
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON response from Ableton: {str(e)}")
            if 'response_data' in locals() and response_data:
                logger.error(f"Raw response (first 200 bytes): {response_data[:200]}")
            self.sock = None
            raise Exception(f"Invalid response from Ableton: {str(e)}")
        except Exception as e:
            logger.error(f"Error communicating with Ableton: {str(e)}")
            self.sock = None
            raise Exception(f"Communication error with Ableton: {str(e)}")

async def _ableton_watchdog():
    """Background task: vérifie toutes les 5s que le Remote Script Ableton est toujours actif."""
    await asyncio.sleep(5)  # Laisser le serveur démarrer complètement
    logger.info("Ableton watchdog started")
    while True:
        await asyncio.sleep(5)
        global _ableton_connection
        if _ableton_connection is None:
            continue
        try:
            # Ping silencieux sans log
            if _ableton_connection.sock is None:
                raise ConnectionError("Socket is None")
            _ableton_connection.sock.settimeout(2.0)
            _ableton_connection.sock.sendall(b'')
        except Exception:
            print("")
            print("==========================================")
            print("  Remote script not started              ")
            print("  Ableton déconnecté - arrêt du serveur  ")
            print("==========================================")
            logger.error("Ableton connection lost - shutting down server")
            try:
                _ableton_connection.disconnect()
            except:
                pass
            _ableton_connection = None
            os.kill(os.getpid(), signal.SIGTERM)
            return

@asynccontextmanager
async def server_lifespan(server: FastMCP) -> AsyncIterator[Dict[str, Any]]:
    """Manage server startup and shutdown lifecycle"""
    try:
        logger.info("AbletonMCP server starting up")

        # Vérification obligatoire au démarrage : Ableton doit être lancé
        try:
            ableton = get_ableton_connection()
            logger.info("Successfully connected to Ableton on startup")
        except Exception as e:
            print("")
            print("==========================================")
            print("  Remote script not started              ")
            print("  Lancez Ableton avant de démarrer le    ")
            print("  serveur MCP.                           ")
            print("==========================================")
            # Désactiver les logs et quitter sans traceback
            logging.disable(logging.CRITICAL)
            os.kill(os.getpid(), signal.SIGTERM)
            await asyncio.sleep(5)
            return

        # Démarrage du watchdog en arrière-plan
        watchdog_task = asyncio.create_task(_ableton_watchdog())

        yield {}
    finally:
        global _ableton_connection
        if _ableton_connection:
            logger.info("Disconnecting from Ableton on shutdown")
            _ableton_connection.disconnect()
            _ableton_connection = None
        logger.info("AbletonMCP server shut down")

# Create the MCP server with lifespan support
mcp = FastMCP(
    "AbletonMCP",
    lifespan=server_lifespan
)

# Global connection for resources
_ableton_connection = None

def get_ableton_connection():
    """Get or create a persistent Ableton connection"""
    global _ableton_connection
    
    if _ableton_connection is not None:
        try:
            # Test the connection with a simple ping
            # We'll try to send an empty message, which should fail if the connection is dead
            # but won't affect Ableton if it's alive
            _ableton_connection.sock.settimeout(1.0)
            _ableton_connection.sock.sendall(b'')
            return _ableton_connection
        except Exception as e:
            logger.warning(f"Existing connection is no longer valid: {str(e)}")
            try:
                _ableton_connection.disconnect()
            except:
                pass
            _ableton_connection = None
    
    # Connection doesn't exist or is invalid, create a new one
    if _ableton_connection is None:
        # Try to connect up to 3 times with a short delay between attempts
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                logger.info(f"Connecting to Ableton (attempt {attempt}/{max_attempts})...")
                _ableton_connection = AbletonConnection(host="localhost", port=9877)
                if _ableton_connection.connect():
                    logger.info("Created new persistent connection to Ableton")
                    
                    # Validate connection with a simple command
                    try:
                        # Get session info as a test
                        _ableton_connection.send_command("get_session_info")
                        logger.info("Connection validated successfully")
                        return _ableton_connection
                    except Exception as e:
                        logger.error(f"Connection validation failed: {str(e)}")
                        _ableton_connection.disconnect()
                        _ableton_connection = None
                        # Continue to next attempt
                else:
                    _ableton_connection = None
            except Exception as e:
                logger.error(f"Connection attempt {attempt} failed: {str(e)}")
                if _ableton_connection:
                    _ableton_connection.disconnect()
                    _ableton_connection = None
            
            # Wait before trying again, but only if we have more attempts left
            if attempt < max_attempts:
                import time
                time.sleep(1.0)
        
        # If we get here, all connection attempts failed
        if _ableton_connection is None:
            logger.error("Failed to connect to Ableton after multiple attempts")
            raise Exception("Could not connect to Ableton. Make sure the Remote Script is running.")
    
    return _ableton_connection


# Core Tool endpoints

@mcp.tool()
def get_device_parameters(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get all parameters of a device on a track.

    Parameters:
    - track_index: The index of the track
    - device_index: The index of the device on the track (0 = first device)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_device_parameters", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting device parameters: {str(e)}")
        return f"Error getting device parameters: {str(e)}"

@mcp.tool()
def set_device_parameter(ctx: Context, track_index: int, device_index: int, parameter_index: int, value: float) -> str:
    """
    Set a parameter value on a device.

    Parameters:
    - track_index: The index of the track
    - device_index: The index of the device on the track
    - parameter_index: The index of the parameter to modify
    - value: The new value (will be clamped between min and max automatically)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "parameter_index": parameter_index,
            "value": value
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting device parameter: {str(e)}")
        return f"Error setting device parameter: {str(e)}"

@mcp.tool()
def get_session_info(ctx: Context) -> str:
    """Get detailed information about the current Ableton session"""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_session_info")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting session info from Ableton: {str(e)}")
        return f"Error getting session info: {str(e)}"

@mcp.tool()
def get_track_info(ctx: Context, track_index: int) -> str:
    """
    Get detailed information about a specific track in Ableton.
    
    Parameters:
    - track_index: The index of the track to get information about
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_track_info", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting track info from Ableton: {str(e)}")
        return f"Error getting track info: {str(e)}"

@mcp.tool()
def create_midi_track(ctx: Context, index: int = -1) -> str:
    """
    Create a new MIDI track in the Ableton session.
    
    Parameters:
    - index: The index to insert the track at (-1 = end of list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_midi_track", {"index": index})
        return f"Created new MIDI track: {result.get('name', 'unknown')}"
    except Exception as e:
        logger.error(f"Error creating MIDI track: {str(e)}")
        return f"Error creating MIDI track: {str(e)}"


@mcp.tool()
def set_track_name(ctx: Context, track_index: int, name: str) -> str:
    """
    Set the name of a track.
    
    Parameters:
    - track_index: The index of the track to rename
    - name: The new name for the track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_name", {"track_index": track_index, "name": name})
        return f"Renamed track to: {result.get('name', name)}"
    except Exception as e:
        logger.error(f"Error setting track name: {str(e)}")
        return f"Error setting track name: {str(e)}"

@mcp.tool()
def set_track_volume(ctx: Context, track_index: int, volume: float = None, db: float = None) -> str:
    """
    Set the volume of a track.

    Parameters:
    - track_index: The index of the track
    - volume: Raw Ableton volume value (0.0 = silence, 0.85 = 0 dB, 1.0 = +6 dB).
              Use this only if you know the exact internal value.
    - db: Volume in dB. Preferred over volume. Examples: 0 (= 0 dB), -3, -10, -inf (silence).
          Range: -inf (silence) to +6 dB max. The Remote Script converts dB to Ableton value automatically.

    Note: provide either db or volume, db takes priority.
    """
    try:
        ableton = get_ableton_connection()
        params = {"track_index": track_index}
        if db is not None:
            if db == -float('inf') or db <= -999:
                # Silence: bypass Remote Script conversion, set directly to 0.0
                params["volume"] = 0.0
            else:
                params["db"] = db
                params["volume"] = 1.0  # ignored by Remote Script when db is set
        elif volume is not None:
            params["volume"] = volume
        else:
            raise ValueError("Provide either db or volume")
        result = ableton.send_command("set_track_volume", params)
        if db is not None:
            return f"Set volume of track {track_index} to {db} dB"
        return f"Set volume of track {track_index} to {volume}"
    except Exception as e:
        logger.error(f"Error setting track volume: {str(e)}")
        return f"Error setting track volume: {str(e)}"

@mcp.tool()
def set_track_pan(ctx: Context, track_index: int, pan: float) -> str:
    """
    Set the panoramique (pan) of a track.

    Parameters:
    - track_index: The index of the track
    - pan: Pan value between -1.0 (full left) and 1.0 (full right). 0.0 = center.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_pan", {
            "track_index": track_index,
            "pan": pan
        })
        return f"Set pan of track {track_index} to {pan}"
    except Exception as e:
        logger.error(f"Error setting track pan: {str(e)}")
        return f"Error setting track pan: {str(e)}"

@mcp.tool()
def set_track_send(ctx: Context, track_index: int, send_index: int, value: float = None, db: float = None) -> str:
    """
    Set the send level of a track to a return/aux bus.

    Parameters:
    - track_index: The index of the source track
    - send_index: The index of the send (0 = Send A, 1 = Send B, etc.)
    - value: Raw Ableton send value (0.0 = off, 1.0 = 0 dB).
             Use this only if you know the exact internal value.
    - db: Send level in dB. Preferred over value. Examples: 0 (= 0 dB), -7, -inf (off).
          The Remote Script converts dB to Ableton value automatically.

    Note: provide either db or value, db takes priority.
    """
    try:
        ableton = get_ableton_connection()
        params = {"track_index": track_index, "send_index": send_index}
        if db is not None:
            if db == -float('inf') or db <= -999:
                # Silence: bypass Remote Script conversion, set directly to 0.0
                params["value"] = 0.0
            else:
                params["db"] = db
                params["value"] = 0.0  # ignored by Remote Script when db is set
        elif value is not None:
            params["value"] = value
        else:
            raise ValueError("Provide either db or value")
        result = ableton.send_command("set_track_send", params)
        if db is not None:
            return f"Set send {send_index} of track {track_index} to {db} dB"
        return f"Set send {send_index} of track {track_index} to {value}"
    except Exception as e:
        logger.error(f"Error setting track send: {str(e)}")
        return f"Error setting track send: {str(e)}"

@mcp.tool()
def set_track_mute(ctx: Context, track_index: int, mute: bool) -> str:
    """
    Mute or unmute a track.

    Parameters:
    - track_index: The index of the track
    - mute: True to mute the track, False to unmute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_mute", {
            "track_index": track_index,
            "mute": mute
        })
        state = "muted" if mute else "unmuted"
        return f"Track {track_index} {state}"
    except Exception as e:
        logger.error(f"Error setting track mute: {str(e)}")
        return f"Error setting track mute: {str(e)}"

@mcp.tool()
def set_track_solo(ctx: Context, track_index: int, solo: bool) -> str:
    """
    Solo or unsolo a track.

    Parameters:
    - track_index: The index of the track
    - solo: True to solo the track, False to unsolo
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_solo", {
            "track_index": track_index,
            "solo": solo
        })
        state = "soloed" if solo else "unsoloed"
        return f"Track {track_index} {state}"
    except Exception as e:
        logger.error(f"Error setting track solo: {str(e)}")
        return f"Error setting track solo: {str(e)}"

@mcp.tool()
def set_track_arm(ctx: Context, track_index: int, arm: bool) -> str:
    """
    Arm or disarm a track for recording.

    Parameters:
    - track_index: The index of the track
    - arm: True to arm the track for recording, False to disarm
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_track_arm", {
            "track_index": track_index,
            "arm": arm
        })
        state = "armed" if arm else "disarmed"
        return f"Track {track_index} {state}"
    except Exception as e:
        logger.error(f"Error setting track arm: {str(e)}")
        return f"Error setting track arm: {str(e)}"

@mcp.tool()
def create_clip(ctx: Context, track_index: int, clip_index: int, length: float = 4.0) -> str:
    """
    Create a new MIDI clip in the specified track and clip slot.
    
    Parameters:
    - track_index: The index of the track to create the clip in
    - clip_index: The index of the clip slot to create the clip in
    - length: The length of the clip in beats (default: 4.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_clip", {
            "track_index": track_index, 
            "clip_index": clip_index, 
            "length": length
        })
        return f"Created new clip at track {track_index}, slot {clip_index} with length {length} beats"
    except Exception as e:
        logger.error(f"Error creating clip: {str(e)}")
        return f"Error creating clip: {str(e)}"

@mcp.tool()
def add_notes_to_clip(
    ctx: Context, 
    track_index: int, 
    clip_index: int, 
    notes: List[Dict[str, Union[int, float, bool]]]
) -> str:
    """
    Add MIDI notes to a clip.
    
    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("add_notes_to_clip", {
            "track_index": track_index,
            "clip_index": clip_index,
            "notes": notes
        })
        return f"Added {len(notes)} notes to clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error adding notes to clip: {str(e)}")
        return f"Error adding notes to clip: {str(e)}"

@mcp.tool()
def set_clip_name(ctx: Context, track_index: int, clip_index: int, name: str) -> str:
    """
    Set the name of a clip.
    
    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    - name: The new name for the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_name", {
            "track_index": track_index,
            "clip_index": clip_index,
            "name": name
        })
        return f"Renamed clip at track {track_index}, slot {clip_index} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting clip name: {str(e)}")
        return f"Error setting clip name: {str(e)}"

@mcp.tool()
def set_tempo(ctx: Context, tempo: float) -> str:
    """
    Set the tempo of the Ableton session.
    
    Parameters:
    - tempo: The new tempo in BPM
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_tempo", {"tempo": tempo})
        return f"Set tempo to {tempo} BPM"
    except Exception as e:
        logger.error(f"Error setting tempo: {str(e)}")
        return f"Error setting tempo: {str(e)}"


@mcp.tool()
def load_instrument_or_effect(ctx: Context, track_index: int, uri: str) -> str:
    """
    Load an instrument or effect onto a track using its URI.
    
    Parameters:
    - track_index: The index of the track to load the instrument on
    - uri: The URI of the instrument or effect to load (e.g., 'query:Synths#Instrument%20Rack:Bass:FileId_5116')
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": uri
        })
        
        # Check if the instrument was loaded successfully
        if result.get("loaded", False):
            new_devices = result.get("new_devices", [])
            if new_devices:
                return f"Loaded instrument with URI '{uri}' on track {track_index}. New devices: {', '.join(new_devices)}"
            else:
                devices = result.get("devices_after", [])
                return f"Loaded instrument with URI '{uri}' on track {track_index}. Devices on track: {', '.join(devices)}"
        else:
            return f"Failed to load instrument with URI '{uri}'"
    except Exception as e:
        logger.error(f"Error loading instrument by URI: {str(e)}")
        return f"Error loading instrument by URI: {str(e)}"

@mcp.tool()
def fire_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Start playing a clip.
    
    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("fire_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Started playing clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error firing clip: {str(e)}")
        return f"Error firing clip: {str(e)}"

@mcp.tool()
def stop_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Stop playing a clip.
    
    Parameters:
    - track_index: The index of the track containing the clip
    - clip_index: The index of the clip slot containing the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_clip", {
            "track_index": track_index,
            "clip_index": clip_index
        })
        return f"Stopped clip at track {track_index}, slot {clip_index}"
    except Exception as e:
        logger.error(f"Error stopping clip: {str(e)}")
        return f"Error stopping clip: {str(e)}"

@mcp.tool()
def start_playback(ctx: Context) -> str:
    """Start playing the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("start_playback")
        return "Started playback"
    except Exception as e:
        logger.error(f"Error starting playback: {str(e)}")
        return f"Error starting playback: {str(e)}"

@mcp.tool()
def stop_playback(ctx: Context) -> str:
    """Stop playing the Ableton session."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("stop_playback")
        return "Stopped playback"
    except Exception as e:
        logger.error(f"Error stopping playback: {str(e)}")
        return f"Error stopping playback: {str(e)}"

@mcp.tool()
def search_browser(ctx: Context, query: str, category_type: str = "all", max_results: int = 20) -> str:
    """
    Search for instruments, effects, or plugins by name in Ableton's browser.
    Searches ALL categories including VST2, VST3, and AU third-party plugins.

    Parameters:
    - query: Name to search for (case-insensitive partial match, e.g. 'Serum', 'Pro-Q', 'Massive')
    - category_type: Where to search:
        'all'          - everything (default)
        'instruments'  - instruments & synths only
        'audio_effects'- audio effects only
        'midi_effects' - MIDI effects only
        'sounds'       - sounds/presets only
        'drums'        - drum kits only
        'plugins'      - third-party VST/AU plugins only
    - max_results: Maximum number of results (default 20)

    Returns a list of matching items with their URIs.
    Use the URI with load_instrument_or_effect to load the plugin onto a track.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("search_browser", {
            "query": query,
            "category_type": category_type,
            "max_results": max_results
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error searching browser: {str(e)}")
        return f"Error searching browser: {str(e)}"


@mcp.tool()
def get_browser_tree(ctx: Context, category_type: str = "all") -> str:
    """
    Get a hierarchical tree of browser categories from Ableton.
    
    Parameters:
    - category_type: Type of categories to get ('all', 'instruments', 'sounds', 'drums', 'audio_effects', 'midi_effects')
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_tree", {
            "category_type": category_type
        })
        
        # Check if we got any categories
        if "available_categories" in result and len(result.get("categories", [])) == 0:
            available_cats = result.get("available_categories", [])
            return (f"No categories found for '{category_type}'. "
                   f"Available browser categories: {', '.join(available_cats)}")
        
        # Format the tree in a more readable way
        total_folders = result.get("total_folders", 0)
        formatted_output = f"Browser tree for '{category_type}' (showing {total_folders} folders):\n\n"
        
        def format_tree(item, indent=0):
            output = ""
            if item:
                prefix = "  " * indent
                name = item.get("name", "Unknown")
                path = item.get("path", "")
                has_more = item.get("has_more", False)
                
                # Add this item
                output += f"{prefix}• {name}"
                if path:
                    output += f" (path: {path})"
                if has_more:
                    output += " [...]"
                output += "\n"
                
                # Add children
                for child in item.get("children", []):
                    output += format_tree(child, indent + 1)
            return output
        
        # Format each category
        for category in result.get("categories", []):
            formatted_output += format_tree(category)
            formatted_output += "\n"
        
        return formatted_output
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        else:
            logger.error(f"Error getting browser tree: {error_msg}")
            return f"Error getting browser tree: {error_msg}"

@mcp.tool()
def get_browser_items_at_path(ctx: Context, path: str) -> str:
    """
    Get browser items at a specific path in Ableton's browser.
    
    Parameters:
    - path: Path in the format "category/folder/subfolder"
            where category is one of the available browser categories in Ableton
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_browser_items_at_path", {
            "path": path
        })
        
        # Check if there was an error with available categories
        if "error" in result and "available_categories" in result:
            error = result.get("error", "")
            available_cats = result.get("available_categories", [])
            return (f"Error: {error}\n"
                   f"Available browser categories: {', '.join(available_cats)}")
        
        return json.dumps(result, indent=2)
    except Exception as e:
        error_msg = str(e)
        if "Browser is not available" in error_msg:
            logger.error(f"Browser is not available in Ableton: {error_msg}")
            return f"Error: The Ableton browser is not available. Make sure Ableton Live is fully loaded and try again."
        elif "Could not access Live application" in error_msg:
            logger.error(f"Could not access Live application: {error_msg}")
            return f"Error: Could not access the Ableton Live application. Make sure Ableton Live is running and the Remote Script is loaded."
        elif "Unknown or unavailable category" in error_msg:
            logger.error(f"Invalid browser category: {error_msg}")
            return f"Error: {error_msg}. Please check the available categories using get_browser_tree."
        elif "Path part" in error_msg and "not found" in error_msg:
            logger.error(f"Path not found: {error_msg}")
            return f"Error: {error_msg}. Please check the path and try again."
        else:
            logger.error(f"Error getting browser items at path: {error_msg}")
            return f"Error getting browser items at path: {error_msg}"

@mcp.tool()
def load_drum_kit(ctx: Context, track_index: int, rack_uri: str, kit_path: str) -> str:
    """
    Load a drum rack and then load a specific drum kit into it.
    
    Parameters:
    - track_index: The index of the track to load on
    - rack_uri: The URI of the drum rack to load (e.g., 'Drums/Drum Rack')
    - kit_path: Path to the drum kit inside the browser (e.g., 'drums/acoustic/kit1')
    """
    try:
        ableton = get_ableton_connection()
        
        # Step 1: Load the drum rack
        result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": rack_uri
        })
        
        if not result.get("loaded", False):
            return f"Failed to load drum rack with URI '{rack_uri}'"
        
        # Step 2: Get the drum kit items at the specified path
        kit_result = ableton.send_command("get_browser_items_at_path", {
            "path": kit_path
        })
        
        if "error" in kit_result:
            return f"Loaded drum rack but failed to find drum kit: {kit_result.get('error')}"
        
        # Step 3: Find a loadable drum kit
        kit_items = kit_result.get("items", [])
        loadable_kits = [item for item in kit_items if item.get("is_loadable", False)]
        
        if not loadable_kits:
            return f"Loaded drum rack but no loadable drum kits found at '{kit_path}'"
        
        # Step 4: Load the first loadable kit
        kit_uri = loadable_kits[0].get("uri")
        load_result = ableton.send_command("load_browser_item", {
            "track_index": track_index,
            "item_uri": kit_uri
        })
        
        return f"Loaded drum rack and kit '{loadable_kits[0].get('name')}' on track {track_index}"
    except Exception as e:
        logger.error(f"Error loading drum kit: {str(e)}")
        return f"Error loading drum kit: {str(e)}"


@mcp.tool()
def get_arrangement_clips(ctx: Context, track_index: int) -> str:
    """
    List all clips on a track in the Arrangement view.

    Parameters:
    - track_index: The index of the track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_arrangement_clips", {"track_index": track_index})
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting arrangement clips: {str(e)}")
        return f"Error getting arrangement clips: {str(e)}"

@mcp.tool()
def create_arrangement_clip(ctx: Context, track_index: int, position: float, length: float = 4.0) -> str:
    """
    Create a new MIDI clip in the Arrangement view at a given position on the timeline.

    Parameters:
    - track_index: The index of the track
    - position: Start position in beats on the Arrangement timeline
    - length: Length of the clip in beats (default: 4.0)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("create_arrangement_clip", {
            "track_index": track_index,
            "position": position,
            "length": length
        })
        return f"Created arrangement clip at track {track_index}, position {position}, length {length} beats"
    except Exception as e:
        logger.error(f"Error creating arrangement clip: {str(e)}")
        return f"Error creating arrangement clip: {str(e)}"

@mcp.tool()
def add_notes_to_arrangement_clip(
    ctx: Context,
    track_index: int,
    position: float,
    notes: List[Dict[str, Union[int, float, bool]]]
) -> str:
    """
    Add MIDI notes to a clip in the Arrangement view.

    Parameters:
    - track_index: The index of the track
    - position: Start position in beats of the target clip on the Arrangement timeline
    - notes: List of note dictionaries, each with pitch, start_time, duration, velocity, and mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("add_notes_to_arrangement_clip", {
            "track_index": track_index,
            "position": position,
            "notes": notes
        })
        return f"Added {len(notes)} notes to arrangement clip at track {track_index}, position {position}"
    except Exception as e:
        logger.error(f"Error adding notes to arrangement clip: {str(e)}")
        return f"Error adding notes to arrangement clip: {str(e)}"

@mcp.tool()
def set_arrangement_clip_name(ctx: Context, track_index: int, position: float, name: str) -> str:
    """
    Set the name of a clip in the Arrangement view.

    Parameters:
    - track_index: The index of the track
    - position: Start position in beats of the target clip on the Arrangement timeline
    - name: The new name for the clip
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_clip_name", {
            "track_index": track_index,
            "position": position,
            "name": name
        })
        return f"Renamed arrangement clip at track {track_index}, position {position} to '{name}'"
    except Exception as e:
        logger.error(f"Error setting arrangement clip name: {str(e)}")
        return f"Error setting arrangement clip name: {str(e)}"

@mcp.tool()
def set_clip_envelope_point(
    ctx: Context,
    track_index: int,
    clip_index: int,
    device_index: int,
    param_index: int,
    points: List[Dict[str, float]]
) -> str:
    """
    Définit une liste de points d'automation pour un paramètre dans un clip Session View.
    Si 'points' est vide, efface l'enveloppe.

    Parameters:
    - track_index:  Index de la piste (0-based)
    - clip_index:   Index du slot de clip (0-based)
    - device_index: Index du device. Utiliser -1 pour le volume, -2 pour le pan, -3 pour les sends.
    - param_index:  Index du paramètre dans le device (ignoré si device_index < 0)
    - points:       Liste de {"time": <beats relatifs au début du clip>, "value": <0.0-1.0>}
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_envelope_point", {
            "track_index":  track_index,
            "clip_index":   clip_index,
            "device_index": device_index,
            "param_index":  param_index,
            "points":       points
        })
        if result.get("cleared"):
            return (
                f"Cleared automation envelope on track {track_index}, "
                f"clip {clip_index}, param '{result.get('param_name', param_index)}'"
            )
        return (
            f"Wrote {result.get('points_written', len(points))} automation point(s) on track {track_index}, "
            f"clip {clip_index}, param '{result.get('param_name', param_index)}'"
        )
    except Exception as e:
        logger.error(f"Error setting clip envelope point: {str(e)}")
        return f"Error setting clip envelope point: {str(e)}"
@mcp.tool()
def clear_clip_envelope(
    ctx: Context,
    track_index: int,
    clip_index: int,
    device_index: int,
    param_index: int
) -> str:
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("clear_clip_envelope", {
            "track_index":  track_index,
            "clip_index":   clip_index,
            "device_index": device_index,
            "param_index":  param_index
        })

        return (
            f"Cleared automation envelope on track {track_index}, "
            f"clip {clip_index}, param '{result.get('param_name', param_index)}'"
        )

    except Exception as e:
        logger.error(f"Error clearing clip envelope: {str(e)}")
        return f"Error clearing clip envelope: {str(e)}"

@mcp.tool()
def set_arrangement_envelope(
    ctx: Context,
    track_index: int,
    position: float,
    device_index: int,
    param_index: int,
    points: List[Dict[str, float]]
) -> str:
    """
    Write automation points into an Arrangement View clip envelope.

    Parameters:
    - track_index:  Index of the track (0-based)
    - position:     Start position of the target clip in beats on the Arrangement timeline
    - device_index: Index of the device on the track.
                    Use -1 for track volume fader, -2 for track panning.
    - param_index:  Index of the parameter inside the device (ignored if device_index < 0)
    - points:       List of {"time": <beats relative to clip start>, "value": <0.0-1.0>}

    Example — automate filter cutoff (param 3) on device 0, clip at beat 8:
      points = [
          {"time": 0.0, "value": 0.2},
          {"time": 2.0, "value": 0.8},
          {"time": 4.0, "value": 0.2}
      ]
      set_arrangement_envelope(1, 8.0, 0, 3, points)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_arrangement_envelope", {
            "track_index":  track_index,
            "position":     position,
            "device_index": device_index,
            "param_index":  param_index,
            "points":       points
        })
        return (
            f"Wrote {len(points)} automation point(s) on track {track_index}, "
            f"arrangement clip at beat {position}, "
            f"param '{result.get('param_name', param_index)}'"
        )
    except Exception as e:
        logger.error(f"Error writing arrangement envelope: {str(e)}")
        return f"Error writing arrangement envelope: {str(e)}"


@mcp.tool()
def add_automation_ramp(
    ctx: Context,
    track_index: int,
    clip_index: int,
    device_index: int,
    param_index: int,
    start_time: float,
    end_time: float,
    start_value: float,
    end_value: float,
    curve: str = "linear",
    resolution: float = 0.25
) -> str:
    """
    Cree une rampe d'automation lisse entre deux points dans un clip Session View.
    Genere automatiquement des points intermediaires pour eviter les bookends de insert_step.

    Parameters:
    - track_index:   Index de la piste (0-based)
    - clip_index:    Index du slot de clip (0-based)
    - device_index:  Index du device (-1=volume, -2=pan, -3=send, >=0=device)
    - param_index:   Index du parametre dans le device
    - start_time:    Beat de debut de la rampe (relatif au debut du clip)
    - end_time:      Beat de fin de la rampe
    - start_value:   Valeur normalisee au debut (entre min et max du parametre)
    - end_value:     Valeur normalisee a la fin
    - curve:         Type de courbe: "linear", "exponential", "logarithmic"
    - resolution:    Pas entre les points en beats (defaut: 0.25 = double croche)

    Exemple - fade out sur 4 beats:
      add_automation_ramp(1, 0, 1, 9, 0.0, 4.0, 0.0, -1.0, "linear", 0.25)
    """
    import math

    try:
        duration = end_time - start_time
        if duration <= 0:
            return "Error: end_time must be greater than start_time"

        num_steps = max(2, int(duration / resolution))
        points = []

        for i in range(num_steps + 1):
            t = i / float(num_steps)  # 0.0 a 1.0

            # Courbe
            if curve == "exponential":
                k = 3.0
                t_curved = (math.exp(k * t) - 1) / (math.exp(k) - 1)
            elif curve == "logarithmic":
                k = 3.0
                t_curved = math.log(1 + k * t) / math.log(1 + k)
            else:  # linear
                t_curved = t

            value = start_value + (end_value - start_value) * t_curved
            beat = start_time + t * duration

            points.append({"time": round(beat, 4), "value": round(value, 6), "duration": resolution})

        ableton = get_ableton_connection()
        result = ableton.send_command("set_clip_envelope_point", {
            "track_index":  track_index,
            "clip_index":   clip_index,
            "device_index": device_index,
            "param_index":  param_index,
            "points":       points
        })

        return (
            f"Ramp created on track {track_index}, clip {clip_index}, "
            f"param '{result.get('param_name', param_index)}': "
            f"{start_value} -> {end_value} over {duration} beats "
            f"({len(points)} points, curve={curve})"
        )
    except Exception as e:
        logger.error(f"Error creating automation ramp: {str(e)}")
        return f"Error creating automation ramp: {str(e)}"



@mcp.tool()
def get_groove_amount(ctx: Context) -> str:
    """Get the global groove amount of the session (0.0 to 1.0)."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_groove_amount")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting groove amount: {str(e)}"

@mcp.tool()
def set_groove_amount(ctx: Context, amount: float) -> str:
    """
    Set the global groove amount of the session.

    Parameters:
    - amount: Groove amount between 0.0 and 1.0
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_groove_amount", {"amount": amount})
        return f"Groove amount set to {result.get('groove_amount', amount)}"
    except Exception as e:
        return f"Error setting groove amount: {str(e)}"

@mcp.tool()
def get_groove_pool(ctx: Context) -> str:
    """Get the list of available grooves in the groove pool."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_groove_pool")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting groove pool: {str(e)}"

@mcp.tool()
def apply_groove(ctx: Context, track_index: int, clip_index: int, groove_index: int) -> str:
    """
    Apply a groove from the pool to a Session View clip.

    Parameters:
    - track_index:   Index of the track (0-based)
    - clip_index:    Index of the clip slot (0-based)
    - groove_index:  Index of the groove in the groove pool (use get_groove_pool to list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("apply_groove", {
            "track_index": track_index,
            "clip_index": clip_index,
            "groove_index": groove_index
        })
        return f"Groove '{result.get('groove_name', groove_index)}' applied to track {track_index}, clip {clip_index}"
    except Exception as e:
        return f"Error applying groove: {str(e)}"

@mcp.tool()
def apply_groove_arrangement(ctx: Context, track_index: int, position: float, groove_index: int) -> str:
    """
    Apply a groove from the pool to an Arrangement View clip.

    Parameters:
    - track_index:   Index of the track (0-based)
    - position:      Start position of the target clip in beats on the Arrangement timeline
    - groove_index:  Index of the groove in the groove pool (use get_groove_pool to list)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("apply_groove_arrangement", {
            "track_index":  track_index,
            "position":     position,
            "groove_index": groove_index
        })
        return (
            f"Groove '{result.get('groove_name', groove_index)}' applied to "
            f"track {track_index}, arrangement clip at beat {position}"
        )
    except Exception as e:
        logger.error(f"Error applying groove to arrangement clip: {str(e)}")
        return f"Error applying groove to arrangement clip: {str(e)}"


@mcp.tool()
def get_notes_arrangement(ctx: Context, track_index: int, position: float) -> str:
    """
    Read all MIDI notes from an Arrangement View clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - position:    Start position of the target clip in beats on the Arrangement timeline
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_notes_arrangement", {
            "track_index": track_index,
            "position":    position
        })
        import json
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting notes from arrangement clip: {str(e)}")
        return f"Error getting notes from arrangement clip: {str(e)}"
        
@mcp.tool()
def replace_notes_arrangement(
    ctx: Context,
    track_index: int,
    position: float,
    notes: List[Dict[str, Any]]
) -> str:
    """
    Replace all MIDI notes in an Arrangement View clip, preserving automation and groove.
    Clears existing notes then writes the new ones in a single operation.

    Parameters:
    - track_index: Index of the track (0-based)
    - position:    Start position of the clip in beats on the Arrangement timeline
    - notes:       List of note dicts with pitch, start_time, duration, velocity, mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("replace_notes_arrangement", {
            "track_index": track_index,
            "position":    position,
            "notes":       notes
        })
        return (
            f"Replaced notes in arrangement clip at track {track_index}, beat {position}: "
            f"{result.get('note_count', 0)} note(s) written."
        )
    except Exception as e:
        logger.error(f"Error replacing notes in arrangement clip: {str(e)}")
        return f"Error replacing notes in arrangement clip: {str(e)}"


@mcp.tool()
def get_song_key(ctx: Context) -> str:
    """Get the song's current root note and scale name."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_song_key")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting song key: {str(e)}"


@mcp.tool()
def set_song_root_note(ctx: Context, root_note: int) -> str:
    """
    Set the song's root note.

    Parameters:
    - root_note: Integer 0-11 (C=0, C#=1, D=2, D#=3, E=4, F=5, F#=6, G=7, G#=8, A=9, A#=10, B=11)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_song_root_note", {"root_note": root_note})
        return f"Root note set to {result.get('root_note')}"
    except Exception as e:
        return f"Error setting root note: {str(e)}"


@mcp.tool()
def get_song_scale(ctx: Context) -> str:
    """Get the song's current scale mode and name."""
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_song_scale")
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"Error getting song scale: {str(e)}"


@mcp.tool()
def set_song_scale(ctx: Context, scale_name: str) -> str:
    """
    Set the song's scale by name.

    Parameters:
    - scale_name: Name of the scale (e.g. "major", "minor", "dorian", "phrygian", etc.)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_song_scale", {"scale_name": scale_name})
        return f"Scale set to {result.get('scale_name')}"
    except Exception as e:
        return f"Error setting scale: {str(e)}"


@mcp.tool()
def get_view_mode(ctx: Context) -> str:
    """
    Return the currently visible view in Ableton: Session or Arrangement.
    Always call this before any clip operation to route to the correct mode.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_view_mode")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting view mode: {str(e)}")
        return f"Error getting view mode: {str(e)}"


@mcp.tool()
def get_notes_clip(ctx: Context, track_index: int, clip_index: int) -> str:
    """
    Read all MIDI notes from a Session View clip.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index:  Index of the clip slot (0-based)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_notes_clip", {
            "track_index": track_index,
            "clip_index":  clip_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting notes from clip: {str(e)}")
        return f"Error getting notes from clip: {str(e)}"


@mcp.tool()
def replace_notes_clip(
    ctx: Context,
    track_index: int,
    clip_index: int,
    notes: List[Dict[str, Any]]
) -> str:
    """
    Replace all MIDI notes in a Session View clip, preserving automation and groove.
    Clears existing notes then writes the new ones in a single operation.

    Parameters:
    - track_index: Index of the track (0-based)
    - clip_index:  Index of the clip slot (0-based)
    - notes:       List of note dicts with pitch, start_time, duration, velocity, mute
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("replace_notes_clip", {
            "track_index": track_index,
            "clip_index":  clip_index,
            "notes":       notes
        })
        return (
            f"Replaced notes in clip at track {track_index}, slot {clip_index}: "
            f"{result.get('note_count', 0)} note(s) written."
        )
    except Exception as e:
        logger.error(f"Error replacing notes in clip: {str(e)}")
        return f"Error replacing notes in clip: {str(e)}"


@mcp.tool()
def get_selected_track(ctx: Context) -> str:
    """
    Return the index and name of the currently selected track in Ableton.
    Useful to avoid hardcoding track indices when the user has already selected the target.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_selected_track")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting selected track: {str(e)}")
        return f"Error getting selected track: {str(e)}"


@mcp.tool()
def get_selected_device(ctx: Context) -> str:
    """
    Return the index and name of the currently selected device on the selected track.
    Also returns the track_index so it can be used directly with other tools.
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_selected_device")
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting selected device: {str(e)}")
        return f"Error getting selected device: {str(e)}"

@mcp.tool()
def get_rack_chains(ctx: Context, track_index: int, device_index: int) -> str:
    """
    Get chains and devices inside a rack device (Instrument Rack, Audio Effect Rack, etc.).
    Returns all chains with their devices and parameters.

    Parameters:
    - track_index: The index of the track
    - device_index: The index of the rack device on the track
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_rack_chains", {
            "track_index": track_index,
            "device_index": device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting rack chains: {str(e)}")
        return f"Error getting rack chains: {str(e)}"


@mcp.tool()
def get_rack_chain_device_parameters(
    ctx: Context,
    track_index: int,
    device_index: int,
    chain_index: int,
    chain_device_index: int
) -> str:
    """
    Get all parameters of a plugin/device nested inside a rack chain.
    Use this when a plugin has more than 16 parameters — wrap it in a rack
    and use this tool to access all of its parameters.

    Parameters:
    - track_index:        Index of the track (0-based)
    - device_index:       Index of the rack on the track (0-based)
    - chain_index:        Index of the chain inside the rack (0-based)
    - chain_device_index: Index of the device inside that chain (0-based)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("get_rack_chain_device_parameters", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "chain_device_index": chain_device_index
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error getting rack chain device parameters: {str(e)}")
        return f"Error getting rack chain device parameters: {str(e)}"


@mcp.tool()
def set_rack_chain_device_parameter(
    ctx: Context,
    track_index: int,
    device_index: int,
    chain_index: int,
    chain_device_index: int,
    parameter_index: int,
    value: float
) -> str:
    """
    Set a parameter on a plugin/device nested inside a rack chain.
    Use this when a plugin has more than 16 parameters — wrap it in a rack
    and use this tool to modify any of its parameters.

    Parameters:
    - track_index:        Index of the track (0-based)
    - device_index:       Index of the rack on the track (0-based)
    - chain_index:        Index of the chain inside the rack (0-based)
    - chain_device_index: Index of the device inside that chain (0-based)
    - parameter_index:    Index of the parameter to set (0-based)
    - value:              New value (clamped to the parameter's min/max automatically)
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_rack_chain_device_parameter", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "chain_device_index": chain_device_index,
            "parameter_index": parameter_index,
            "value": value
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting rack chain device parameter: {str(e)}")
        return f"Error setting rack chain device parameter: {str(e)}"


@mcp.tool()
def set_rack_chain_device_parameters(
    ctx: Context,
    track_index: int,
    device_index: int,
    chain_index: int,
    chain_device_index: int,
    parameters: List[Dict[str, Any]]
) -> str:
    """
    Set multiple parameters at once on a plugin/device nested inside a rack chain.
    More efficient than calling set_rack_chain_device_parameter repeatedly.

    Parameters:
    - track_index:        Index of the track (0-based)
    - device_index:       Index of the rack on the track (0-based)
    - chain_index:        Index of the chain inside the rack (0-based)
    - chain_device_index: Index of the device inside that chain (0-based)
    - parameters:         List of {parameter_index: int, value: float} dicts

    Example:
      parameters = [
        {"parameter_index": 3, "value": 0.75},
        {"parameter_index": 7, "value": 0.5}
      ]
    """
    try:
        ableton = get_ableton_connection()
        result = ableton.send_command("set_rack_chain_device_parameters", {
            "track_index": track_index,
            "device_index": device_index,
            "chain_index": chain_index,
            "chain_device_index": chain_device_index,
            "parameters": parameters
        })
        return json.dumps(result, indent=2)
    except Exception as e:
        logger.error(f"Error setting rack chain device parameters: {str(e)}")
        return f"Error setting rack chain device parameters: {str(e)}"


# Main execution
def main():
    """Run the MCP server"""
    mcp.run()

if __name__ == "__main__":
    main()