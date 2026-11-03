# BestCredit Integration Mocks

Локальные HTTP-эмуляторы внешних интеграций. Отдельный Git-репозиторий рядом с
`bestcredit4you` и `bestcredit4you-leadmanagement`.

Сейчас реализован **Kommo API v4**, используемый обоими backend-сервисами.
Следующий провайдер — **Authorize.Net**; архитектура и этапы расширения описаны в
[docs/architecture.md](docs/architecture.md). Его API пока не реализован.

## Запуск

Требуются Python 3.12+ и `uv`. Из папки этого проекта:

```bash
uv sync --locked
cp .env.example .env
uv run --env-file .env uvicorn mock_server.app:create_app --factory --host 127.0.0.1 --port 4010
```

Проверка:

```bash
curl http://127.0.0.1:4010/health
curl -H 'Authorization: Bearer local-kommo-token' \
  'http://127.0.0.1:4010/api/v4/leads/33579273?with=contacts,source_id'
```

`/health` показывает список подключённых провайдеров. `/docs` содержит служебные
маршруты; перечень конкретных Kommo-маршрутов — в [docs/kommo-api.md](docs/kommo-api.md).
Kommo API смонтирован с исходным путём `/api/v4`, поэтому клиентам не нужны изменения кода.

## Подключение приложений

Адреса локального стенда, команды повторного запуска и результаты проверки через API
приложений: [docs/local-development.md](docs/local-development.md).

В **обоих** файлах:

- `../bestcredit4you-leadmanagement/.env`
- `../bestcredit4you/payment/.env`

установить:

```dotenv
KOMMO_BASE_URL=http://127.0.0.1:4010
KOMMO_ACCESS_TOKEN=local-kommo-token
```

Перезапустить lead-management, payment API и отдельно payment worker, если он запущен.
Console использует их API. Если процесс запущен в Docker, `127.0.0.1` внутри контейнера
указывает на сам контейнер; нужен доступный ему адрес mock-сервера.

Для записи платежных заметок/задач payment использует отдельные переключатели:

```dotenv
KOMMO_WRITEBACK_ENABLED=true
KOMMO_WRITEBACK_LEAD_ALLOWLIST=33579273
```

Для новых тестовых лидов расширить allowlist. В lead-management `BESTCREDIT_DRY_RUN=true`
может отключать изменения в отдельных сценариях распределения. Настройки приложений
не меняются автоматически этим проектом.

## Начальные данные

При первом запуске создаётся `data/kommo.sqlite3`:

- лид `33579273`, связанный контакт `37514079`;
- тестовые данные для платёжного плана: $200 + 8 × $280 = $2440;
- незавершённая задача `4578935` и обычная заметка;
- воронки INCOMING, SALES, TECH; локальные справочники INSIGHT, AI QUALIFIER,
  BANGTAO, NAI YANG с ID переходов из кода приложения;
- пользователи с ID, используемыми в настройках проекта, и одна тестовая роль;
- пустые sources, events и unsorted.

Имена, контакты и содержимое заметок вымышлены. Числовые ID сохранены для совместимости
с конфигурацией приложения. Названия дополнительных статусов и права роли — локальные
примерные настройки, а не копия всех production-справочников.

Изменения через POST/PATCH сохраняются между перезапусками. Batch-запросы атомарны:
если элемент не прошёл проверку, весь запрос откатывается.

### Экспорт, редактирование и сброс

Все служебные Kommo-маршруты требуют тот же локальный Bearer-токен.

```bash
curl -H 'Authorization: Bearer local-kommo-token' \
  http://127.0.0.1:4010/_mock/kommo/state -o data/scenario.json
```

В `data/scenario.json` можно редактировать массивы `leads`, `contacts`, `users`, `roles`,
`pipelines`, `sources`, `tasks`, `notes`, `events`, `unsorted`. Импорт **заменяет всё
состояние Kommo**; отсутствующие коллекции становятся пустыми:

```bash
curl -X PUT -H 'Authorization: Bearer local-kommo-token' \
  -H 'Content-Type: application/json' --data-binary @data/scenario.json \
  http://127.0.0.1:4010/_mock/kommo/state
```

Возврат к начальному набору:

```bash
curl -X POST -H 'Authorization: Bearer local-kommo-token' \
  http://127.0.0.1:4010/_mock/kommo/reset
```

`MOCK_DATA_DIR` задаёт каталог данных, `KOMMO_MOCK_TOKEN` — локальный токен.
Относительный каталог вычисляется от корня этого репозитория. Данные, `.env` и логи
исключены из Git. Приложение не делает запросов к production Kommo.

## Проверки

```bash
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
# Дополнительно: оба настоящих клиента, сервер стартует и останавливается автоматически:
RUN_CLIENT_CHECKS=1 uv run pytest -q tests/test_clients.py
```

Дополнительно, при установленном `node_modules` соседних проектов, запустите проверку
реальными TypeScript-клиентами против запущенного mock-сервера:

```bash
node --import ../bestcredit4you-leadmanagement/node_modules/tsx/dist/loader.mjs scripts/check-clients.mjs
```

Она создаёт лид, контакт, заметки и задачу, меняет ответственных и завершает задачу.
Использует `MOCK_BASE_URL` (по умолчанию `http://127.0.0.1:4010`) и `KOMMO_MOCK_TOKEN`.

## Границы эмуляции

- Покрывается используемое приложением подмножество API. Формы записи смоделированы
  по коду клиентов; их полное побайтовое совпадение с Kommo ещё не подтверждено Postman-примерами.
- Нет автоматической отправки Kommo-webhooks и работы виджетов/digital pipeline.
  Входящие webhooks приложения нужно вызывать отдельно. Изменения состояния пока
  не генерируют журнал событий; chat events можно загрузить через state.
- PostgreSQL-зеркало Kommo, читаемое через `KOMMO_SERVICE_DATABASE_URL`, не синхронизируется
  с SQLite. Соответствующие отчёты используют существующий локальный снимок.
- Google Sheets, SignWell, WhatsApp, Telegram и платёжный шлюз продолжают зависеть от
  собственных настроек. Этот сервер пока заменяет именно HTTP API Kommo.
- Хранилище рассчитано на локальные интеграционные сценарии: изменения одного провайдера
  сериализуются, а большие коллекции фильтруются в памяти. Для больших объёмов можно
  заменить хранилище провайдера на нормализованные SQL-таблицы.

Если порт занят:

```bash
lsof -nP -iTCP:4010 -sTCP:LISTEN
```

Остановите найденный свой процесс командой `kill <PID>` либо выберите другой `--port`
и обновите `KOMMO_BASE_URL`.
