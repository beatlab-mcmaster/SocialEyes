"""
csv_processor.py

Author: Biranugan Pirabaharan
Purpose: This class is handles reading/writing to CSV files.
"""
import pandas as pd
import csv
import numpy as np


class CSVProcessor:
    """
    A class for processing CSV files.

    Attributes:
        file_path (str): The path to the CSV file.
        dtype (dict, optional): A dictionary specifying the data types of the columns. Defaults to None.
        cols (list, optional): A list of column names (headers) to write to the CSV file. Defaults to None.

    Methods:
    - read_csv(): Reads the CSV File and returns all data in it as a pandas DataFrame.
    - write_csv(): Writes headers specified to the CSV File
    """

    def __init__(self, file_path, dtype=None, cols=None):
        self.file_path = file_path
        self.dtype = dtype
        self.usecols = cols

    def read_csv(self):
        """
        Reads the CSV file and returns the data as a pandas DataFrame.

        Returns:
            pandas.DataFrame: The data read from the CSV file.
        """
        # try:
        data = pd.read_csv(self.file_path, dtype=self.dtype,
                        usecols=self.usecols)
        # except ValueError as e:
        #     data = pd.read_csv(self.file_path)
        #     if self.dtype:
        #         # print(e, "\n converting columns with .astype() instead")
        #         for col, dt in self.dtype.items():
        #             data[col] = data[col].astype(dt)
        return data
    
    def write_csv(self):
        """
        Writes the column names as the header to the CSV file.
        """
        with open(self.file_path, 'w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=self.usecols)
            writer.writeheader()

    def append_csv(self, row_data):
        """
        Appends a row of data to the CSV file.

        Args:
            row_data (list): The data to be appended as a row in the CSV file.
        """
        with open(self.file_path, mode='a', newline='') as file:
            writer = csv.writer(file)
            writer.writerow(row_data)
