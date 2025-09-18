# WebSocket Generator for Garak

This adds WebSocket support to garak, enabling security testing of WebSocket-based LLM services.

## Features

- **Full WebSocket Protocol Support** - RFC 6455 compliant WebSocket implementation
- **Flexible Authentication** - Basic Auth, Bearer tokens, custom headers
- **Response Pattern Recognition** - Configurable typing indicators and response timing
- **SSH Tunnel Compatible** - Works with secure remote access patterns
- **Production Tested** - Successfully tested with real WebSocket LLM services

## Usage

### Command Line

```bash
python -m garak \
  --model_type websocket.WebSocketGenerator \
  --generator_options '{"websocket": {"WebSocketGenerator": {"endpoint": "ws://localhost:3000/", "auth_type": "basic", "username": "your_user", "password": "your_pass", "api_key": "your_key", "conversation_id": "session_id"}}}' \
  --probes encoding,dan,jailbreak \
  --generations 1
```

### Programmatic Usage

```python
from garak.generators.websocket import WebSocketGenerator
from garak.attempt import Message, Conversation

generator = WebSocketGenerator(
    endpoint="ws://localhost:3000/",
    auth_type="basic",
    username="your_user",
    password="your_pass",
    api_key="your_key",
    conversation_id="session_id"
)

# Create a conversation
conversation = Conversation()
conversation.add_message(Message("Test prompt", role="user"))

# Generate response
responses = generator._call_model(conversation)
print(responses[0].text)
```

## Configuration Parameters

| Parameter | Type | Description | Default |
|-----------|------|-------------|---------|
| `endpoint` | str | WebSocket URL (ws:// or wss://) | Required |
| `auth_type` | str | Authentication method ('basic', 'bearer', 'custom') | 'basic' |
| `username` | str | Username for basic authentication | None |
| `password` | str | Password for basic authentication | None |
| `api_key` | str | API key parameter | None |
| `conversation_id` | str | Session/conversation identifier | None |
| `custom_headers` | dict | Additional WebSocket headers | {} |
| `response_timeout` | int | Response timeout in seconds | 15 |
| `typing_indicators` | list | Frames to ignore (e.g., typing indicators) | ['typing on', 'typing off'] |
| `response_after_typing` | bool | Whether response comes after typing indicators | True |
| `max_message_length` | int | Maximum message length | 1000 |

## Authentication Types

### Basic Authentication
```json
{
  "auth_type": "basic",
  "username": "your_username",
  "password": "your_password"
}
```

### Bearer Token
```json
{
  "auth_type": "bearer",
  "api_key": "your_bearer_token"
}
```

### Custom Headers
```json
{
  "auth_type": "custom",
  "custom_headers": {
    "Authorization": "Custom your_token",
    "X-API-Key": "your_api_key"
  }
}
```

## WebSocket LLM Patterns

The generator handles common WebSocket LLM patterns:

### Typing Indicators
Many chat-based LLMs send typing indicators:
```
→ "Hello!"
← "typing on"
← "typing off"  
← "Hi there! How can I help?"
```

Configure with:
```json
{
  "typing_indicators": ["typing on", "typing off"],
  "response_after_typing": true
}
```

### Direct Response
Some LLMs respond immediately:
```
→ "Hello!"
← "Hi there! How can I help?"
```

Configure with:
```json
{
  "response_after_typing": false
}
```

## SSH Tunnel Support

For remote WebSocket services:

```bash
# Set up tunnel
ssh -L 3000:remote-llm-service.com:3000 your-server

# Use localhost endpoint
python -m garak \
  --model_type websocket.WebSocketGenerator \
  --generator_options '{"websocket": {"WebSocketGenerator": {"endpoint": "ws://localhost:3000/"}}}' \
  --probes dan
```

## Example: Testing a Chat LLM

```bash
python -m garak \
  --model_type websocket.WebSocketGenerator \
  --generator_options '{"websocket": {"WebSocketGenerator": {
    "endpoint": "ws://chat-service.example.com:8080/chat",
    "auth_type": "basic",
    "username": "test_user",
    "password": "test_pass",
    "conversation_id": "test_session",
    "typing_indicators": ["typing_start", "typing_end"],
    "response_after_typing": true
  }}}' \
  --probes encoding,injection,jailbreak \
  --generations 2
```

## Troubleshooting

### Connection Issues
- Verify WebSocket endpoint is reachable
- Check authentication credentials
- Ensure proper SSL/TLS configuration for wss:// endpoints

### No Responses
- Adjust `response_timeout` for slow services
- Check `typing_indicators` configuration
- Verify `response_after_typing` setting matches your service

### Authentication Failures
- Verify username/password for basic auth
- Check API key format for bearer auth
- Ensure custom headers are correctly formatted

## Contributing

This WebSocket generator was developed to enable security testing of WebSocket-based LLM services. It has been tested with various WebSocket LLM implementations and follows RFC 6455 WebSocket standards.

For issues or improvements, please contribute to the garak project on GitHub.