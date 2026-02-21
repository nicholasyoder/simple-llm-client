# Simple LLM Client

A lightweight chat client for Groq's LLM API with both CLI and GUI interfaces.

## Features

- **CLI Interface**: Terminal-based chat with Rich formatting and markdown rendering
- **GUI Interface**: Modern, frameless window with streaming responses and syntax highlighting
- **Markdown Support**: Full markdown rendering with code syntax highlighting
- **Streaming Responses**: Real-time token streaming for faster perceived response times
- **Multiple Models**: Support for various Groq models (llama, qwen, gemma, etc.)
- **Conversation History**: Persistent chat history within each session
- **System Tray Integration**: Minimize to tray and control via DBus
- **Customizable System Prompts**: Set custom system prompts for specialized assistants

## Installation

### Prerequisites

- Python 3.10+
- Groq API key ([Get one here](https://console.groq.com/keys))

### Setup

1. Clone the repository:
```bash
git clone https://github.com/nicholasyoder/simple-llm-client.git
cd simple-llm-client
```

2. Create a virtual environment:
```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Set up your API key:
```bash
cp .env.example .env
# Edit .env and add your GROQ_API_KEY
```

## Usage

### GUI Mode (Recommended)

Launch the GUI chat window:

```bash
./gui.py
```

**Options:**
- `-m, --model MODEL`: Specify the model to use (default: llama-3.3-70b-versatile)
- `-s, --system PROMPT`: Set a custom system prompt
- `--api-key KEY`: Provide API key directly (overrides .env)
- `--no-tray`: Don't show system tray icon

**Example:**
```bash
./gui.py --model llama-3.1-8b-instant --system "You are a helpful coding assistant"
```

**Keyboard Shortcuts:**
- `Enter`: Send message
- `Shift+Enter`: New line in input
- `Esc`: Hide window
- Click system tray icon to toggle window

**DBus Control:**

You can control the GUI window via DBus:

```bash
# Toggle window visibility
dbus-send --session --type=method_call \
  --dest=com.groqchat.App \
  /com/groqchat/App \
  com.groqchat.App.Toggle

# Show window
dbus-send --session --type=method_call \
  --dest=com.groqchat.App \
  /com/groqchat/App \
  com.groqchat.App.Show

# Hide window
dbus-send --session --type=method_call \
  --dest=com.groqchat.App \
  /com/groqchat/App \
  com.groqchat.App.Hide
```

### CLI Mode

Launch the terminal-based chat:

```bash
./chat.py
```

**Options:**
- `-m, --model MODEL`: Specify the model to use
- `-s, --system PROMPT`: Set a custom system prompt
- `--api-key KEY`: Provide API key directly

**Available Commands:**
- `/help`: Show help message
- `/model [name]`: Show or change current model
- `/models`: List available models
- `/system [prompt]`: Show or set system prompt
- `/clear`: Clear conversation history
- `/history`: Show conversation history
- `/exit`: Exit (or Ctrl+D, Ctrl+C)

**Multi-line Input:**
End a line with `\` to continue on the next line.

## Configuration

### Window Size

The GUI automatically saves and restores window size. Configuration is stored in:
- Linux: `~/.config/groq-chat/config.json`

### Environment Variables

Create a `.env` file with:
```
GROQ_API_KEY=your_api_key_here
```

## Available Models

The client supports all Groq models, including:
- llama-3.3-70b-versatile
- llama-3.1-8b-instant
- meta-llama/llama-4-maverick-17b-128e-instruct
- meta-llama/llama-4-scout-17b-16e-instruct
- moonshotai/kimi-k2-instruct-0905
- qwen/qwen3-32b
- openai/gpt-oss-120b
- gemma2-9b-it

## Troubleshooting

### DBus service already running

If you see "Is another instance already running?", another instance of the GUI is already active. Close it first or use DBus to control the existing instance.

### Missing API Key

Make sure your `.env` file exists and contains a valid `GROQ_API_KEY`. Alternatively, pass it via `--api-key` flag.

## Development

Contributions are welcome! Please feel free to submit pull requests or open issues.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
