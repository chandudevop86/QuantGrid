from app.config import settings


SYMBOL_CONFIG = {
    "NIFTY": {
        "security_id": settings.DHAN_SECURITY_ID_NIFTY,
        "exchange_segment": settings.DHAN_EXCHANGE_SEGMENT_INDEX,
    },
    "BANKNIFTY": {
        "security_id": settings.DHAN_SECURITY_ID_BANKNIFTY,
        "exchange_segment": settings.DHAN_EXCHANGE_SEGMENT_INDEX,
    },
    "FINNIFTY": {
        "security_id": settings.DHAN_SECURITY_ID_FINNIFTY,
        "exchange_segment": settings.DHAN_EXCHANGE_SEGMENT_INDEX,
    },
    "MIDCPNIFTY": {
        "security_id": settings.DHAN_SECURITY_ID_MIDCPNIFTY,
        "exchange_segment": settings.DHAN_EXCHANGE_SEGMENT_INDEX,
    },
}