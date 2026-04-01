"""Constants for event types and weights."""

ALLOWED_EVENT_TYPES = {
    "like_post", "like_reel",
    "comment_post", "comment_reel",
    "share_post", "message",
    "view_post", "view_reel",
    "view_profile"
}

# Baseline implicit weights (tune later)
EVENT_WEIGHTS: dict[str, float] = {
    "message": 2.0,
    "comment_post": 2.0,
    "comment_reel": 2.0,
    "share_post": 1.5,
    "like_post": 1.0,
    "like_reel": 1.0,
    "view_profile": 1.0,
    "view_post": 0.1,
    "view_reel": 0.1
}


def cap_for_event(event_type: str) -> int:
    """
    Cap tổng số event trong 1 cửa sổ thời gian (xấp xỉ rule theo ngày trong docs):
    - message: ~20
    - view: ~50
    - còn lại: 300
    """
    if event_type == "message":
        return 20
    if event_type == "view_profile":
        return 10
    if event_type in ("view_post", "view_reel"):
        return 50
    return 300
