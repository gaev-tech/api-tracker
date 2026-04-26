# api-tracker

Облачный трекер задач с API-first архитектурой. В отличие от Jira/Linear/YouTrack, вся функциональность доступна через REST API — UI служит лишь для визуальной проверки.

## Спецификации

| Документ | Содержание |
|----------|------------|
| [Product Spec](specs/product-spec.md) | Продукт, сущности, фичи, тарифная система, права доступа |
| [Architecture](specs/architecture.md) | Стек, декомпозиция сервисов, паттерны коммуникации, БД, инфраструктура |
| [API Spec](specs/api-spec.md) | REST-эндпоинты, модели данных, коды ошибок, пагинация, RSQL |
| [DB Schema](specs/db-schema.md) | Физическая схема PostgreSQL, таблицы, индексы, нейминг |
| [UI Spec](specs/ui-spec.md) | Экраны, виджеты, принципы UI |
| [Roadmap](specs/roadmap.md) | DAG задач реализации (I-*, D-*, F-*) с зависимостями |

## Команды

**Backend (Go, per-service):**
```bash
go build ./...
go test ./...
go vet ./...
buf generate        # gRPC codegen из contracts/proto/
```

**Frontend (Angular):**
```bash
npm install
npm run build
npm run lint
npm test
```

**Локальная разработка:**
```bash
docker compose up   # из deploy/
```

Миграции БД запускаются автоматически при старте каждого сервиса.
