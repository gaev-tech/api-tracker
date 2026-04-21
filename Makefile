.PHONY: build test lint help

SERVICES := identity-service workspace-service automations-service events-service billing-service files-service

build: ## Build all backend services
	@for svc in $(SERVICES); do \
		echo "==> build $$svc"; \
		cd backend/services/$$svc && go build ./... && cd ../../..; \
	done

test: ## Run tests for all backend services
	@for svc in $(SERVICES); do \
		echo "==> test $$svc"; \
		cd backend/services/$$svc && go test ./... && cd ../../..; \
	done

lint: ## Run go vet for all backend services
	@for svc in $(SERVICES); do \
		echo "==> vet $$svc"; \
		cd backend/services/$$svc && go vet ./... && cd ../../..; \
	done

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
