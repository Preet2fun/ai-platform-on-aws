.DEFAULT_GOAL := help
PY ?= python3
PIP ?= pip3

AGENTS := supervisor security_a2a cost_a2a cloudwatch_a2a jira_a2a knowledge_a2a \
          investigator_a2a advisor_a2a aws_api_mcp aws_knowledge_mcp cloudwatch_mcp

.PHONY: help install lint typecheck test run-supervisor deploy-all clean

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	 awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

install: ## Install deps + shared lib (editable)
	$(PIP) install -e ".[dev]"

lint: ## Ruff lint
	ruff check agents libs

typecheck: ## Mypy typecheck
	mypy agents libs

test: ## Run tests
	pytest -q

run-supervisor: ## Run the supervisor agent locally
	$(PY) -m agents.supervisor.supervisor_runtime

deploy-all: ## Build + push deployment.zip for every runtime
	@for a in $(AGENTS); do echo ">>> deploying $$a"; ./scripts/deploy.sh $$a || exit 1; done

clean: ## Remove build artifacts
	find . -name '__pycache__' -type d -prune -exec rm -rf {} + ; \
	find . -name 'deployment.zip' -delete ; rm -rf .build
