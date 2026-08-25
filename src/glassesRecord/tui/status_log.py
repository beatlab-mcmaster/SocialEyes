class StatusLogController:
    def __init__(self, max_len: int):
        self._messages = []
        self._max_len = max_len

    def push(self, message: str) -> str:
        """
        Adds a new message to the log and returns the current log text.
        If the log exceeds the maximum length (`_max_len`), it will remove the oldest messages.
        """
        self._messages.append(message)
        self._messages = self._messages[-self._max_len:]
        return self.text

    @property
    def text(self) -> str:
        return '\n'.join(self._messages)