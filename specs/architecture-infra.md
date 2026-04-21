# Архитектура инфраструктуры

Kubernetes, observability, CI/CD, масштабирование. Изменяется при инфра-задачах (I-*).

Общие принципы архитектуры — в `architecture.md`. Сервисы бэкенда — в `architecture-backend.md`.

---

## 1. Инфраструктура

### 1.1. Kubernetes

Все сервисы развёрнуты как Deployments с HorizontalPodAutoscaler. Минимум 2 реплики на сервис в production.

Компоненты кластера:
- **Ingress:** Nginx Ingress Controller. TLS-сертификаты — через cert-manager и Let's Encrypt.
- **Service Mesh:** на старте не используется; при необходимости добавляется Linkerd (лёгкий аналог Istio).
- **Kafka:** через Strimzi Operator — декларативное управление кластером Kafka в K8s. Минимум 3 брокера в production.
- **PostgreSQL и Citus:** managed-сервис облачного провайдера (предпочтительно) или через оператор (Zalando Postgres Operator / CloudNativePG) для self-hosted. Citus может быть развёрнут отдельно через Citus Community Operator.
- **Redis:** через оператор (Redis Operator) или managed-сервис.
- **Prometheus + Grafana + Loki:** через `kube-prometheus-stack` (Grafana Operator) и Loki Helm chart.
- **Sentry:** self-hosted через Helm либо облачный Sentry.
- **MinIO** (если не managed S3): через MinIO Operator.

### 1.2. Топология окружений

Минимум два окружения:
- **staging** — отдельный namespace (или отдельный кластер для изоляции) для интеграционного тестирования.
- **production** — основная среда.

Dev-окружение разработчика — локальный Kubernetes (Kind / Minikube / Docker Desktop) либо Docker Compose с минимальным набором зависимостей (Postgres, Kafka, Redis).

### 1.3. Секреты

Секреты хранятся в Kubernetes Secret, на старте инжектятся в pods через env / volume. Для боевого управления секретами может использоваться HashiCorp Vault или SealedSecrets — решение откладывается на более поздний этап.

---

## 2. Наблюдаемость

### 2.1. Метрики

**Prometheus** собирает метрики со всех сервисов:
- **Golden signals:** latency, traffic, errors, saturation для каждого сервиса.
- **HTTP-метрики:** из middleware Gin (request count, duration, status code).
- **gRPC-метрики:** из interceptor'ов (аналогично HTTP).
- **Kafka-метрики:** producer offset, consumer lag, commit rate.
- **БД-метрики:** pool size, active connections, slow queries (через pg_stat_statements в PostgreSQL/Citus).
- **Доменные метрики:** число созданных задач, проектов, автоматизаций в единицу времени; срабатываний автоматизаций; неуспешных срабатываний.

**Grafana** строит дашборды:
- Общий dashboard системы: здоровье всех сервисов, ошибки, latency.
- Dashboard каждого сервиса: свои метрики + потребление ресурсов.
- Dashboard Kafka: lag по consumer groups (особенно automations-service и events-service).
- Dashboard по тарифам: распределение пользователей по тарифам, доход, отказы платежей.

### 2.2. Ошибки

**Sentry** собирает все unhandled-исключения и HTTP 5xx-ошибки из сервисов через Go SDK. Context обогащается: user_id (если аутентифицирован), request_id, service name.

### 2.3. Логи

**Loki + Promtail.**
- Все сервисы пишут структурированные логи в stdout (JSON-формат).
- Promtail как DaemonSet на каждой ноде собирает логи pod'ов и отправляет в Loki.
- Loki индексирует метки (service, pod, severity), сам текст хранит сжатыми chunk'ами.
- Grafana предоставляет UI для поиска логов (LogQL).

**Стандартные поля в логе:** `timestamp`, `level`, `service`, `request_id`, `user_id`, `message`, `error` (если есть).

### 2.4. Request tracing

Распределённая трассировка на старте не подключается. Вместо этого — `request_id` в заголовке `X-Request-ID`, генерируется api-gateway, пробрасывается через все синхронные и асинхронные вызовы (в HTTP-заголовке, gRPC-metadata, в payload события). Логи всех сервисов по одному `request_id` выгребаются через Loki.

Если в будущем потребуется полноценный distributed tracing — добавляется OpenTelemetry + Grafana Tempo (совместим со стеком Grafana-Loki).

---

## 3. CI/CD и деплой

### 3.1. Monorepo-структура

Monorepo разделён на верхнем уровне по экосистемам и ролям артефактов:

```
/
├── backend/                        # всё, что бежит на Go
│   ├── services/                   # микросервисы
│   │   ├── identity/
│   │   │   ├── cmd/                # точка входа (main.go)
│   │   │   ├── internal/           # приватный код сервиса
│   │   │   ├── migrations/         # goose-миграции БД
│   │   │   ├── Dockerfile
│   │   │   └── go.mod
│   │   ├── workspace/
│   │   ├── automations/
│   │   ├── events/
│   │   ├── billing/
│   │   └── files/
│   ├── api-gateway/                # Nginx-конфиг + auth-sidecar для PAT-валидации
│   ├── pkg/                        # shared Go-модули
│   │   ├── service-template/       # базовый шаблон сервиса
│   │   ├── outbox/                 # transactional outbox relay
│   │   ├── grpc/                   # клиент/сервер обёртки
│   │   ├── kafka/                  # producer/consumer обёртки
│   │   ├── logging/                # структурированное логирование
│   │   ├── metrics/                # Prometheus-middleware
│   │   ├── sentry/                 # Sentry-интеграция
│   │   └── rsql/                   # парсер RSQL для backend
│   └── go.work                     # Go workspace для всех модулей
│
├── frontend/                       # Angular Workspace целиком
│   ├── angular.json
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   ├── Dockerfile                  # multistage (node build → nginx:alpine)
│   ├── projects/
│   │   ├── app/                    # основное приложение
│   │   └── docs/                   # лендинг-документация
│   └── libs/                       # библиотеки workspace
│       ├── design-system/
│       ├── api-client/
│       ├── shared-widgets/
│       ├── shared-utils/
│       ├── rsql/
│       └── markdown-editor/
│
├── contracts/                      # общие контракты между backend и frontend
│   ├── proto/                      # gRPC-контракты и схемы событий Kafka
│   │   ├── identity/
│   │   │   └── v1/                 # *.proto + сгенерированные *.pb.go, *_grpc.pb.go (коммитятся в репо)
│   │   ├── workspace/
│   │   │   └── v1/
│   │   ├── automations/
│   │   │   └── v1/
│   │   ├── events/
│   │   │   └── v1/
│   │   ├── billing/
│   │   │   └── v1/
│   │   ├── files/
│   │   │   └── v1/
│   │   ├── ping/                   # эталонный proto для проверки инфраструктуры codegen (I-17)
│   │   │   └── v1/                 # ping.proto + ping.pb.go + ping_grpc.pb.go
│   │   ├── buf.yaml
│   │   └── buf.gen.yaml            # конфигурация кодогенерации (local plugins, paths=source_relative)
│   └── openapi/                    # актуальная OpenAPI-спецификация (артефакт CI)
│       └── openapi.yaml
│
├── deploy/                         # всё, связанное с деплоем
│   ├── helm/                       # Helm-чарты
│   │   ├── identity/
│   │   ├── workspace/
│   │   ├── automations/
│   │   ├── events/
│   │   ├── billing/
│   │   ├── files/
│   │   ├── api-gateway/
│   │   ├── web-app/                # статика app за Nginx
│   │   ├── web-docs/               # статика docs за Nginx
│   │   └── infra/                  # kafka, postgres, citus, redis, minio, monitoring
│   └── compose/
│       └── docker-compose.yml      # локальное dev-окружение
│
├── docs-source/                    # markdown-исходники документации
│   ├── overview/
│   ├── scenarios/
│   ├── guides/
│   └── api-templates/
│
├── tools/                          # вспомогательные скрипты
│   ├── openapi-gen/
│   ├── openapi-to-ts/
│   ├── migrations/
│   └── scripts/
│
├── .github/
│   └── workflows/
│       └── ci-backend.yml
├── Makefile
└── README.md
```

**Принципы структуры:**

- **`backend/` и `frontend/` на верхнем уровне.** Разработчик сразу видит два понятных входа.
- **`contracts/` отдельно.** Proto и OpenAPI — межстековые контракты. Backend публикует `openapi.yaml` как CI-артефакт; frontend потребляет через codegen.
- **`deploy/` объединяет helm и compose.** Helm-чарты для Kubernetes, `docker-compose.yml` для локального dev-окружения.
- **`docs-source/` отдельно.** Контент-авторы работают с markdown-исходниками, не касаясь `frontend/projects/docs/`.
- **`tools/` кросс-стековый.** Скрипты затрагивают оба стека.

### 3.2. Pipeline

Каждый push/merge запускает в GitHub Actions:

1. **Lint & static check:** `go vet`, `golangci-lint`, `buf lint` для proto-файлов.
2. **Code generation:** `buf generate` для proto → Go-типы.
3. **Unit-тесты.**
4. **Integration-тесты:** поднимаются через docker-compose (Postgres, Kafka).
5. **Build images:** для изменившихся сервисов. Path-based триггеры (`paths:` в workflow): изменение в `services/workspace/` → собирается только workspace. Image tagging: `ghcr.io/<owner>/<repo>/<service>:<commit-sha>`, плюс `:latest` для главной ветки. Теги branch-name не используются.
6. **Push в GitHub Container Registry (ghcr.io):** только при мерже в main. В pull request образы собираются (для проверки Dockerfile), но не публикуются. Все Docker-джобы находятся в `.github/workflows/ci-backend.yml` (отдельный файл для Docker не создаётся).
7. **Deploy на staging** (автоматически после успешного pipeline в main).
8. **Deploy на production** — ручное подтверждение (`environment: production` с required reviewers).

### 3.3. Деплой в Kubernetes

**Инструмент:** `helm upgrade --install <release> helm/<service>` из CI-job.

Helm-чарт каждого сервиса содержит:
- `Deployment` с указанием image-тега.
- `Service` для внутреннего gRPC/HTTP.
- `Ingress` (для сервисов с публичным API — фактически только api-gateway).
- `HorizontalPodAutoscaler`.
- `ServiceMonitor` (для Prometheus).
- ConfigMaps / Secrets.

**Стратегия обновления:** RollingUpdate. Один под обновляется за раз, старый pod'ы работают до готовности нового.

### 3.4. Откат

Откат через `helm rollback <release> <revision>` — возврат к предыдущему released-тегу. Поскольку миграции обратно-совместимы, откат возможен без дополнительных шагов с БД.

---

## 4. Масштабирование

### 4.1. Горизонтальное масштабирование сервисов

Все stateless-сервисы (identity, workspace, automations, events, billing, files, api-gateway) масштабируются через HPA по метрикам CPU и RPS.

### 4.2. Масштабирование БД

- **Citus-кластеры** (workspace, events, automations): добавление воркер-нод, ребаланс шардов.
- **PostgreSQL-сервисы** (identity, billing, files): вертикальное масштабирование; read replicas для read-heavy endpoint'ов.

### 4.3. Масштабирование Kafka

Добавление брокеров, увеличение числа партиций в топиках. Consumer group'ы автоматически перераспределяются.

### 4.4. Гео-распределение

На старте — один регион. Переход на multi-region — отдельный проект, вне текущего роадмапа.
