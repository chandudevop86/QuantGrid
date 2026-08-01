from Backend.domain.notifications.events import NotificationEventType
from Backend.domain.notifications.models import NotificationChannel


class OrderEventPublisher:


    def __init__(
        self,
        notification_service
    ):
        self.notification_service = notification_service



    def order_created(
        self,
        order_id: str,
        symbol: str
    ):

        self.notification_service.create_notification(

            event_type=NotificationEventType.ORDER_CREATED,

            subject="Order Created",

            message=f"Order created for {symbol}",

            channel=NotificationChannel.TELEGRAM,

            order_id=order_id,

            symbol=symbol,
        )



    def order_submitted(
        self,
        order_id: str,
        symbol: str
    ):

        self.notification_service.create_notification(

            event_type=NotificationEventType.ORDER_SUBMITTED,

            subject="Order Submitted",

            message=f"Order submitted to broker for {symbol}",

            channel=NotificationChannel.TELEGRAM,

            order_id=order_id,

            symbol=symbol,
        )



    def order_filled(
        self,
        order_id: str,
        symbol: str,
        price: float
    ):

        self.notification_service.create_notification(

            event_type=NotificationEventType.ORDER_FILLED,

            subject="Order Filled",

            message=f"{symbol} order filled at {price}",

            channel=NotificationChannel.TELEGRAM,

            order_id=order_id,

            symbol=symbol,

            payload={
                "fill_price": price
            }
        )



    def order_rejected(
        self,
        order_id: str,
        symbol: str,
        reason: str
    ):

        self.notification_service.create_notification(

            event_type=NotificationEventType.ORDER_REJECTED,

            subject="Order Rejected",

            message=f"{symbol} order rejected: {reason}",

            channel=NotificationChannel.TELEGRAM,

            order_id=order_id,

            symbol=symbol,

            payload={
                "reason": reason
            }
        )



    def risk_breach(
        self,
        message: str
    ):

        self.notification_service.create_notification(

            event_type=NotificationEventType.RISK_BREACH,

            subject="Risk Alert",

            message=message,

            channel=NotificationChannel.TELEGRAM,
        )