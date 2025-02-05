"""
csv_file.py

Authors:  Zahid Mirza, Shreshth Saxena
Purpose: Handles CSV file operations.
"""

import csv
class CSVFile:
    def __init__(self, file_path, headers) -> None:
        """
        Initializes the CSVFile instance, opens the file, and writes the header row.

        Args:
            file_path (str): The path to the CSV file. The file will be opened in append mode.
            headers (list of str): The header row to be written to the CSV file.

        Raises:
            Exception: If an error occurs while opening the file or writing the header row.
        """
        try: 
            self.file = open(file_path, mode='a+', newline='')
            self.writer = csv.writer(self.file)
            self.writer.writerow(headers)
        except Exception as e:
            print(f"Exception encountered when opening/creating file: {e}")
    def writerow(self, data):
        """
        Writes a single row of data to the CSV file and flushes the file buffer.

        Args:
            data (list): A list of values to be written as a row in the CSV file.

        Raises:
            Exception: If an error occurs while writing to the file.
        """
        try:
            self.writer.writerow(data)
            self.file.flush()
        except Exception as e:
            print(f"Exception encountered when writing to file: {e}")
    def close(self):
        """
        Closes the CSV file.

        This method should be called when finished writing to ensure that all data is properly saved and 
        resources are released.

        Raises:
            Exception: If an error occurs while closing the file.
        """
        try:
            self.file.close()
        except Exception as e:
            print(f"Exception encountered when closing file: {e}")