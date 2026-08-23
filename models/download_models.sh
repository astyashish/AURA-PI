#!/bin/bash
# Download all required Ollama models

echo "Pulling LLM models via Ollama..."

ollama pull gemma2:2b
echo "✓ gemma2:2b — Main chat model"

ollama pull qwen2.5:0.5b
echo "✓ qwen2.5:0.5b — Fast lightweight model"

ollama pull llava:7b
echo "✓ llava:7b — Vision/image analysis model"

echo ""
echo "All models ready. Run: python main.py"
