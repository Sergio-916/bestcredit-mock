# Локальное подключение BestCredit

Проверено 2026-10-26 на macOS. Node-процессы используют установленный Node.js 24.22.1.

## Адреса

| Сервис | Адрес | Проверка |
|---|---|---|
| Kommo mock | http://127.0.0.1:4010 | `GET /health` |
| Lead-management | http://127.0.0.1:3012 | `GET /health` |
| Payment API | http://127.0.0.1:4310 | `GET /api/health` |
| Console | http://127.0.0.1:4320 | Страница входа сотрудников |

В локальных `.env` lead-management и payment настроены:

```dotenv
KOMMO_BASE_URL=http://127.0.0.1:4010
KOMMO_ACCESS_TOKEN=local-kommo-token
```

У payment включён `KOMMO_WRITEBACK_ENABLED=true` и allowlist тестового лида `33579273`.
Для других ID allowlist нужно расширить. Console уже настроена на локальные backend-адреса.

## Проверенные сценарии

1. Payment: `GET /api/admin/enrollments/from-kommo/33579273/preview` с локальным
   `x-admin-api-key` вернул HTTP 200, `ready=true`, тестового клиента и менеджера.
2. Платёжный план рассчитан приложением: первый базовый платёж $200, ещё 8 по $280,
   общая базовая стоимость $2440; комиссия рассчитывается самим payment API.
3. Поле Service Package временно изменено PATCH-запросом к mock; следующий preview
   приложения получил новое значение. После проверки исходное поле восстановлено.
4. Lead-management: `GET /admin/lead-assignment/config` с его локальным Bearer-токеном
   вернул HTTP 200 и `kommoCatalogAvailable=true`.
5. Console собрана из текущих исходников; в браузере открывается страница входа.

Ключи backend-авторизации остаются в локальных `.env` приложений.

## Повторный запуск

Каждую команду запускать в отдельном терминале из указанной папки:

- `bestcredit-mocks/`:

  ```bash
  uv run --env-file .env uvicorn mock_server.app:create_app --factory --host 127.0.0.1 --port 4010
  ```

- `bestcredit4you-leadmanagement/`:

  ```bash
  nvm use 24.22.1
  npm run dev
  ```

- `bestcredit4you/payment/`:

  ```bash
  nvm use 24.22.1
  npm run dev:api
  ```

- `bestcredit4you/console/`:

  ```bash
  nvm use 24.22.1
  npm run build
  npm start
  ```

При фоновом запуске этой проверки логи размещены в `bestcredit-mocks/data/`:
`server.log`, `leadmanagement.log`, `payment.log`, `console.log`.

Чтобы найти процессы перед повторным запуском или остановкой:

```bash
lsof -nP -iTCP:4010 -iTCP:3012 -iTCP:4310 -iTCP:4320 -sTCP:LISTEN
kill -TERM <PID>
```

## Текущие границы

- В lead-management сохранён `BESTCREDIT_DRY_RUN=true`: изменения в отдельных
  сценариях распределения могут быть пропущены. Это отдельный переключатель от HTTP-подключения Kommo.
- Google Sheets credentials в текущем `.env` не настроены; фоновый sheet-sync пишет
  соответствующую ошибку в лог. Это не ошибка mock Kommo.
- Payment worker отдельно не запущен. Для фоновой обработки используется обычный
  worker приложения; Authorize.Net пока не эмулируется, его sandbox-ключи не настроены.
- Проверка не выполняла списание и не создавала новый платёжный план.
- PostgreSQL-зеркало и прочие внешние интеграции не заменяются HTTP-эмулятором Kommo.
