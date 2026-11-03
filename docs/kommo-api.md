# Поддерживаемый API Kommo

Базовый адрес: `http://127.0.0.1:4010`. Все запросы требуют
`Authorization: Bearer local-kommo-token` (значение настраивается).

| Метод | Путь | Поведение |
|---|---|---|
| GET | `/api/v4/leads` | Фильтрованный список и пагинация |
| POST | `/api/v4/leads` | Batch создания |
| GET, PATCH | `/api/v4/leads/{id}` | Чтение, ответственный, статус/воронка, custom fields |
| GET, POST | `/api/v4/contacts` | Поиск контактов / batch создания |
| GET, PATCH | `/api/v4/contacts/{id}` | Чтение / изменение |
| POST | `/api/v4/leads/{id}/link` | Двусторонняя связь с контактом |
| GET | `/api/v4/leads/{id}/notes` | Список заметок |
| POST | `/api/v4/leads/{id}/notes` | Создание common-заметки для лида |
| POST | `/api/v4/leads/notes` | Batch common-заметок с entity_id (payment) |
| GET, POST | `/api/v4/tasks` | Фильтрованный список / создание задач |
| GET, PATCH | `/api/v4/tasks/{id}` | Чтение / ответственный, текст, срок, завершение |
| GET | `/api/v4/leads/pipelines` | Локальный список воронок |
| GET | `/api/v4/leads/pipelines/{id}` | Воронка со статусами |
| GET | `/api/v4/leads/pipelines/{id}/statuses/{id}` | Статус воронки |
| GET | `/api/v4/users`, `/api/v4/users/{id}` | Пользователи, rights, role/group |
| GET | `/api/v4/roles`, `/api/v4/roles/{id}` | Роли и их пользователи |
| PATCH | `/api/v4/roles/{id}` | Обновление имени/прав роли |
| GET | `/api/v4/sources`, `/api/v4/sources/{id}` | Источники из state |
| GET | `/api/v4/events` | События из state с фильтрами |
| GET | `/api/v4/leads/unsorted` | Неразобранные по UID/воронке |
| POST | `/api/v4/leads/unsorted/forms` | Создание заявки, лида и контакта |
| POST | `/api/v4/leads/unsorted/{uid}/accept` | Принятие и удаление из неразобранных |
| POST | `/api/v4/leads/unsorted/{uid}/link` | Связать чат с существующим лидом |

## Query-параметры

- `page`, `limit` (1–250), `_links.next` только при наличии следующей страницы.
- `with=contacts,source_id` для лидов; `with=leads` для контактов.
- `query` — поиск по имени и custom field values, включая телефон/email.
- `filter[responsible_user_id][]`, `filter[entity_id][]`, `filter[entity_type][]`;
  индексированные варианты `[0]`, `[1]` также поддерживаются.
- `filter[statuses][0][pipeline_id]`, `filter[statuses][0][status_id]` и другие индексы.
  Между парами OR, между разными фильтрами AND.
- `filter[created_at][from]`, `filter[created_at][to]`, `order[created_at]=asc|desc`.
- `filter[is_completed]=0|1`, `filter[uid]`, `filter[pipeline_id]`.
- `filter[entity]=contact`, `filter[entity_id]`,
  `filter[type]=incoming_chat_message,outgoing_chat_message` для событий.

## Запись и ответы

POST-коллекции принимают JSON-массивы; PATCH одной сущности — JSON-объект.
Успешные JSON-ответы используют `application/hal+json`, списки — `_embedded`.
При обновлении custom fields объединяются по `field_id`; `values: null` или `[]`
очищает указанное поле. Неуказанные поля сохраняются.

Пустые результаты leads/contacts/tasks/notes/events/sources/unsorted — **204 без тела**.
Для users/roles/pipelines пустой список имеет JSON-envelope (требование текущих клиентов).
Удалённый лид из state (`is_deleted=true`) возвращает 204, неизвестный ID — 404.
Ошибочные JSON/параметры возвращают 400, неверный токен — 401.
Неизвестные маршруты не подменяются успешными заглушками.

Sources и chat events загружаются через `/_mock/kommo/state`; по умолчанию пустые.
Для `unsorted/link` нужна запись `category=chats`: можно создать форму, экспортировать
state и изменить category на chats для теста такого сценария. Link принимает
`link.entity_id`, `link.entity_type=leads` и необязательное `link.metadata.contact_id`.

Автоматические webhooks, rate limiting и случайные ошибки пока отсутствуют. Payload
создания/обновления возвращается в расширенном формате сущности, удобном обоим клиентам;
точное совпадение всех ответов записи с production Kommo ещё требует контрактных примеров.
