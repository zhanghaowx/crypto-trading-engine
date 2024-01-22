from datetime import datetime, timedelta


class TimeRange:
    """
    Represents a time range
    """

    def __init__(self, start: datetime, end: datetime):
        self.start = start
        self.end = end

    def generate_time_ranges(
        self, interval_in_minutes: int
    ) -> list["TimeRange"]:
        """
        Generates a list of smaller time ranges from a bigger time range. Each
        time range shall be exactly inter_in_minutes minutes, except the last
        one which might be smaller than it.

        Args:
            interval_in_minutes: Interval of the smaller time range
        Returns:
            A list of smaller time ranges
        """
        time_ranges = list[TimeRange]()

        current_time = self.start
        while (self.end - current_time).total_seconds() > 1:
            next_time = min(
                self.end, current_time + timedelta(minutes=interval_in_minutes)
            )
            time_ranges.append(TimeRange(current_time, next_time))
            current_time = next_time

        return time_ranges
