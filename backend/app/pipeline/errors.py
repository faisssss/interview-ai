class PermanentPipelineError(Exception):
    """A failure that retrying cannot fix. Its message is shown to the user."""
