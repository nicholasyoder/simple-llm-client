#!/usr/bin/env python3
"""Groq CLI chat client with streaming and conversation history."""

import argparse
import os
import sys
from typing import Optional

from dotenv import load_dotenv
from groq import Groq
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
from rich.text import Text

load_dotenv()

console = Console()

DEFAULT_MODEL = "llama-3.3-70b-versatile"

MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "meta-llama/llama-4-maverick-17b-128e-instruct",
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "moonshotai/kimi-k2-instruct-0905",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "gemma2-9b-it",
]

HELP_TEXT = """\
[bold]Commands:[/bold]
  [cyan]/help[/cyan]          Show this help
  [cyan]/model[/cyan]         Show current model
  [cyan]/model <name>[/cyan]  Switch model
  [cyan]/models[/cyan]        List available models
  [cyan]/system[/cyan]        Show system prompt
  [cyan]/system <text>[/cyan] Set system prompt
  [cyan]/clear[/cyan]         Clear conversation history
  [cyan]/history[/cyan]       Show conversation history
  [cyan]/exit[/cyan]          Exit (also Ctrl+D or Ctrl+C)

[dim]Multi-line input: end a line with \\ to continue on the next line.[/dim]
"""


def read_multiline_input(prompt_str: str) -> Optional[str]:
    """Read input, supporting line continuation with backslash."""
    try:
        line = Prompt.ask(prompt_str)
    except (EOFError, KeyboardInterrupt):
        return None

    lines = []
    while line.endswith("\\"):
        lines.append(line[:-1])
        try:
            line = Prompt.ask("... ")
        except (EOFError, KeyboardInterrupt):
            break
    lines.append(line)
    return "\n".join(lines)


def stream_response(client: Groq, messages: list[dict], model: str) -> str:
    """Stream a chat completion and return the full response text."""
    full_text = ""

    with Live(console=console, refresh_per_second=15) as live:
        stream = client.chat.completions.create(
            messages=messages,
            model=model,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                full_text += delta
                live.update(
                    Panel(
                        Markdown(full_text),
                        title=f"[bold green]assistant[/bold green] [dim]({model})[/dim]",
                        border_style="green",
                    )
                )

    return full_text


def print_history(messages: list[dict], system_prompt: Optional[str]) -> None:
    if system_prompt:
        console.print(Panel(system_prompt, title="[bold yellow]system[/bold yellow]", border_style="yellow"))
    if not messages:
        console.print("[dim]No conversation history.[/dim]")
        return
    for msg in messages:
        role = msg["role"]
        content = msg["content"]
        if role == "user":
            console.print(Panel(content, title="[bold blue]user[/bold blue]", border_style="blue"))
        else:
            console.print(
                Panel(
                    Markdown(content),
                    title="[bold green]assistant[/bold green]",
                    border_style="green",
                )
            )


def main() -> None:
    parser = argparse.ArgumentParser(description="Groq CLI chat client")
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help="Model to use")
    parser.add_argument("-s", "--system", default=None, help="System prompt")
    parser.add_argument("--api-key", default=None, help="Groq API key (overrides GROQ_API_KEY env var)")
    args = parser.parse_args()

    api_key = args.api_key or os.environ.get("GROQ_API_KEY")
    if not api_key:
        console.print("[bold red]Error:[/bold red] No API key found. Set GROQ_API_KEY or use --api-key.")
        sys.exit(1)

    client = Groq(api_key=api_key)
    model = args.model
    system_prompt: Optional[str] = args.system
    messages: list[dict] = []

    console.print(
        Panel(
            f"[bold]Groq CLI Chat[/bold]\nModel: [cyan]{model}[/cyan]\nType [cyan]/help[/cyan] for commands.",
            border_style="bright_black",
        )
    )

    while True:
        user_input = read_multiline_input("[bold blue]you[/bold blue]")

        if user_input is None:
            console.print("\n[dim]Goodbye.[/dim]")
            break

        user_input = user_input.strip()
        if not user_input:
            continue

        # Commands
        if user_input.startswith("/"):
            parts = user_input.split(" ", 1)
            cmd = parts[0].lower()
            arg = parts[1].strip() if len(parts) > 1 else ""

            if cmd == "/exit":
                console.print("[dim]Goodbye.[/dim]")
                break

            elif cmd == "/help":
                console.print(HELP_TEXT)

            elif cmd == "/model":
                if arg:
                    model = arg
                    console.print(f"[dim]Model set to [cyan]{model}[/cyan][/dim]")
                else:
                    console.print(f"Current model: [cyan]{model}[/cyan]")

            elif cmd == "/models":
                console.print("[bold]Available models:[/bold]")
                for m in MODELS:
                    marker = " [green]<-- current[/green]" if m == model else ""
                    console.print(f"  [cyan]{m}[/cyan]{marker}")

            elif cmd == "/system":
                if arg:
                    system_prompt = arg
                    console.print(f"[dim]System prompt set.[/dim]")
                else:
                    if system_prompt:
                        console.print(Panel(system_prompt, title="[bold yellow]system[/bold yellow]", border_style="yellow"))
                    else:
                        console.print("[dim]No system prompt set.[/dim]")

            elif cmd == "/clear":
                messages = []
                console.print("[dim]Conversation cleared.[/dim]")

            elif cmd == "/history":
                print_history(messages, system_prompt)

            else:
                console.print(f"[red]Unknown command:[/red] {cmd}. Type [cyan]/help[/cyan] for available commands.")

            continue

        # Build message list for this request
        messages.append({"role": "user", "content": user_input})

        api_messages = []
        if system_prompt:
            api_messages.append({"role": "system", "content": system_prompt})
        api_messages.extend(messages)

        try:
            response_text = stream_response(client, api_messages, model)
            messages.append({"role": "assistant", "content": response_text})
        except Exception as e:
            console.print(f"[bold red]Error:[/bold red] {e}")
            # Remove the user message we just appended since we got no response
            messages.pop()


if __name__ == "__main__":
    main()
