"""WebSocket generator

Connect to LLM services via WebSocket protocol. This generator enables garak
to test WebSocket-based LLM services that use real-time bidirectional communication.

The WebSocket generator supports:
- Custom authentication (Basic Auth, API keys, custom headers)
- WebSocket frame parsing and message reconstruction
- Configurable response patterns and timing
- SSH tunnel compatibility for secure remote testing

Example usage:

.. code-block:: python

   import garak.generators.websocket

   g = garak.generators.websocket.WebSocketGenerator(
       endpoint="ws://localhost:3000/",
       auth_type="basic",
       username="user",
       password="pass",
       api_key="your_api_key",
       conversation_id="conversation_uuid"
   )

This generator was developed and tested with production WebSocket LLM services.
"""

import socket
import time
import base64
import os
import logging
from typing import List, Union, Dict, Any, Optional
from urllib.parse import urlparse

from garak import _config
from garak.attempt import Message, Conversation
from garak.generators.base import Generator

logger = logging.getLogger(__name__)


class WebSocketGenerator(Generator):
    """Generator for WebSocket-based LLM services
    
    This generator connects to LLM services that communicate via WebSocket protocol,
    handling authentication, frame parsing, and response reconstruction.
    
    Configuration parameters:
    - endpoint: WebSocket URL (ws:// or wss://)
    - auth_type: Authentication method ('basic', 'bearer', 'custom')
    - username/password: For basic authentication
    - api_key: API key parameter
    - conversation_id: Session/conversation identifier
    - custom_headers: Additional headers for WebSocket handshake
    - response_timeout: Timeout for response waiting (default: 15 seconds)
    - typing_indicators: List of frames to ignore (default: ['typing on', 'typing off'])
    - response_after_typing: Whether response comes after typing indicators (default: True)
    """

    DEFAULT_PARAMS = {
        "endpoint": None,
        "auth_type": "basic",  # 'basic', 'bearer', 'custom'
        "username": None,
        "password": None,
        "api_key": None,
        "conversation_id": None,
        "custom_headers": {},
        "response_timeout": 15,
        "typing_indicators": ["typing on", "typing off"],
        "response_after_typing": True,
        "max_message_length": 1000,
    }

    generator_family_name = "websocket"
    supports_multiple_generations = False
    active = True

    def __init__(self, name="websocket", config_root=_config, **kwargs):
        # Call parent __init__ first (this handles _load_config)
        super().__init__(name, config_root=config_root)
        
        # Set defaults from DEFAULT_PARAMS
        for key, value in self.DEFAULT_PARAMS.items():
            if not hasattr(self, key):
                setattr(self, key, value)
        
        # Override with provided kwargs (CLI parameters come through here)
        for key, value in kwargs.items():
            setattr(self, key, value)
        
        # Validate required parameters
        if not hasattr(self, 'endpoint') or not self.endpoint:
            raise ValueError("WebSocket endpoint is required")
        
        # Parse endpoint
        parsed = urlparse(self.endpoint)
        self.host = parsed.hostname or "localhost"
        self.port = parsed.port or (443 if parsed.scheme == "wss" else 80)
        self.path = parsed.path or "/"
        self.query = parsed.query
        
        # Setup authentication
        self._setup_auth()
        
        logger.info(f"WebSocket generator initialized for {self.host}:{self.port}")

    def _setup_auth(self):
        """Setup authentication headers based on auth_type"""
        self.auth_header = None
        
        if self.auth_type == "basic" and self.username and self.password:
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode('ascii')
            self.auth_header = f"Basic {credentials}"
        elif self.auth_type == "bearer" and self.api_key:
            self.auth_header = f"Bearer {self.api_key}"

    def _create_websocket_connection(self) -> socket.socket:
        """Create WebSocket connection with proper handshake"""
        try:
            # Generate WebSocket key
            key = base64.b64encode(os.urandom(16)).decode()
            
            # Build query parameters
            query_params = []
            if self.query:
                query_params.append(self.query)
            if self.api_key:
                query_params.append(f"password={self.api_key}")
            if self.conversation_id:
                query_params.append(f"conversation_id={self.conversation_id}")
            
            query_string = "&".join(query_params)
            path = f"{self.path}?{query_string}" if query_string else self.path
            
            # Build WebSocket handshake request
            request_lines = [
                f"GET {path} HTTP/1.1",
                f"Host: {self.host}:{self.port}",
                "Upgrade: websocket",
                "Connection: Upgrade",
                f"Sec-WebSocket-Key: {key}",
                "Sec-WebSocket-Version: 13"
            ]
            
            # Add authentication header if configured
            if self.auth_header:
                request_lines.append(f"Authorization: {self.auth_header}")
            
            # Add custom headers
            for header_name, header_value in self.custom_headers.items():
                request_lines.append(f"{header_name}: {header_value}")
            
            request = "\r\n".join(request_lines) + "\r\n\r\n"
            
            # Create socket connection
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(30)
            sock.connect((self.host, self.port))
            sock.send(request.encode())
            
            # Read handshake response
            handshake = sock.recv(4096).decode()
            
            if "101 Switching Protocols" not in handshake:
                sock.close()
                raise Exception(f'WebSocket handshake failed: {handshake[:150]}')
            
            logger.debug(f"WebSocket connection established to {self.host}:{self.port}")
            return sock
            
        except Exception as e:
            logger.error(f"Failed to create WebSocket connection: {e}")
            raise

    def _read_websocket_frame(self, sock: socket.socket) -> Optional[str]:
        """Read and parse single WebSocket frame"""
        try:
            data = sock.recv(4096)
            if not data or len(data) < 2:
                return None
            
            # Parse WebSocket frame header
            fin = (data[0] & 0x80) != 0
            opcode = data[0] & 0x0f
            
            if opcode == 1:  # Text frame
                payload_len = data[1] & 0x7f
                
                if payload_len < 126:
                    payload_start = 2
                elif payload_len == 126:
                    payload_start = 4
                    payload_len = int.from_bytes(data[2:4], 'big')
                else:
                    payload_start = 10
                    payload_len = int.from_bytes(data[2:10], 'big')
                
                # Extract payload (WebSocket frames from server are typically unmasked)
                if payload_start + payload_len <= len(data):
                    payload = data[payload_start:payload_start + payload_len]
                    return payload.decode('utf-8', errors='ignore')
            
            return None
            
        except Exception as e:
            logger.debug(f"Error reading WebSocket frame: {e}")
            return None

    def _send_websocket_message(self, sock: socket.socket, message: str):
        """Send message via WebSocket with proper framing"""
        try:
            # Create WebSocket frame
            frame = bytearray([0x81])  # FIN + Text frame
            
            # Prepare payload (limit length to prevent issues)
            payload = message.encode('utf-8')[:self.max_message_length]
            
            # Add payload length and mask bit (client must mask)
            if len(payload) < 126:
                frame.append(len(payload) | 0x80)  # Masked
            elif len(payload) < 65536:
                frame.append(126 | 0x80)  # Masked + 16-bit length
                frame.extend(len(payload).to_bytes(2, 'big'))
            else:
                frame.append(127 | 0x80)  # Masked + 64-bit length
                frame.extend(len(payload).to_bytes(8, 'big'))
            
            # Add mask and masked payload
            mask = os.urandom(4)
            frame.extend(mask)
            for i, byte in enumerate(payload):
                frame.append(byte ^ mask[i % 4])
            
            sock.send(frame)
            logger.debug(f"Sent WebSocket message: {message[:50]}...")
            
        except Exception as e:
            logger.error(f"Failed to send WebSocket message: {e}")
            raise

    def _receive_response(self, sock: socket.socket) -> str:
        """Receive and reconstruct response from WebSocket frames"""
        start_time = time.time()
        frames = []
        typing_off_seen = False
        
        while time.time() - start_time < self.response_timeout:
            try:
                frame_content = self._read_websocket_frame(sock)
                
                if frame_content:
                    frames.append(frame_content)
                    logger.debug(f"Received frame: {frame_content[:50]}...")
                    
                    # Handle typing indicators if configured
                    if frame_content in self.typing_indicators:
                        if frame_content == 'typing off':
                            typing_off_seen = True
                        continue
                    
                    # Check response timing based on configuration
                    if self.response_after_typing:
                        if typing_off_seen:
                            # This is the response after typing indicators
                            return frame_content
                    else:
                        # Response comes immediately
                        return frame_content
                        
            except Exception as e:
                logger.debug(f"Error receiving frame: {e}")
                pass
                
            time.sleep(0.1)
        
        # Extract actual response (filter out typing indicators)
        response_frames = [f for f in frames if f not in self.typing_indicators]
        
        if response_frames:
            # Join multiple response frames if needed
            full_response = ' '.join(response_frames).strip()
            logger.debug(f"Reconstructed response: {full_response[:100]}...")
            return full_response
        
        return ""

    def _call_model(
        self, prompt: Conversation, generations_this_call: int = 1
    ) -> List[Union[Message, None]]:
        """Core method called by garak to generate responses"""
        if not prompt or not prompt.last_message():
            return [None]
        
        prompt_text = prompt.last_message().text
        responses = []
        
        for _ in range(generations_this_call):
            try:
                # Create WebSocket connection
                sock = self._create_websocket_connection()
                
                # Send prompt
                self._send_websocket_message(sock, prompt_text)
                
                # Receive response
                response_text = self._receive_response(sock)
                
                # Close connection
                sock.close()
                
                # Create response message
                if response_text:
                    responses.append(Message(response_text))
                    logger.info(f"Generated response: {response_text[:50]}...")
                else:
                    responses.append(None)
                    logger.warning("No response received from WebSocket")
                
                # Brief delay between generations
                if generations_this_call > 1:
                    time.sleep(1)
                    
            except Exception as e:
                logger.error(f"WebSocket generation failed: {e}")
                responses.append(None)
        
        return responses


DEFAULT_CLASS = "WebSocketGenerator"


# Convenience function for simple WebSocket testing
def create_websocket_generator(
    endpoint: str,
    auth_type: str = "basic",
    username: str = None,
    password: str = None,
    api_key: str = None,
    conversation_id: str = None,
    **kwargs
) -> WebSocketGenerator:
    """Convenience function to create WebSocket generator with common parameters"""
    return WebSocketGenerator(
        endpoint=endpoint,
        auth_type=auth_type,
        username=username,
        password=password,
        api_key=api_key,
        conversation_id=conversation_id,
        **kwargs
    )