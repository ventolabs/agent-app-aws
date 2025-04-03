.PHONY: help install clean test format run run-ui run-api

# Colors for pretty printing
BLUE := \033[34m
GREEN := \033[32m
YELLOW := \033[33m
RED := \033[31m
RESET := \033[0m

help: ## Show this help message
	@echo '${BLUE}Usage:${RESET}'
	@echo '  make ${GREEN}<target>${RESET}'
	@echo ''
	@echo '${BLUE}Targets:${RESET}'
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  ${GREEN}%-15s${RESET} %s\n", $$1, $$2}'

install: ## Install dependencies and set up development environment
	@echo "${BLUE}Installing uv package manager...${RESET}"
	curl -LsSf https://astral.sh/uv/install.sh | sh
	@echo "${BLUE}Setting up development environment...${RESET}"
	./scripts/dev_setup.sh
	@echo "${GREEN}Installation complete! Run 'source .venv/bin/activate' to activate the virtual environment${RESET}"

clean: ## Clean up generated files and virtual environments
	@echo "${BLUE}Cleaning up...${RESET}"
	rm -rf .venv/
	rm -rf __pycache__/
	rm -rf .pytest_cache/
	rm -rf .coverage
	rm -rf .mypy_cache/
	rm -rf .ruff_cache/
	rm -rf *.egg-info/
	@echo "${GREEN}Clean up complete!${RESET}"

test: ## Run tests
	@echo "${BLUE}Running tests...${RESET}"
	pytest tests/ -v

format: ## Format code using ruff
	@echo "${BLUE}Formatting code...${RESET}"
	ruff format .
	ruff check . --fix
	@echo "${GREEN}Formatting complete!${RESET}"

run: ## Run the entire application stack using docker
	@if [ -z "$$OPENAI_API_KEY" ]; then \
		echo "${RED}Error: OPENAI_API_KEY environment variable is not set${RESET}"; \
		echo "Please set it using: export OPENAI_API_KEY=your_key_here"; \
		exit 1; \
	fi
	@echo "${BLUE}Starting the application stack...${RESET}"
	ag ws up
	@echo "${GREEN}Application is running!${RESET}"
	@echo "- Streamlit UI: ${BLUE}http://localhost:8501${RESET}"
	@echo "- FastAPI docs: ${BLUE}http://localhost:8000/docs${RESET}"
	@echo "- Postgres: ${BLUE}localhost:5432${RESET}"

stop: ## Stop the running application stack
	@echo "${BLUE}Stopping the application stack...${RESET}"
	ag ws down
	@echo "${GREEN}Application stopped${RESET}"

# Default target
.DEFAULT_GOAL := help 