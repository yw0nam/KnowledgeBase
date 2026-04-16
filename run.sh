ANTHROPIC_BASE_URL=http://192.168.0.41:5535 \
ANTHROPIC_API_KEY=token-abc123 \
ANTHROPIC_AUTH_TOKEN=token-abc123 \
ANTHROPIC_DEFAULT_OPUS_MODEL=chat_model \
ANTHROPIC_DEFAULT_SONNET_MODEL=chat_model \
ANTHROPIC_DEFAULT_HAIKU_MODEL=chat_model \
claude --dangerously-skip-permissions #-p "/graphify raw/ --update --wiki --obsidian --obsidian-dir ."
