class ProjectWorkflowError(Exception):
    """
    A workflow/validation problem in a project operation (bad stage, incomplete
    or invalid discovery answers, ...). Rendered to the uniform API error
    envelope by ``common.exception_handler``.
    """

    def __init__(self, code: str, message: str, status: int = 400, details=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status
        self.details = details
