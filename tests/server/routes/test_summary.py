import pytest

from supernote.client.client import Client
from supernote.client.summary import SummaryClient
from supernote.models.summary import (
    AddSummaryDTO,
    AddSummaryGroupDTO,
    QuerySummaryDTO,
    UpdateSummaryDTO,
    UpdateSummaryGroupDTO,
)


@pytest.fixture
def summary_client(authenticated_client: Client) -> SummaryClient:
    """Create a SummaryClient."""
    return SummaryClient(authenticated_client)


async def test_summary_tags_crud(summary_client: SummaryClient) -> None:
    # 1. Query initial tags (should be empty)
    response = await summary_client.query_tags()
    assert response.success
    assert len(response.summary_tag_do_list) == 0

    # 2. Add a tag
    add_response = await summary_client.add_tag(name="Work")
    assert add_response.success
    tag_id = add_response.id
    assert tag_id is not None

    # 3. Verify tag was added
    response = await summary_client.query_tags()
    assert len(response.summary_tag_do_list) == 1
    assert response.summary_tag_do_list[0].name == "Work"
    assert response.summary_tag_do_list[0].id == tag_id

    # 4. Update the tag
    update_response = await summary_client.update_tag(tag_id=tag_id, name="Job")
    assert update_response.success

    # 5. Verify update
    response = await summary_client.query_tags()
    assert response.summary_tag_do_list[0].name == "Job"

    # 6. Delete the tag
    delete_response = await summary_client.delete_tag(tag_id=tag_id)
    assert delete_response.success

    # 7. Verify deletion
    response = await summary_client.query_tags()
    assert len(response.summary_tag_do_list) == 0


async def test_summary_crud(summary_client: SummaryClient) -> None:
    # 1. Add a summary
    add_dto = AddSummaryDTO(
        content="This is a test summary",
        data_source="TEST",
        tags="test,summary",
        metadata='{"key": "value"}',
    )
    add_response = await summary_client.add_summary(add_dto)
    assert add_response.success
    summary_id = add_response.id
    assert summary_id is not None

    # 2. Query the summary
    query_response = await summary_client.query_summaries(ids=[summary_id])
    assert query_response.success
    assert len(query_response.summary_do_list) == 1
    summary = query_response.summary_do_list[0]
    assert summary.content == "This is a test summary"
    assert summary.data_source == "TEST"
    assert summary.tags == "test,summary"
    assert summary.metadata == '{"key": "value"}'

    # 3. Update the summary
    update_dto = UpdateSummaryDTO(
        id=summary_id,
        content="Updated test summary",
        tags="updated",
    )
    update_response = await summary_client.update_summary(update_dto)
    assert update_response.success

    # 4. Verify update
    query_response = await summary_client.query_summaries(ids=[summary_id])
    summary = query_response.summary_do_list[0]
    assert summary.content == "Updated test summary"
    assert summary.tags == "updated"

    # 5. Delete the summary
    delete_response = await summary_client.delete_summary(summary_id)
    assert delete_response.success

    # 6. Verify deletion
    query_response = await summary_client.query_summaries(ids=[summary_id])
    assert len(query_response.summary_do_list) == 0


async def test_group_crud(summary_client: SummaryClient) -> None:
    # 1. Add a group
    group_uuid = "test-group-uuid"
    add_dto = AddSummaryGroupDTO(
        unique_identifier=group_uuid,
        name="Test Group",
        md5_hash="hash123",
        description="A test group",
    )
    add_response = await summary_client.add_group(add_dto)
    assert add_response.success
    group_id = add_response.id
    assert group_id is not None

    # 2. Query groups
    query_response = await summary_client.query_groups()
    assert query_response.success
    assert [
        (g.id, g.unique_identifier, g.name) for g in query_response.summary_do_list
    ] == [(group_id, group_uuid, "Test Group")]

    # 3. Update group
    update_dto = UpdateSummaryGroupDTO(
        id=group_id,
        unique_identifier=group_uuid,
        name="Updated Group",
        md5_hash="newhash",
    )
    update_response = await summary_client.update_group(update_dto)
    assert update_response.success

    # 4. Verify update
    query_response = await summary_client.query_groups()
    assert [
        (g.id, g.unique_identifier, g.name) for g in query_response.summary_do_list
    ] == [(group_id, group_uuid, "Updated Group")]

    # 5. Delete group
    delete_response = await summary_client.delete_group(group_id)
    assert delete_response.success

    # 6. Verify deletion
    query_response = await summary_client.query_groups()
    assert not any(g.id == group_id for g in query_response.summary_do_list)


async def test_summary_binary_flow(summary_client: SummaryClient) -> None:
    # 1. Apply for upload
    upload_response = await summary_client.upload_apply("test_strokes.bin")
    assert upload_response.success
    assert upload_response.full_upload_url is not None
    assert upload_response.inner_name is not None
    inner_name = upload_response.inner_name

    # 2. Add summary with that inner name
    add_dto = AddSummaryDTO(
        content="Summary with binary",
        data_source="TEST",
        handwrite_inner_name=inner_name,
    )
    add_response = await summary_client.add_summary(add_dto)
    assert add_response.id
    summary_id = add_response.id

    # 3. Apply for download
    download_response = await summary_client.download_summary(summary_id)
    assert download_response.success
    assert download_response.url is not None
    assert inner_name in download_response.url


async def test_advanced_queries(summary_client: SummaryClient) -> None:
    # 1. Setup: Add a test summary
    add_dto = AddSummaryDTO(
        content="Advanced Test content",
        md5_hash="advhash",
        handwrite_md5="advhwmd5",
        comment_handwrite_name="advhw.bin",
    )
    add_response = await summary_client.add_summary(add_dto)
    summary_id = add_response.id
    assert summary_id is not None

    # 2. Test query/summary/hash
    query_dto = QuerySummaryDTO(ids=[summary_id])
    hash_response = await summary_client.query_summary_hash(query_dto)
    assert hash_response.success
    assert len(hash_response.summary_info_vo_list) == 1
    info = hash_response.summary_info_vo_list[0]
    assert info.id == summary_id
    assert info.md5_hash == "advhash"
    assert info.handwrite_md5 == "advhwmd5"
    assert info.comment_handwrite_name == "advhw.bin"

    # 3. Test query/summary/id
    id_response = await summary_client.query_summary_id(query_dto)
    assert id_response.success
    assert len(id_response.summary_do_list) == 1
    summary = id_response.summary_do_list[0]
    assert summary.id == summary_id
    assert summary.content == "Advanced Test content"


async def test_query_summary_hash_pagination(summary_client: SummaryClient) -> None:
    """query/summary/hash must report the true total count and page count."""
    total_summaries = 25
    page_size = 10
    created_ids = []
    for i in range(total_summaries):
        add_dto = AddSummaryDTO(
            content=f"Pagination test summary {i}",
            data_source="TEST",
            source_path=f"/Document/Books/book_{i % 3}.pdf",
        )
        add_response = await summary_client.add_summary(add_dto)
        assert add_response.success
        created_ids.append(add_response.id)
    response = await summary_client.query_summary_hash(
        QuerySummaryDTO(page=1, size=page_size)
    )
    assert response.success
    assert response.total_records == total_summaries
    assert response.total_pages == 1
    assert response.current_page == 1
    assert response.page_size == total_summaries
    assert {item.id for item in response.summary_info_vo_list} == set(created_ids)


async def test_query_summary_hash_returns_full_set_beyond_default_page_size(
    summary_client: SummaryClient,
) -> None:
    """query/summary/hash must never truncate to a fixed page size.
    Regression test: the real Supernote device only ever requests page 1
    of this sync-manifest endpoint and never paginates further, even when
    totalPages correctly reports more than one page. A user with many
    summaries for a single book (e.g. 130+ digest entries) must therefore
    get every one of them back in a single call, not just a default-sized
    first page.
    """
    total_summaries = 131
    created_ids = []
    for i in range(total_summaries):
        add_dto = AddSummaryDTO(
            content=f"Digest entry {i}",
            data_source="TEST",
            source_path="/Document/Books/design_of_everyday_things.pdf",
        )
        add_response = await summary_client.add_summary(add_dto)
        assert add_response.success
        created_ids.append(add_response.id)
    # Default request shape: no explicit size, as the real device sends.
    response = await summary_client.query_summary_hash(QuerySummaryDTO())
    assert response.success
    assert response.total_records == total_summaries
    assert response.total_pages == 1
    assert response.current_page == 1
    assert response.page_size == total_summaries
    assert len(response.summary_info_vo_list) == total_summaries
    assert {item.id for item in response.summary_info_vo_list} == set(created_ids)


async def test_query_summary_group_pagination(summary_client: SummaryClient) -> None:
    """query/summary/group must report the true total count and page count."""
    total_groups = 5
    page_size = 2
    created_ids = []
    for i in range(total_groups):
        add_dto = AddSummaryGroupDTO(
            unique_identifier=f"pagination-group-{i}",
            name=f"Group {i}",
            md5_hash=f"hash-{i}",
        )
        add_response = await summary_client.add_group(add_dto)
        assert add_response.success
        created_ids.append(add_response.id)

    response = await summary_client.query_groups(page=1, size=page_size)
    assert response.success
    assert response.total_records == total_groups
    assert response.total_pages == 3
    assert len(response.summary_do_list) == page_size

    response_last = await summary_client.query_groups(page=3, size=page_size)
    assert response_last.total_records == total_groups
    assert response_last.total_pages == 3
    assert len(response_last.summary_do_list) == 1


async def test_delete_summary_device_alias(
    summary_client: SummaryClient, authenticated_client: Client
) -> None:
    """DELETE /api/file/delete/summary must work like the POST route.
    Regression test: the real device issues DELETE (not POST) with body
    {"id": <int>} when deleting a digest/summary entry -- confirmed via
    trace log -- and previously got a 404 since only the POST alias
    existed.
    """
    add_dto = AddSummaryDTO(content="To be deleted via DELETE verb")
    add_response = await summary_client.add_summary(add_dto)
    assert add_response.success
    summary_id = add_response.id
    assert summary_id is not None
    resp = await authenticated_client.request(
        "delete", "/api/file/delete/summary", json={"id": summary_id}
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["success"] is True
    query_response = await summary_client.query_summaries(ids=[summary_id])
    assert len(query_response.summary_do_list) == 0


async def test_update_summary_device_alias(
    summary_client: SummaryClient, authenticated_client: Client
) -> None:
    """PUT /api/file/update/summary must work like the POST route.
    Regression test: the real device issues PUT (not POST) with the full
    UpdateSummaryDTO body when it re-syncs/edits an existing summary --
    confirmed via trace log -- and previously got a 404 since only the
    POST alias existed.
    """
    add_dto = AddSummaryDTO(content="Original content")
    add_response = await summary_client.add_summary(add_dto)
    assert add_response.success
    summary_id = add_response.id
    assert summary_id is not None
    resp = await authenticated_client.request(
        "put",
        "/api/file/update/summary",
        json={"id": summary_id, "content": "Updated via PUT verb"},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body["success"] is True
    query_response = await summary_client.query_summaries(ids=[summary_id])
    assert len(query_response.summary_do_list) == 1
    assert query_response.summary_do_list[0].content == "Updated via PUT verb"
