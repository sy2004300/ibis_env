class UIProjectError(Exception):
    """A user-facing project-management failure."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class ProjectValidationError(UIProjectError):
    pass


class ProjectStateError(UIProjectError):
    pass


class ProjectStorageError(UIProjectError):
    pass


class ExcelImportError(UIProjectError):
    pass
