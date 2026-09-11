from uuid import UUID

from pydantic import BaseModel, ConfigDict


class EmailJob(BaseModel):
    """Тело сообщения из очереди: то же, что публикует backend.FastStreamEmailQueue."""

    model_config = ConfigDict(frozen=True)

    message_id: UUID
    category: str
    to: str
    subject: str
    html: str
    text: str
