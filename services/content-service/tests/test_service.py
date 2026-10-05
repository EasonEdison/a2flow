from typing import cast

import pytest

from a2flow_content.errors import ContentError
from a2flow_content.models import (
    Environment,
    ListPeopleQuery,
    ResolvePeopleQuery,
    TrustedContext,
)
from a2flow_content.service import ContentRepository, ContentService, markdown_to_text


def people_service() -> ContentService:
    return ContentService(cast(ContentRepository, object()))


def test_markdown_to_text_preserves_literal_content_and_code() -> None:
    source = "# 标题\n\nuser_id 与 a*b\n\n`code_value`\n\n```python\nx_y = a * b\n```"
    result = markdown_to_text(source)
    assert "user_id" in result
    assert "a*b" in result
    assert "code_value" in result
    assert "x_y = a * b" in result
    assert "# 标题" not in result


def test_people_list_is_stable_typed_and_paged() -> None:
    result = people_service().list_people(
        TrustedContext(7, Environment.PRT, "list-people-first"), ListPeopleQuery()
    )

    assert result.total == 15
    assert result.page == 1
    assert result.page_size == 5
    assert [item.person_id for item in result.items] == [
        "demo-person-001",
        "demo-person-002",
        "demo-person-003",
        "demo-person-004",
        "demo-person-005",
    ]
    assert result.items[0].phone == "138****0001"


def test_people_list_last_and_out_of_range_pages() -> None:
    service = people_service()
    context = TrustedContext(-9, Environment.ONLINE, "list-people-tail")

    last_page = service.list_people(context, ListPeopleQuery(page=3, page_size=5))
    assert len(last_page.items) == 5
    assert last_page.items[-1].person_id == "demo-person-015"

    empty_page = service.list_people(context, ListPeopleQuery(page=4, page_size=5))
    assert empty_page.items == ()
    assert empty_page.total == 15


def test_resolve_people_preserves_id_order() -> None:
    result = people_service().resolve_people(
        TrustedContext(7, Environment.PRT, "resolve-people"),
        ResolvePeopleQuery(("demo-person-003", "demo-person-001")),
    )

    assert [item.person_id for item in result] == ["demo-person-003", "demo-person-001"]
    assert result[0].name == "苏晚晴"
    assert result[1].phone == "138****0001"


def test_resolve_people_rejects_unknown_id_without_partial_result() -> None:
    with pytest.raises(ContentError, match="PERSON_NOT_FOUND"):
        people_service().resolve_people(
            TrustedContext(7, Environment.PRT, "resolve-people-missing"),
            ResolvePeopleQuery(("demo-person-001", "demo-person-999")),
        )
