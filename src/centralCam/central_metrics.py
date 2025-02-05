"""
central_metrics.py

Authors:  Zahid Mirza, Shreshth Saxena
Purpose: Managing and calculating metrics related to timestamps and frame processing of the centralview.
"""


from csv_file import CSVFile

class CentralMetrics:
    def __init__(self, metrics_file_path, metrics_headers, timestamp_file_path, timestamp_headers) -> None:
        """
        Initializes the CentralMetrics instance with file paths and headers for CSV files.

        Args:
            metrics_file_path (str): Path to the CSV file for storing central metrics (jitter and FPS).
            metrics_headers (list of str): Headers for the central metrics CSV file.
            timestamp_file_path (str): Path to the CSV file for storing individual frame timestamps.
            timestamp_headers (list of str): Headers for the timestamp CSV file.
        """
        self.all_timestamps = []
        self.all_timestamps_diff = []
        self.central_metrics_csv = CSVFile(metrics_file_path, metrics_headers)
        self.central_timestamps_csv = CSVFile(timestamp_file_path, timestamp_headers)

    def _calculate_average_timestamp_diff(self):
        """
        Calculates the average difference between consecutive timestamps.

        Returns:
            float: The average timestamp difference in nanoseconds.
        """
        sum_of_all_timestamps_diffs = 0
        for i in range(len(self.all_timestamps) - 1):
            sum_of_all_timestamps_diffs += self.all_timestamps[i + 1] - self.all_timestamps[i]
        return sum_of_all_timestamps_diffs / (len(self.all_timestamps) - 1)
    
    def _calculate_jitter(self):
        """
        Calculates the jitter as the standard deviation of the timestamp differences, normalized to seconds.

        Args:
            window_size (int): The number of timestamps to consider for the jitter calculation.

        Returns:
            float: The jitter in seconds.
        """
        sum_of_average_timestamp_diff_sq = (self._calculate_average_timestamp_diff()) ** 2
        sum_of_sq_average_timestamp_diff = sum(elem ** 2 for elem in self.all_timestamps_diff)
        variance = sum_of_sq_average_timestamp_diff / len(self.all_timestamps_diff) - sum_of_average_timestamp_diff_sq
        st_dev = variance ** (1 / 2)
        return st_dev / 1e9
    
    def _calculate_fps(self, window_size):
        """
        Calculates the frames per second (FPS) over a given window size.

        Args:
            window_size (int): The number of timestamps to consider for the FPS calculation.

        Returns:
            float: The FPS over the specified window size.
        """
        start = self.all_timestamps[len(self.all_timestamps) - window_size] / 1e9
        end = self.all_timestamps[len(self.all_timestamps) - 1] / 1e9
        return window_size / (end - start)
    
    def add_timestamp(self, frame_count, frame_fail_count, timestamp, window_size):
        """
        Updates and logs FPS and jitter to the central metrics CSV file every `window_size` frames.

        Args:
            frame_count (int): The total number of frames processed.
            frame_fail_count (int): The number of frames that failed processing.
            timestamp (int): The timestamp of the current frame in nanoseconds.
            window_size (int): The number of frames to consider for calculating metrics.
        """
        self.all_timestamps.append(timestamp)
        self.central_timestamps_csv.writerow([frame_count, frame_fail_count, timestamp])
        # Only start calculating differences between timestamps once more than one frame has been received
        if len(self.all_timestamps) > 1:
            timestamp_diff = self.all_timestamps[len(self.all_timestamps)-1] - self.all_timestamps[len(self.all_timestamps)-2]
            self.all_timestamps_diff.append(timestamp_diff)
        # Log the results to the central CSV file
        if len(self.all_timestamps) % window_size == 0 and len(self.all_timestamps) > 0:
            fps = self._calculate_fps(window_size)
            jitter = self._calculate_jitter()
            self.central_metrics_csv.writerow([frame_count, jitter, fps])


class CentralTimestampsOnly:
    def __init__(self, timestamp_file_path, timestamp_headers) -> None:
        self.central_timestamps_csv = CSVFile(timestamp_file_path, timestamp_headers)
    
    def add_timestamp(self, *args):
        """
        Adds a row to central_timestamps_csv. Make sure that the order and number of provided args is correct.
        
        Args:
            *args: Positional arguments representing the values to log, in a consistent order.

        """
        self.central_timestamps_csv.writerow(args)
