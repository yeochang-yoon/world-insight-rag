class ServiceError(Exception):
    """Only controlled, public-safe messages may cross the UI boundary."""


UNAVAILABLE = "제공된 문서에서 확인할 수 없습니다."
