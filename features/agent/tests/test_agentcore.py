from datetime import datetime, timedelta, timezone

from bedrock_agentcore import BedrockAgentCoreApp
from roam_contracts.models import (
    GeoPoint,
    Lodging,
    Pace,
    PlaceRef,
    PlanSelection,
    SegmentMode,
    TravelMode,
    TravelSegment,
    TripBrief,
)

from roam_agent.agentcore_app import handle_invocation, set_store
from roam_agent.dynamo_store import DynamoPlanStore
from roam_agent.llm import build_model, model_settings
from roam_agent.store import PlanRecord

JST = timezone(timedelta(hours=9))


def _brief() -> TripBrief:
    return TripBrief(
        destination="Kyoto, Japan",
        timezone="Asia/Tokyo",
        arrival=TravelSegment(
            mode=SegmentMode.FLIGHT, number="JL3020", carrier="JL",
            from_place=PlaceRef(code="HND", name="Haneda"),
            to_place=PlaceRef(code="KIX", name="Kansai", location=GeoPoint(lat=34.4347, lng=135.244)),
            depart_at=datetime(2026, 11, 14, 9, 20, tzinfo=JST),
            arrive_at=datetime(2026, 11, 14, 10, 35, tzinfo=JST),
            source="fixture",
        ),
        departure=TravelSegment(
            mode=SegmentMode.FLIGHT, number="JL3025", carrier="JL",
            from_place=PlaceRef(code="KIX", name="Kansai", location=GeoPoint(lat=34.4347, lng=135.244)),
            to_place=PlaceRef(code="HND", name="Haneda"),
            depart_at=datetime(2026, 11, 16, 18, 20, tzinfo=JST),
            arrive_at=datetime(2026, 11, 16, 19, 35, tzinfo=JST),
            source="fixture",
        ),
        lodging=[Lodging(name="Hotel Granvia Kyoto", location=GeoPoint(lat=34.9858, lng=135.7588), check_in=datetime(2026, 11, 14, 15, tzinfo=JST), check_out=datetime(2026, 11, 16, 11, tzinfo=JST))],
        budget="200.00",
        interests=["temples"],
        pace=Pace.BALANCED,
        preferred_modes=[TravelMode.WALK],
        daily_start="09:00",
        daily_end="21:00",
    )


def test_entrypoint_plans_from_the_scripted_fixtures(monkeypatch):
    monkeypatch.setenv("ROAM_SCRIPTED_AGENT", "1")
    monkeypatch.delenv("ROAM_PLAN_STORE", raising=False)
    set_store(None)
    result = handle_invocation({
        "action": "plan",
        "plan_id": "kyoto-demo",
        "brief": _brief().model_dump(mode="json"),
        "selection": {"must_visit": ["bamboo-grove", "tenryuji"], "maybe": [], "excluded": []},
    })
    ids = {stop["id"] for day in result["itinerary"]["days"] for stop in day["stops"]}
    assert {"bamboo-grove", "tenryuji"} <= ids
    assert result["config"]["plan_store"] == "memory"
    other = handle_invocation({
        "action": "plan",
        "brief": _brief().model_dump(mode="json"),
        "selection": {"must_visit": [], "maybe": [], "excluded": []},
    })
    assert other["plan_id"] != result["plan_id"]
    assert result["config"]["tools_mcp_url"].endswith(":8003/mcp")


def test_runtime_exposes_ping():
    app = BedrockAgentCoreApp()
    paths = {getattr(route, "path", None) for route in app.routes}
    assert "/ping" in paths
    assert "/invocations" in paths


def test_bedrock_provider_selects_the_bedrock_model_id(monkeypatch):
    monkeypatch.setenv("ROAM_LLM_PROVIDER", "bedrock")
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    settings = model_settings()
    assert settings["provider"] == "bedrock"
    assert settings["model_id"].startswith("anthropic.claude")
    assert settings["region"] == "us-west-2"
    try:
        build_model()
    except RuntimeError as exc:
        assert "strands-agents" in str(exc)


def test_default_provider_stays_local(monkeypatch):
    monkeypatch.delenv("ROAM_LLM_PROVIDER", raising=False)
    assert model_settings()["provider"] == "anthropic"
    assert build_model() is None


class _Table:
    def __init__(self):
        self.items = {}

    def put_item(self, TableName, Item):
        self.items[(TableName, Item["plan_id"]["S"])] = Item

    def get_item(self, TableName, Key):
        item = self.items.get((TableName, Key["plan_id"]["S"]))
        return {"Item": item} if item else {}


def test_dynamo_store_round_trip():
    store = DynamoPlanStore("roam-plans", client=_Table())
    brief = _brief()
    store.put(PlanRecord(plan_id="p1", brief=brief))
    loaded = store.get("p1")
    assert loaded is not None
    assert loaded.brief.destination == "Kyoto, Japan"
    assert store.get("missing") is None
    selection = PlanSelection(must_visit=["bamboo-grove"], maybe=[], excluded=[])
    assert selection.must_visit == ["bamboo-grove"]
