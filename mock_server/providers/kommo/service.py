import copy
import re
import time
import uuid
from urllib.parse import urlencode

from pydantic import JsonValue
from starlette.datastructures import QueryParams

from .data import ACCOUNT_ID, DEFAULT_USER, ApiError, Object, State, integer, obj, objects


class KommoService:
    def __init__(self, state: State, base_url: str, query: QueryParams):
        self.state = state
        self.base = base_url.rstrip("/")
        self.query = query
        self.now = int(time.time())

    def find(self, kind: str, identifier: str | int) -> Object:
        key = "uid" if kind == "unsorted" else "id"
        for item in self.state[kind]:
            if str(item.get(key)) == str(identifier):
                return item
        raise ApiError(404, f"{kind}/{identifier} not found")

    def next_id(self, kind: str) -> int:
        return max((integer(item["id"], "id") for item in self.state[kind]), default=100000) + 1

    def render(self, item: Object, path: str, kind: str) -> Object:
        result = copy.deepcopy(item)
        if kind == "notes":
            path = f"leads/{item['entity_id']}/notes/{item['id']}"
        result["_links"] = {"self": {"href": f"{self.base}/api/v4/{path}"}}
        embedded = obj(result.get("_embedded", {}))
        includes = self.query.get("with", "").split(",")
        if kind == "leads":
            if "contacts" not in includes:
                embedded.pop("contacts", None)
            if "source_id" not in includes:
                result.pop("source_id", None)
            result["_embedded"] = embedded
        if kind == "contacts" and "leads" not in includes:
            embedded.pop("leads", None)
            result["_embedded"] = embedded
        if kind == "pipelines":
            for status in objects(embedded.get("statuses", [])):
                status["_links"] = {
                    "self": {
                        "href": (f"{self.base}/api/v4/leads/pipelines/{item['id']}/statuses/{status['id']}")
                    }
                }
        return result

    def collection(self, kind: str, items: list[Object], path: str) -> JsonValue:
        page = integer(self.query.get("page", "1"), "page")
        limit = min(integer(self.query.get("limit", "250"), "limit"), 250)
        start = (page - 1) * limit
        batch = items[start : start + limit]
        # User and role readers require envelopes even for empty collections.
        if not batch and kind not in ("users", "roles", "pipelines"):
            return None
        links: Object = {}
        for relation, number in [("self", page), ("next", page + 1), ("prev", page - 1)]:
            if relation == "next" and start + limit >= len(items):
                continue
            if relation == "prev" and page == 1:
                continue
            params = [(k, v) for k, v in self.query.multi_items() if k not in ("page", "limit")]
            params += [("page", str(number)), ("limit", str(limit))]
            links[relation] = {"href": f"{self.base}/api/v4/{path}?{urlencode(params)}"}
        key = "uid" if kind == "unsorted" else "id"
        return {
            "_page": page,
            "_links": links,
            "_embedded": {kind: [self.render(item, f"{path}/{item[key]}", kind) for item in batch]},
        }

    def filtered(self, kind: str) -> list[Object]:
        items = [item for item in self.state[kind] if not item.get("is_deleted")]
        statuses: dict[str, dict[str, int]] = {}
        filters: dict[str, list[str]] = {}
        for key, value in self.query.multi_items():
            match = re.fullmatch(r"filter\[statuses\]\[(\d+)\]\[(pipeline_id|status_id)\]", key)
            if match:
                statuses.setdefault(match[1], {})[match[2]] = integer(value, key)
                continue
            match = re.fullmatch(r"filter\[([^\]]+)\](?:\[(?:\d*)\])?", key)
            if match:
                name = match[1]
                if name not in (
                    "responsible_user_id",
                    "entity_id",
                    "entity_type",
                    "entity",
                    "type",
                    "is_completed",
                    "uid",
                    "pipeline_id",
                ):
                    raise ApiError(400, f"Unsupported filter: {name}")
                filters.setdefault(name, []).extend(value.split(","))
            elif key.startswith("filter[") and not re.fullmatch(r"filter\[created_at\]\[(from|to)\]", key):
                raise ApiError(400, f"Unsupported filter: {key}")
        if statuses:
            if any(set(pair) != {"pipeline_id", "status_id"} for pair in statuses.values()):
                raise ApiError(400, "Each status filter requires pipeline_id and status_id")
            items = [
                item
                for item in items
                if any(all(item.get(k) == v for k, v in pair.items()) for pair in statuses.values())
            ]
        for key, values in filters.items():
            field_name = "entity_type" if key == "entity" else key
            if key == "is_completed":
                if any(v not in ("0", "1") for v in values):
                    raise ApiError(400, "is_completed must be 0 or 1")
                items = [item for item in items if str(int(bool(item.get(field_name)))) in values]
            else:
                items = [item for item in items if str(item.get(field_name)) in values]
        for boundary in ("from", "to"):
            value = self.query.get(f"filter[created_at][{boundary}]")
            if value is not None:
                timestamp = integer(value, "created_at", 0)
                items = [
                    item
                    for item in items
                    if (
                        integer(item.get("created_at", 0), "created_at", 0) >= timestamp
                        if boundary == "from"
                        else integer(item.get("created_at", 0), "created_at", 0) <= timestamp
                    )
                ]
        search = self.query.get("query")
        if search:
            normalized = search.casefold().strip()
            digits = re.sub(r"\D", "", search)

            def matches(item: Object) -> bool:
                values: list[JsonValue] = [item.get("name", "")]
                for field in objects(item.get("custom_fields_values") or []):
                    values.extend(v.get("value", "") for v in objects(field.get("values", [])))
                return any(
                    normalized in str(value).casefold()
                    or (
                        len(digits) >= 7
                        and digits.removeprefix("1") == re.sub(r"\D", "", str(value)).removeprefix("1")
                    )
                    for value in values
                )

            items = [item for item in items if matches(item)]
        order = self.query.get("order[created_at]")
        if order not in (None, "asc", "desc"):
            raise ApiError(400, "Unsupported order")
        if order or kind == "events":
            items.sort(
                key=lambda item: integer(item.get("created_at", 0), "created_at", 0), reverse=order != "asc"
            )
        return items

    def status(self, pipeline_id: JsonValue, status_id: JsonValue) -> Object:
        pipeline = self.find("pipelines", integer(pipeline_id, "pipeline_id"))
        for status in objects(obj(pipeline["_embedded"])["statuses"]):
            if status["id"] == integer(status_id, "status_id"):
                return status
        raise ApiError(400, "Status does not belong to pipeline")

    def validate(self, kind: str, item: Object, *, imported: bool = False) -> None:
        for key in ("responsible_user_id", "entity_id", "complete_till", "pipeline_id", "status_id"):
            if key in item:
                integer(item[key], key, 0 if key == "responsible_user_id" else 1)
                if not isinstance(item[key], int):
                    raise ApiError(400, f"{key} must be a JSON integer")
        if "is_completed" in item and not isinstance(item["is_completed"], bool):
            raise ApiError(400, "is_completed must be boolean")
        if kind == "leads":
            self.status(item.get("pipeline_id"), item.get("status_id"))
        if kind == "tasks":
            if item.get("entity_type") not in ("leads", "contacts", "companies"):
                raise ApiError(400, "Invalid task entity_type")
            integer(item.get("entity_id"), "entity_id")
            integer(item.get("complete_till"), "complete_till")
        if kind == "notes":
            self.find("leads", integer(item.get("entity_id"), "entity_id"))
            params = obj(item.get("params"))
            if not imported and (
                item.get("note_type") != "common" or not isinstance(params.get("text"), str)
            ):
                raise ApiError(400, "Only common notes with params.text are supported")
        if "name" in item and not isinstance(item["name"], str):
            raise ApiError(400, "name must be a string")
        if "_embedded" in item:
            embedded = obj(item["_embedded"])
            for key in ("contacts", "leads", "tags", "companies", "users", "statuses"):
                if key in embedded:
                    objects(embedded[key], key)

    def merge_fields(self, old: JsonValue, new: JsonValue) -> JsonValue:
        if new is None:
            return None
        result = copy.deepcopy(objects(old or []))
        for field in objects(new, "custom_fields_values"):
            identifier = field.get("field_id")
            code = field.get("field_code")
            if identifier is None:
                identifier = {"PHONE": 584388, "EMAIL": 584390}.get(str(code))
            integer(identifier, "field_id")
            existing = next((f for f in result if f.get("field_id") == identifier), None)
            normalized = {**(existing or {}), **field, "field_id": identifier}
            if code in ("PHONE", "EMAIL"):
                normalized.update(field_name="Phone" if code == "PHONE" else "Email", field_type="multitext")
            values = normalized.get("values")
            if values is not None:
                objects(values, "values")
            if existing is not None:
                result.remove(existing)
            if values:
                result.append(normalized)
        return list(result)

    def update(self, kind: str, current: Object, patch: Object) -> Object:
        if "id" in patch and patch["id"] != current["id"]:
            raise ApiError(400, "Cannot change entity ID")
        updated = {
            **current,
            **{k: v for k, v in patch.items() if k not in ("_links", "created_at", "account_id")},
        }
        if "custom_fields_values" in patch:
            updated["custom_fields_values"] = self.merge_fields(
                current.get("custom_fields_values"), patch["custom_fields_values"]
            )
        self.validate(kind, updated)
        if kind == "leads" and "_embedded" in patch:
            embedded = obj(updated["_embedded"])
            tags = objects(embedded.get("tags", []))
            next_tag = (
                max(
                    (
                        integer(tag["id"], "tag.id")
                        for lead in self.state["leads"]
                        for tag in objects(obj(lead.get("_embedded", {})).get("tags", []))
                        if "id" in tag
                    ),
                    default=500000,
                )
                + 1
            )
            for tag in tags:
                if "id" not in tag:
                    tag["id"] = next_tag
                    next_tag += 1
                    tag.setdefault("color", None)
        updated["updated_at"] = self.now
        current.clear()
        current.update(updated)
        if kind == "tasks":
            self.refresh_task_deadline(current)
        return current

    def refresh_task_deadline(self, task: Object) -> None:
        if task.get("entity_type") != "leads":
            return
        for lead in self.state["leads"]:
            if lead["id"] == task.get("entity_id"):
                tasks = [t for t in self.state["tasks"] if t["id"] != task["id"]] + [task]
                deadlines = [
                    integer(t.get("complete_till"), "complete_till")
                    for t in tasks
                    if t.get("entity_type") == "leads"
                    and t.get("entity_id") == lead["id"]
                    and not t.get("is_completed")
                ]
                lead["closest_task_at"] = min(deadlines, default=None)

    def create(self, kind: str, payload: Object) -> Object:
        item: Object = {
            "id": self.next_id(kind),
            "account_id": ACCOUNT_ID,
            "created_by": 0,
            "updated_by": 0,
            "created_at": self.now,
            "updated_at": self.now,
            "group_id": 0,
            "responsible_user_id": DEFAULT_USER,
        }
        if kind in ("leads", "contacts"):
            item.update(
                name="Local lead" if kind == "leads" else "Local contact",
                is_deleted=False,
                custom_fields_values=None,
                closest_task_at=None,
                _embedded={"tags": [], "companies": []},
            )
        if kind == "leads":
            item.update(
                price=0,
                price_with_minor_units=0.0,
                pipeline_id=14229720,
                status_id=109869808,
                loss_reason_id=None,
                closed_at=None,
                score=None,
                labor_cost=None,
                source_id=None,
            )
        if kind == "contacts":
            item.update(first_name="", last_name="", is_unsorted=False)
        if kind == "tasks":
            item.update(is_completed=False, text="", result=[], duration=0, task_type_id=1)
        payload = {k: v for k, v in payload.items() if k not in ("id", "account_id", "created_by", "_links")}
        self.update(kind, item, payload)
        self.state[kind].append(item)
        return item

    def envelope(self, kind: str, items: list[Object], path: str) -> Object:
        return {
            "_embedded": {
                kind: [self.render(item, f"{path}/{item.get('id', item.get('uid'))}", kind) for item in items]
            }
        }

    def link(self, lead_id: JsonValue, contact_id: JsonValue) -> None:
        lead = self.find("leads", integer(lead_id, "lead_id"))
        contact = self.find("contacts", integer(contact_id, "contact_id"))
        for parent, collection, child in [(lead, "contacts", contact), (contact, "leads", lead)]:
            embedded = obj(parent.setdefault("_embedded", {}))
            links = objects(embedded.get(collection, []))
            if not any(link["id"] == child["id"] for link in links):
                links.append(
                    {"id": child["id"], **({"is_main": not links} if collection == "contacts" else {})}
                )
            embedded[collection] = list(links)
            parent["updated_at"] = self.now

    def handle(self, method: str, path: str, body: JsonValue) -> JsonValue:
        path = path.strip("/")
        parts = path.split("/")
        if parts[:2] == ["leads", "pipelines"] and method == "GET":
            if len(parts) == 2:
                return self.collection("pipelines", self.state["pipelines"], path)
            pipeline = self.find("pipelines", parts[2])
            if len(parts) == 3:
                return self.render(pipeline, path, "pipelines")
            if len(parts) == 5 and parts[3] == "statuses":
                try:
                    return self.render(self.status(parts[2], parts[4]), path, "statuses")
                except ApiError as error:
                    raise ApiError(404, error.detail) from error
        if parts[:2] == ["leads", "unsorted"]:
            return self.unsorted(method, parts[2:], body)
        if parts == ["leads", "notes"] and method == "POST":
            return self.envelope("notes", [self.create("notes", p) for p in self.batch(body)], "leads/notes")
        if len(parts) == 3 and parts[0] == "leads" and parts[2] == "notes":
            lead = self.find("leads", parts[1])
            if method == "GET":
                notes = [n for n in self.state["notes"] if n["entity_id"] == lead["id"]]
                return self.collection("notes", notes, path)
            if method == "POST":
                return self.envelope(
                    "notes",
                    [self.create("notes", {**p, "entity_id": lead["id"]}) for p in self.batch(body)],
                    path,
                )
        if len(parts) == 3 and parts[0] == "leads" and parts[2] == "link" and method == "POST":
            for link in self.batch(body):
                if link.get("to_entity_type") != "contacts":
                    raise ApiError(400, "Only contact links are supported")
                self.link(parts[1], link.get("to_entity_id"))
            return None
        kind = parts[0]
        if kind not in ("leads", "contacts", "tasks", "users", "roles", "sources", "events"):
            raise ApiError(404, "Unsupported endpoint")
        if len(parts) == 1:
            if method == "GET":
                return self.collection(kind, self.filtered(kind), path)
            if method == "POST" and kind in ("leads", "contacts", "tasks"):
                return self.envelope(kind, [self.create(kind, p) for p in self.batch(body)], path)
        if len(parts) == 2:
            item = self.find(kind, parts[1])
            if method == "GET":
                return None if item.get("is_deleted") else self.render(item, path, kind)
            if method == "PATCH" and kind in ("leads", "contacts", "tasks", "roles"):
                return self.render(self.update(kind, item, obj(body)), path, kind)
        raise ApiError(404, "Unsupported endpoint or method")

    def batch(self, body: JsonValue) -> list[Object]:
        items = objects(body, "request body")
        if not 1 <= len(items) <= 250:
            raise ApiError(400, "Batch size must be 1..250")
        return items

    def unsorted(self, method: str, parts: list[str], body: JsonValue) -> JsonValue:
        if not parts and method == "GET":
            return self.collection("unsorted", self.filtered("unsorted"), "leads/unsorted")
        if parts == ["forms"] and method == "POST":
            created: list[Object] = []
            for payload in self.batch(body):
                pipeline_id = integer(payload.get("pipeline_id"), "pipeline_id")
                pipeline = self.find("pipelines", pipeline_id)
                statuses = objects(obj(pipeline["_embedded"])["statuses"])
                status_id = next((s["id"] for s in statuses if s.get("type") == 1), None)
                embedded = obj(payload.get("_embedded"))
                leads = objects(embedded.get("leads", []))
                contacts = objects(embedded.get("contacts", []))
                if len(leads) != 1 or len(contacts) != 1:
                    raise ApiError(400, "Expected one embedded lead and contact")
                lead = self.create(
                    "leads",
                    {
                        **leads[0],
                        "pipeline_id": pipeline_id,
                        "status_id": status_id,
                        "responsible_user_id": leads[0].get("responsible_user_id", 0),
                    },
                )
                contact = self.create("contacts", contacts[0])
                self.link(lead["id"], contact["id"])
                incoming: Object = {
                    **payload,
                    "uid": uuid.uuid4().hex,
                    "account_id": ACCOUNT_ID,
                    "category": "forms",
                    "created_at": payload.get("created_at", self.now),
                    "_embedded": {"leads": [{"id": lead["id"]}], "contacts": [{"id": contact["id"]}]},
                }
                self.state["unsorted"].append(incoming)
                created.append(incoming)
            return self.envelope("unsorted", created, "leads/unsorted")
        if len(parts) == 2 and method == "POST" and parts[1] in ("accept", "link"):
            incoming = self.find("unsorted", parts[0])
            payload = obj(body)
            embedded = obj(incoming["_embedded"])
            lead = self.find("leads", integer(objects(embedded["leads"])[0]["id"], "lead_id"))
            if parts[1] == "accept":
                self.update(
                    "leads",
                    lead,
                    {
                        "status_id": payload.get("status_id"),
                        "responsible_user_id": lead.get("responsible_user_id") or DEFAULT_USER,
                    },
                )
            else:
                link = obj(payload.get("link"))
                if incoming.get("category") != "chats":
                    raise ApiError(400, "Only unsorted chats can be linked")
                if link.get("entity_type") != "leads":
                    raise ApiError(400, "Expected link.entity_type=leads")
                target = self.find("leads", integer(link.get("entity_id"), "entity_id"))
                if target["id"] == lead["id"]:
                    raise ApiError(400, "Cannot link unsorted to itself")
                metadata = obj(link.get("metadata", {}))
                contacts = objects(embedded.get("contacts", []))
                contact_id = metadata.get("contact_id") or (contacts[0]["id"] if contacts else None)
                if contact_id is not None:
                    self.link(target["id"], contact_id)
                lead["is_deleted"] = True
                for contact in self.state["contacts"]:
                    links = obj(contact.get("_embedded", {}))
                    if "leads" in links:
                        links["leads"] = [r for r in objects(links["leads"]) if r["id"] != lead["id"]]
            self.state["unsorted"].remove(incoming)
            return None
        raise ApiError(404, "Unsupported unsorted endpoint")
