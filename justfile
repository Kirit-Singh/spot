# spot dev commands — run `just --list`. Real targets are wired in Chunk 9.
set shell := ["bash", "-cu"]

# Show available recipes
default:
    @just --list

# Start the localhost stack (postgres, redis, api, frontend)
up:
    docker compose -f deploy/docker-compose.yml up --build

# Stop the localhost stack
down:
    docker compose -f deploy/docker-compose.yml down

# Lint all services (wired in Chunk 9)
lint:
    @echo "lint: not wired yet (Chunk 9)"

# Format all services (wired in Chunk 9)
fmt:
    @echo "fmt: not wired yet (Chunk 9)"

# Type-check all services (wired in Chunk 9)
typecheck:
    @echo "typecheck: not wired yet (Chunk 9)"

# Run all tests (wired in Chunk 9)
test:
    @echo "test: not wired yet (Chunk 9)"
