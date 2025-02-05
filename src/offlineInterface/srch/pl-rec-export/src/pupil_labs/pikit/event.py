class Event(object):
    def __init__(self, name, epoch_ns, offset_ns):
        self.name = name
        self.epoch_ns = epoch_ns
        self.offset_ns = offset_ns

    def __repr__(self):
        return (
            f"<{self.__class__.__name__} "
            + ", ".join(
                f"{attr}={getattr(self, attr, '?')!r}"
                for attr in ["epoch_ns", "offset_ns", "name"]
            )
            + ">"
        )
