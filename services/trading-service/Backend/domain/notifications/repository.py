from abc import ABC, abstractmethod
from typing import Optional, List

from Backend.domain.notifications.models import NotificationEvent


class NotificationRepository(ABC):


    @abstractmethod
    def save_event(
        self,
        event: NotificationEvent
    ) -> NotificationEvent:
        """
        Store new notification event.
        """
        pass



    @abstractmethod
    def get_pending_events(
        self,
        limit: int = 100
    ) -> List[NotificationEvent]:
        """
        Fetch unsent notification events.
        """
        pass



    @abstractmethod
    def mark_sent(
        self,
        event_id: int
    ) -> None:
        """
        Mark notification as successfully delivered.
        """
        pass



    @abstractmethod
    def mark_failed(
        self,
        event_id: int,
        error: str
    ) -> None:
        """
        Mark notification delivery failure.
        """
        pass



    @abstractmethod
    def get_by_id(
        self,
        event_id: int
    ) -> Optional[NotificationEvent]:
        """
        Retrieve single notification event.
        """
        pass