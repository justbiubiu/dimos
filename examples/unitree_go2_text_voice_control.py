#!/usr/bin/env python3
# Copyright 2026 Dimensional Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Control Unitree GO2 with text or voice commands via DimOS agent channel.

Usage examples:
    # 1) Start robot stack in another terminal first:
    # dimos run unitree-go2-agentic-mcp --daemon
    #
    # 2) Text control:
    # python examples/unitree_go2_text_voice_control.py --mode text
    #
    # 3) Voice control (requires microphone + whisper):
    # python examples/unitree_go2_text_voice_control.py --mode voice --whisper-model base
"""
# ruff: noqa: I001

from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


def _run_dimos_agent_send(command_text: str) -> None:
    """Forward one natural-language command to DimOS agent."""
    process = subprocess.run(
        ["dimos", "agent-send", command_text],
        capture_output=True,
        text=True,
        check=False,
    )
    if process.returncode != 0:
        stderr = process.stderr.strip() or process.stdout.strip()
        raise RuntimeError(f"dimos agent-send failed: {stderr}")

    output = process.stdout.strip()
    if output:
        print(f"[agent] {output}")


def _ensure_positive(value: float, name: str) -> None:
    if value <= 0:
        raise RuntimeError(f"{name} must be > 0, got {value}")


def _load_whisper_model(model_name: str) -> Any:
    """Load whisper model once for faster repeated transcription."""
    try:
        import whisper  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "Whisper is not installed. Please install dependencies first, e.g. "
            "'uv pip install openai-whisper sounddevice soundfile'."
        ) from exc

    try:
        return whisper.load_model(model_name)
    except Exception as exc:  # pragma: no cover - runtime model errors
        raise RuntimeError(f"Failed to load whisper model '{model_name}': {exc}") from exc


def _text_loop() -> None:
    print("Text mode started. Type command and press Enter. Type 'exit' to quit.")
    while True:
        try:
            text = input("GO2> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not text:
            continue
        if text.lower() in {"exit", "quit", "q"}:
            break

        _run_dimos_agent_send(text)


def _record_audio_wav(duration_sec: float, sample_rate: int) -> Path:
    """Record microphone audio to a temporary WAV file."""
    try:
        import sounddevice as sd  # type: ignore[import-untyped]
        import soundfile as sf  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "Audio dependencies missing. Please install 'sounddevice' and 'soundfile'."
        ) from exc

    frames = int(duration_sec * sample_rate)
    print(f"Recording {duration_sec:.1f}s...")
    try:
        audio = sd.rec(frames, samplerate=sample_rate, channels=1, dtype="float32")
        sd.wait()
    except Exception as exc:
        raise RuntimeError(f"Microphone recording failed: {exc}") from exc
    print("Recording done.")

    fd, path = tempfile.mkstemp(suffix=".wav", prefix="go2_voice_")
    Path(path).unlink(missing_ok=True)
    # Close the raw file descriptor from mkstemp to avoid leaks.
    try:
        os.close(fd)
    except OSError:
        pass
    wav_path = Path(path)
    try:
        sf.write(str(wav_path), audio, sample_rate)
    except Exception as exc:
        raise RuntimeError(f"Failed to write wav file: {exc}") from exc
    return wav_path


def _transcribe_wav(wav_path: Path, model: Any, language: str) -> str:
    """Transcribe WAV with OpenAI whisper package."""
    result = model.transcribe(str(wav_path), language=language, fp16=False)
    return str(result.get("text", "")).strip()


def _voice_loop(duration_sec: float, sample_rate: int, model_name: str, language: str) -> None:
    _ensure_positive(duration_sec, "record-seconds")
    _ensure_positive(float(sample_rate), "sample-rate")
    model = _load_whisper_model(model_name)

    print("Voice mode started. Press Enter to record, type 'exit' to quit.")
    while True:
        try:
            token = input("[Enter=record, exit=quit] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if token in {"exit", "quit", "q"}:
            break

        wav_path = _record_audio_wav(duration_sec=duration_sec, sample_rate=sample_rate)
        try:
            text = _transcribe_wav(wav_path, model=model, language=language)
            if not text:
                print("[voice] No speech recognized, skipping.")
                continue
            print(f"[voice] {text}")
            _run_dimos_agent_send(text)
        finally:
            wav_path.unlink(missing_ok=True)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Control Unitree GO2 by text or voice via DimOS agent-send.",
    )
    parser.add_argument(
        "--mode",
        choices=["text", "voice"],
        default="text",
        help="Control mode.",
    )
    parser.add_argument(
        "--record-seconds",
        type=float,
        default=3.0,
        help="Voice recording duration for each turn.",
    )
    parser.add_argument(
        "--sample-rate",
        type=int,
        default=16000,
        help="Microphone sample rate.",
    )
    parser.add_argument(
        "--whisper-model",
        default="base",
        help="Whisper model name, e.g. tiny/base/small.",
    )
    parser.add_argument(
        "--language",
        default="zh",
        help="Whisper language code, e.g. zh/en.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        if args.mode == "text":
            _text_loop()
        else:
            _voice_loop(
                duration_sec=args.record_seconds,
                sample_rate=args.sample_rate,
                model_name=args.whisper_model,
                language=args.language,
            )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
