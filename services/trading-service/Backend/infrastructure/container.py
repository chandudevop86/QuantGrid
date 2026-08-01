from Backend.infrastructure.database.postgres_notification_repository import (
    PostgresNotificationRepository
)

from Backend.application.notification_service import (
    NotificationService
)

from Backend.application.events.order_event_publisher import (
    OrderEventPublisher
)


class Container:
    """
    Application dependency container.

    Creates and shares application services.
    """


    def __init__(
        self,
        db
    ):

        self.db = db


        # Database layer
        self.notification_repository = (
            PostgresNotificationRepository(
                db=self.db
            )
        )


        # Application layer
        self.notification_service = (
            NotificationService(
                repository=self.notification_repository
            )
        )


        # Event layer
        self.order_event_publisher = (
            OrderEventPublisher(
                notification_service=self.notification_service
            )
        )


    def get_notification_service(self):

        return self.notification_service



    def get_order_event_publisher(self):

        return self.order_event_publisher