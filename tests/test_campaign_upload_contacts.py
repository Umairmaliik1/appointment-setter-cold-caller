from io import BytesIO

import pytest
from starlette.datastructures import UploadFile

from app.api.v1.schemas.campaign import CampaignComplianceConfig
from app.services.campaign_service import campaign_service


@pytest.mark.asyncio
async def test_upload_contacts_rejects_invalid_and_dedupe_and_dnc(monkeypatch):
    campaign = {
        "id": "cmp-1",
        "tenant_id": "tenant-1",
        "status": "draft",
        "compliance": CampaignComplianceConfig().model_dump(),
        "total_contacts": 0,
    }
    current_user = {"id": "user-1", "role": "admin"}
    csv_bytes = (
        "phone_number,name,notes\n"
        "+14155550111,Alice,ok\n"
        "+14155550111,Alice Duplicate,dup\n"
        "abc,Bad,invalid\n"
        "+14155550122,Bob,dnc\n"
    ).encode()
    upload = UploadFile(filename="contacts.csv", file=BytesIO(csv_bytes))

    accepted_store = {"rows": []}

    async def _get_campaign_or_404(_campaign_id):
        return campaign

    def _verify_tenant_access(_user, _tenant_id):
        return None

    async def _get_dnc_phone_set(_tenant_id):
        return {"+14155550122"}

    async def _get_contact_by_phone(_campaign_id, _phone):
        return None

    async def _create_contacts_bulk(rows):
        accepted_store["rows"] = rows

    async def _update_campaign(_campaign_id, _updates):
        return campaign

    async def _event(*_args, **_kwargs):
        return None

    monkeypatch.setattr(campaign_service, "_get_campaign_or_404", _get_campaign_or_404)
    monkeypatch.setattr(campaign_service, "_verify_tenant_access", _verify_tenant_access)
    monkeypatch.setattr("app.services.campaign_service.campaign_repository.get_dnc_phone_set", _get_dnc_phone_set)
    monkeypatch.setattr("app.services.campaign_service.campaign_repository.get_contact_by_phone", _get_contact_by_phone)
    monkeypatch.setattr("app.services.campaign_service.campaign_repository.create_contacts_bulk", _create_contacts_bulk)
    monkeypatch.setattr("app.services.campaign_service.campaign_repository.update_campaign", _update_campaign)
    monkeypatch.setattr(campaign_service, "_event", _event)

    result = await campaign_service.upload_contacts(campaign_id="cmp-1", file=upload, current_user=current_user)

    assert result.accepted_count == 1
    assert result.rejected_count == 3
    assert accepted_store["rows"][0]["phone_number"] == "+14155550111"

