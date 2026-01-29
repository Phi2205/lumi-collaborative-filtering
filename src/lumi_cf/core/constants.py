ALLOWED_EVENT_TYPES = {"like", "comment", "share", "message", "view"}

# Baseline implicit weights (tune later)
EVENT_WEIGHTS: dict[str, float] = {
    "message": 2.0,
    "comment": 2.0,
    "share": 1.5,
    "like": 1.0,
    "view": 0.1,
}


def cap_for_event(event_type: str) -> int:
    """
    Cap tổng số event trong 1 cửa sổ thời gian (xấp xỉ rule theo ngày trong docs):
    - message: ~20 (tương đương 20/ngày trong 1 cửa sổ nhỏ)
    - view: ~50
    - còn lại: 300
    """
    if event_type == "message":
        return 20
    if event_type == "view":
        return 50
    return 300

