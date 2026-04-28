uv run black src/ test/

# Lint code
uv run ruff check src/ test/ --unsafe-fixes --fix
