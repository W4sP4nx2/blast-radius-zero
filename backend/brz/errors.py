from .presets import preset_ids


class ControlError(Exception):
    def __init__(self, reason: str, message: str, status: int = 503, retry_after: int = 0):
        super().__init__(message)
        self.reason, self.message, self.status, self.retry_after = reason, message, status, retry_after

    def detail(self):
        return {"reason": self.reason, "message": self.message,
                "retry_after": self.retry_after, "available_presets": preset_ids()}
