class AIOperationError(Exception):
    """
    Raised when an AI operation fails or returns unusable output.

    Carried through to the API error envelope. ``retryable`` tells the frontend
    whether to offer a Retry action.
    """

    def __init__(self, code: str, message: str, retryable: bool = False, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable
        self.details = details
