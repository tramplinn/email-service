from uuid import UUID

import pytest
from pydantic import ValidationError

from email_service.models import EmailJob


def test_parses_the_wire_shape_published_by_backend() -> None:
    job = EmailJob.model_validate(
        {
            "message_id": "6f9619ff-8b86-d011-b42d-00cf4fc964ff",
            "category": "auth_otp",
            "to": "student@example.com",
            "subject": "Код для входа: 482913",
            "html": "<p>482913</p>",
            "text": "482913",
        },
    )

    assert job.message_id == UUID("6f9619ff-8b86-d011-b42d-00cf4fc964ff")
    assert job.to == "student@example.com"


def test_rejects_missing_fields() -> None:
    with pytest.raises(ValidationError):
        EmailJob.model_validate({"message_id": "6f9619ff-8b86-d011-b42d-00cf4fc964ff"})
