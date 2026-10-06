"""Errors shared by the generators and the web layer."""


class SettingsError(ValueError):
    """The submitted settings cannot be built, for a reason the form fields alone
       cannot express (for example, a hole grid that needs a bin larger than the
       maximum size).

       The message is shown to the user as-is, so write it for them: say what is
       wrong and what to change."""
