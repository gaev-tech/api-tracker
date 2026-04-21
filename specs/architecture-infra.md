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
- **PostgreSQL и Citus:** версия **16**. В dev-окружении — `postgres:16-alpine` в docker-compose. В production — managed-сервис облачного провайдера (предпочтительно) или через оператор (Zalando Postgres Operator / CloudNativePG) для self-hosted. Citus может быть развёрнут отдельно через Citus Community Operator.
- **Redis:** через оператор (Redis Operator) или managed-сервис.
- **Prometheus + Grafana + Loki:** через `kube-prometheus-stack` (Grafana Operator) и Loki Helm chart.
- **Sentry:** self-hosted через Helm либо облачный Sentry.
- **MinIO** (если не managed S3): через MinIO Operator.

### 1.2. Топология окружений

Один кластер Kubernetes, два namespace-а:
- **`staging`** — для интеграционного тестирования. Деплой происходит автоматически после успешного merge в main.
- **`production`** — основная среда. Деплой требует ручного подтверждения (`environment: production` с required reviewers в GitHub Actions).

Dev-окружение разработчика — локальный Kubernetes (Kind / Minikube / Docker Desktop) либо Docker Compose с минимальным набором зависимостей (Postgres, Kafka, Redis).

### 1.3. Секреты

Секреты хранятся в Kubernetes Secret, на старте инжектятся в pods через env / volume. Для боевого управления секретами может использоваться HashiCorp Vault или SealedSecrets — решение откладывается на более поздний этап.

### 1.4. Конвенции именования БД и credentials

**Названия баз данных:** `<service>_db` — например, `identity_db`, `billing_db`, `files_db`, `workspace_db`, `events_db`, `automations_db`.

**Названия ролей:** `<service>_user` — например, `identity_user`, `billing_user`. Каждая роль имеет права только на свою БД (principle of least privilege).

**K8s Secrets с connection strings:** `<service>-db-credentials` — например, `identity-db-credentials`. Содержит ключ `DATABASE_URL` в формате DSN: `postgresql://<user>:<password>@<host>:5432/<dbname>?sslmode=require`.

Сервисы читают `DATABASE_URL` из env-переменной (через `envFrom.secretRef` в Helm-чарте).

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

**Локальная разработка (docker-compose, I-13):**

Prometheus и Grafana добавляются в `deploy/docker-compose.yml` как обычные сервисы. Конфигурация хранится в `deploy/monitoring/`:

```
deploy/monitoring/
├── prometheus.yml              # scrape-конфиг
└── grafana/
    ├── provisioning/
    │   ├── datasources/
    │   │   └── prometheus.yml  # автоматическое подключение datasource
    │   └── dashboards/
    │       └── dashboard.yml   # провайдер дашбордов
    └── dashboards/
        └── overview.json       # базовый dashboard
```

- **Prometheus** слушает `:9090`. Scrape-интервал 15s. В `prometheus.yml` перечислены job'ы для каждого сервиса (`metrics`-endpoint на `/metrics`), а также для exporters.
- **Grafana** слушает `:3000`. Admin-credentials: `admin` / `admin` (dev только). Datasource Prometheus и дашборды подключаются через provisioning при старте. Дашборды — готовые JSON из официального каталога Grafana.
- **nginx-prometheus-exporter** (`nginx/nginx-prometheus-exporter`) — собирает метрики с Nginx stub_status (`/stub_status`). Слушает `:9113`. Для этого nginx.conf должен экспонировать `/stub_status` на внутреннем location.
- **postgres_exporter** (`prometheuscommunity/postgres-exporter`) — по одному экземпляру на каждый PostgreSQL-сервис (identity, billing, files). Слушают `:9187`, `:9188`, `:9189`. Подключаются через `DATA_SOURCE_NAME` (DSN с `sslmode=disable` — в dev-окружении TLS на PostgreSQL не настроен).

Используемые дашборды (Grafana Dashboard IDs):
- **PostgreSQL**: ID 9628 (PostgreSQL Database, совместим с postgres_exporter).
- **Nginx**: ID 12708 (NGINX Prometheus Exporter).

В K8s — `kube-prometheus-stack` через Helm (после I-2). ServiceMonitor'ы сервисов активируются через `serviceMonitor.enabled: true` в Helm values.

### 2.2. Ошибки

**Sentry** собирает все unhandled-исключения и HTTP 5xx-ошибки из сервисов через Go SDK. Context обогащается: user_id (если аутентифицирован), request_id, service name.

### 2.3. Логи

**Loki + Promtail.**
- Все сервисы пишут структурированные логи в stdout (JSON-формат).
- Promtail собирает логи и отправляет в Loki.
- Loki индексирует метки (service, container, level), сам текст хранит сжатыми chunk'ами.
- Grafana предоставляет UI для поиска логов (LogQL).

**Стандартные поля в логе:** `timestamp`, `level`, `service`, `request_id`, `user_id`, `message`, `error` (если есть).

**Локальная разработка (docker-compose, I-14):**

Loki и Promtail добавляются в `deploy/docker-compose.yml`. Конфиги хранятся в `deploy/monitoring/`:

```
deploy/monitoring/
├── loki-config.yml             # хранилище chunk'ов в filesystem, retention 7d
├── promtail-config.yml         # pipeline scrape через Docker socket
...
```

- **Loki** слушает `:3100`. Хранит логи локально в volume `loki-data`. Retention 7 дней.
- **Promtail** монтирует Docker socket (`/var/run/docker.sock`) и читает логи всех контейнеров через Docker service discovery. Добавляет метки `container`, `compose_service`, `image`.
- **Datasource Loki** добавляется в Grafana provisioning (`deploy/monitoring/grafana/provisioning/datasources/loki.yml`).

В K8s — Loki Helm chart + Promtail как DaemonSet (после I-2).

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
│   │   ├── service-template/       # эталонный параметризованный чарт (I-5); копируется для каждого сервиса
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
│       ├── ci-backend.yml          # lint, test, build, push images
│       └── cd-helm.yml             # helm deploy на staging (авто) и production (ручное)
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
7. **Deploy на staging** — автоматически после успешного pipeline в main. Реализован в отдельном workflow `.github/workflows/cd-helm.yml`. Kubeconfig кластера хранится в GitHub Actions Secret `KUBECONFIG_B64` (base64-encoded), на каждом deploy-job декодируется во временный файл.
8. **Deploy на production** — ручное подтверждение (`environment: production` с required reviewers). Тот же `cd-helm.yml`, отдельный job с `environment: production`.

### 3.3. Деплой в Kubernetes

**Инструмент:** `helm upgrade --install <release> deploy/helm/<service>` из CI-job. Версия Helm: **3.16.0**, устанавливается через `azure/setup-helm@v4` в GitHub Actions.

#### Шаблон чарта (I-5)

Все сервисные Helm-чарты строятся по единому шаблону. Реализован как **reference chart** `deploy/helm/service-template/` — полноценный параметризованный чарт, который копируется для каждого нового сервиса. Не является Helm library chart (`type: library`) — каждый сервисный чарт самостоятелен и не имеет зависимости на `_common`.

Структура шаблона:
```
deploy/helm/service-template/
├── Chart.yaml
├── values.yaml          # схема значений по умолчанию
└── templates/
    ├── deployment.yaml
    ├── service.yaml
    ├── hpa.yaml
    ├── servicemonitor.yaml
    ├── configmap.yaml
    ├── secret.yaml
    └── _helpers.tpl
```

Параметры `values.yaml` (ключи верхнего уровня):
- `image.repository`, `image.tag` — образ и тег.
- `replicaCount` — стартовое число реплик.
- `hpa.minReplicas`, `hpa.maxReplicas`, `hpa.targetCPUUtilizationPercentage`.
- `service.port`, `service.grpcPort` — порты HTTP и gRPC.
- `ingress.enabled`, `ingress.host` — Ingress только для api-gateway (по умолчанию отключён).
- `env` — список env-переменных (key/value).
- `envFrom` — ссылки на ConfigMap и Secret (key/value ref).
- `resources.requests`, `resources.limits` — CPU и память.
- `serviceMonitor.enabled` — включение ServiceMonitor для Prometheus.

Helm-чарт каждого сервиса содержит:
- `Deployment` с указанием image-тега.
- `Service` для внутреннего gRPC/HTTP.
- `Ingress` (для сервисов с публичным API — фактически только api-gateway; по умолчанию `ingress.enabled: false`).
- `HorizontalPodAutoscaler`.
- `ServiceMonitor` (для Prometheus; по умолчанию `serviceMonitor.enabled: true`).
- ConfigMap / Secret (пустые шаблоны; заполняются в values конкретного сервиса).

**Стратегия обновления:** RollingUpdate. Один под обновляется за раз, старый pod'ы работают до готовности нового.

#### Проверка шаблона (I-5)

В рамках I-5 создаётся `deploy/helm/helloworld/` — копия шаблона с минимальным `values.yaml`, деплоится на staging как smoke-test. После прохождения — `helloworld`-релиз удаляется.

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
