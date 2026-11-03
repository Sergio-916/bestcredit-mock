from pydantic import JsonValue, TypeAdapter

type Object = dict[str, JsonValue]
type State = dict[str, list[Object]]

KINDS = (
    "leads",
    "contacts",
    "users",
    "roles",
    "pipelines",
    "sources",
    "tasks",
    "notes",
    "events",
    "unsorted",
)
ACCOUNT_ID = 33749143
DEFAULT_USER = 12238931
JSON_ADAPTER = TypeAdapter(JsonValue)


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail


def obj(value: JsonValue, label: str = "object") -> Object:
    if not isinstance(value, dict):
        raise ApiError(400, f"Expected {label} to be an object")
    return value


def objects(value: JsonValue, label: str = "items") -> list[Object]:
    if not isinstance(value, list):
        raise ApiError(400, f"Expected {label} to be an array")
    return [obj(item, label) for item in value]


def integer(value: JsonValue, label: str, minimum: int = 1) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ApiError(400, f"{label} must be an integer >= {minimum}")
    try:
        result = int(value)
    except ValueError:
        raise ApiError(400, f"{label} must be an integer >= {minimum}") from None
    if result < minimum:
        raise ApiError(400, f"{label} must be an integer >= {minimum}")
    return result


def field(field_id: int, name: str, value: JsonValue, kind: str = "text", enum: int | None = None) -> Object:
    entry: Object = {"value": value}
    if enum is not None:
        entry.update(enum_id=enum, enum_code=None)
    return {
        "field_id": field_id,
        "field_name": name,
        "field_code": None,
        "field_type": kind,
        "values": [entry],
    }


def seed(now: int) -> State:
    state: State = {kind: [] for kind in KINDS}
    for index, user_id in enumerate(
        [
            10888195,
            DEFAULT_USER,
            12268171,
            12630411,
            13716683,
            14681896,
            14830664,
            15813732,
            12295123,
            12267995,
        ]
    ):
        state["users"].append(
            {
                "id": user_id,
                "name": f"Local Manager {index + 1}",
                "email": f"manager{index + 1}@example.test",
                "lang": "ru",
                "rights": {
                    "is_active": True,
                    "is_admin": index == 0,
                    "is_free": False,
                    "group_id": 0,
                    "role_id": 1,
                },
                "invite_status": "invite_accepted",
                "_embedded": {"roles": [{"id": 1, "name": "Local Sales"}], "groups": []},
            }
        )
    state["roles"] = [
        {
            "id": 1,
            "name": "Local Sales",
            "rights": {
                "leads": {"view": "A", "edit": "A", "add": "A", "delete": "A", "export": "A"},
                "status_rights": [],
            },
            "_embedded": {"users": [{"id": u["id"]} for u in state["users"]]},
        }
    ]
    pipelines = [
        (14229720, "INCOMING", [(109869804, "Неразобранное"), (109869808, "To Assign Leads")]),
        (
            14229724,
            "SALES",
            [
                (109869836, "Неразобранное"),
                (109869840, "НЕСОРТИРОВАННЫЕ"),
                (109870156, "New"),
                (109870160, "Contacting"),
                (109870164, "Qualified"),
                (109870168, "Contract"),
                (109870172, "Signed"),
                (109870176, "Payment"),
                (109870180, "Paid"),
                (109870408, "Follow-up"),
            ],
        ),
        (
            14229728,
            "TECH",
            [
                (109869852, "Неразобранное"),
                (109869856, "New"),
                (110040496, "In progress"),
                (110040500, "Review"),
                (110040516, "ЗАКРЫТО - УСПЕШНО"),
                (110040520, "ЗАКРЫТО - НЕУСПЕШНО"),
            ],
        ),
    ]
    pipelines.extend(
        [
            (13946200, "INSIGHT (local)", [(107625060, "Incoming")]),
            (13859772, "AI QUALIFIER (local)", [(107001320, "Delivered"), (108629556, "Launch")]),
            (
                9914723,
                "BANGTAO (local)",
                [(76131627, "New"), (82836231, "Assign"), (108167608, "AI qualifier")],
            ),
            (10148543, "NAI YANG (local)", [(77882791, "New"), (77882795, "Assign")]),
        ]
    )
    for position, (pipeline_id, name, statuses) in enumerate(pipelines):
        entries: list[JsonValue] = []
        for sort, (status_id, title) in enumerate(statuses + [(142, "Closed - Won"), (143, "Closed - Lost")]):
            entries.append(
                {
                    "id": status_id,
                    "name": title,
                    "sort": (sort + 1) * 10,
                    "pipeline_id": pipeline_id,
                    "is_editable": status_id not in (142, 143),
                    "color": "#99ccff",
                    "type": 1 if sort == 0 else 0,
                    "account_id": ACCOUNT_ID,
                }
            )
        state["pipelines"].append(
            {
                "id": pipeline_id,
                "name": name,
                "sort": position + 1,
                "is_main": position == 0,
                "is_unsorted_on": True,
                "is_archive": False,
                "account_id": ACCOUNT_ID,
                "_embedded": {"statuses": entries},
            }
        )
    state["contacts"] = [
        {
            "id": 37514079,
            "name": "Test Client",
            "first_name": "Test",
            "last_name": "Client",
            "responsible_user_id": 13716683,
            "group_id": 0,
            "created_by": 0,
            "updated_by": 0,
            "created_at": now,
            "updated_at": now,
            "is_deleted": False,
            "is_unsorted": False,
            "closest_task_at": None,
            "account_id": ACCOUNT_ID,
            "custom_fields_values": [
                {
                    "field_id": 584388,
                    "field_name": "Phone",
                    "field_code": "PHONE",
                    "field_type": "multitext",
                    "values": [{"value": "+12025550123", "enum_id": 474474, "enum_code": "WORK"}],
                },
                {
                    "field_id": 584390,
                    "field_name": "Email",
                    "field_code": "EMAIL",
                    "field_type": "multitext",
                    "values": [{"value": "client@example.test", "enum_code": "WORK"}],
                },
            ],
            "_embedded": {"leads": [{"id": 33579273}], "tags": [], "companies": []},
        }
    ]
    fields: list[JsonValue] = [
        field(1330343, "Client's Full Name", "Test Client"),
        field(1330347, "Client's Date of Birth", 631195200, "date"),
        field(1330351, "Address (OLD)", "123 Test Street, Test City, CA 90001"),
        field(1332123, "Address (NEW)", "123 Test Street, Test City, CA 90001", "textarea"),
        field(1330353, "Telephone", "+12025550123", "numeric"),
        field(1330355, "Email", "client@example.test"),
        field(1330357, "Service Package", "Test service"),
        field(1330363, "Enrollment / Analysis Fee ($)", "200", "numeric"),
        field(1330365, "Number of Payments", "8", "numeric"),
        field(1330367, "Payment Amount ($)", "280", "numeric"),
        field(1330373, "Estimated Total Cost ($)", "2440", "numeric"),
        field(1330369, "Frequency", "every 2 weeks", "select", 1113697),
        field(1330375, "Payment Method", "card", "select", 1113703),
        field(1330545, "Contract type", "short payment", "select", 1114013),
        field(1330381, "Agreement Date", now, "date"),
        field(1330371, "First Payment Date", now + 86400 * 14, "date"),
    ]
    state["leads"] = [
        {
            "id": 33579273,
            "name": "Test Client",
            "price": 0,
            "price_with_minor_units": 0.0,
            "responsible_user_id": 13716683,
            "group_id": 0,
            "status_id": 110040496,
            "pipeline_id": 14229728,
            "loss_reason_id": None,
            "created_by": 0,
            "updated_by": 0,
            "created_at": now,
            "updated_at": now,
            "closed_at": None,
            "closest_task_at": now + 86400,
            "is_deleted": False,
            "custom_fields_values": fields,
            "source_id": None,
            "account_id": ACCOUNT_ID,
            "score": None,
            "labor_cost": None,
            "_embedded": {"contacts": [{"id": 37514079, "is_main": True}], "tags": [], "companies": []},
        }
    ]
    state["tasks"] = [
        {
            "id": 4578935,
            "entity_id": 33579273,
            "entity_type": "leads",
            "responsible_user_id": 13716683,
            "is_completed": False,
            "task_type_id": 1,
            "duration": 0,
            "text": "Local follow-up",
            "result": [],
            "complete_till": now + 86400,
            "account_id": ACCOUNT_ID,
            "created_by": 0,
            "updated_by": 0,
            "created_at": now,
            "updated_at": now,
            "group_id": 0,
        }
    ]
    state["notes"] = [
        {
            "id": 12957353,
            "entity_id": 33579273,
            "note_type": "common",
            "params": {"text": "Synthetic local fixture"},
            "account_id": ACCOUNT_ID,
            "responsible_user_id": 13716683,
            "created_by": 0,
            "updated_by": 0,
            "created_at": now,
            "updated_at": now,
            "group_id": 0,
        }
    ]
    return state


def parse_state(value: JsonValue) -> State:
    raw = obj(value, "state")
    if set(raw) - set(KINDS):
        raise ApiError(400, "Unknown state collection")
    result: State = {}
    for kind in KINDS:
        items = objects(raw.get(kind, []), kind)
        ids: set[str] = set()
        for item in items:
            key = "uid" if kind == "unsorted" else "id"
            identifier = item.get(key)
            if kind in ("events", "unsorted"):
                if not isinstance(identifier, str) or not identifier:
                    raise ApiError(400, f"{kind}.{key} must be a non-empty string")
            else:
                integer(identifier, f"{kind}.id")
            if str(identifier) in ids:
                raise ApiError(400, f"Duplicate {kind}.{key}")
            ids.add(str(identifier))
        result[kind] = items
    return result
