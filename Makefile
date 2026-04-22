.PHONY: build up down test lint help

COMPOSE := docker compose -f deploy/docker-compose.yml
GO_RUN  := docker run --rm -v $(shell pwd)/backend:/app -w /app golang:1.23-alpine

build: ## Build all Docker images
	$(COMPOSE) build

up: ## Start all services
	$(COMPOSE) up -d

down: ## Stop all services
	$(COMPOSE) down

test: ## Run tests for all services inside Docker
	$(GO_RUN) go test ./...

lint: ## Run go vet for all services inside Docker
	$(GO_RUN) go vet ./...

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'
