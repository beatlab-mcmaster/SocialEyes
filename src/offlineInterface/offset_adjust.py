"""
offset_adjust.py

Author: Biranugan Pirabaharan, Mehak Khan, Shreshth Saxena
Purpose: This class adjust timestamp offsets in world files based on given data.
"""

import os
from sklearn import linear_model
import numpy as np
import pandas as pd
import matplotlib as plt
from tqdm import tqdm        

try:
    from offlineInterface.csv_processor import CSVProcessor
except:
    #resolve relative paths when executing the interface independently from src/offlineInterface/    
    import sys
    sys.path.append("../")
    from offlineInterface.csv_processor import CSVProcessor

class TimeOffsetAdjuster:
    """
    A class that adjusts the timestamps in eye-tracking glasses data based on collected time offsets during recording.

    Attributes:
        device_name (str): Name of the device to identify in offsets dataframe.
        offsets_file (str): Path to the offsets dataframe.
        device_offsets_df (obj): A pandas DataFrame that offsets for the device.

    Methods:
        __init__(self, offsets_file): Initializes the TimeOffsetAdjuster object.
        load_offsets(self, offsets_file): Loads the time offsets from a CSV file.
        calculate_linear_fit(self, save_plot): Calculates the linear fit for device offsets.
        adjust_files(self, file_paths, timestamp_col, local_tz): Adjusts the timestamps in provided list of files.

    """

    def __init__(self, device_name, offsets_file, save_plot = False):
        self.device_name = device_name
        self.offsets_file = offsets_file
        self.device_offsets_df = self.load_offsets(offsets_file)
        self.ransac = self.calculate_linear_fit(save_plot)

    def load_offsets(self, offsets_file):
        """
        Loads the time offsets from a CSV file and creates a dictionary 
        to store the mean time offsets and timestamps for each device.

        Args:
            offsets_file (str): The path to the CSV file containing the time offsets.
        """
        offsets_df = CSVProcessor(offsets_file).read_csv()
        return offsets_df[offsets_df["device"] == self.device_name] #filter out offsets for the device

    def calculate_linear_fit(self, save_plot=False):
        """
        Calculates the RANSAC linear fit for each device to predict offset at a given timestamp.
        
        Args:
            save_plot (bool): Set true to save the plot for regression fit in offsets file directory.
        """
        
        X= self.device_offsets_df["timestamp [ns]"].to_numpy().reshape(-1,1) 
        y= self.device_offsets_df["mean time offset [ms]"].to_numpy().reshape(-1, 1)
        ransac = linear_model.RANSACRegressor()
        ransac.fit(X, y)

        if save_plot:
            #Save RANSAC fit plot
            dirname = os.path.dirname(self.offsets_file)
            plt.plot(self.device_offsets_df["timestamp [ns]"], self.device_offsets_df["mean time offset [ms]"], label="mean time offset [ms]")
            plt.plot([X.min(), X.max()], [ransac.predict(np.array(X.min()).reshape(1,-1))[0,0], ransac.predict(np.array(X.max()).reshape(1,-1))[0,0]], label = "RANSAC fit")
            plt.savefig(os.path.join(dirname, f"RANSAC_fit_{self.device_name}.png"))
            plt.close()
        return ransac

    def adjust_files_ransac(self, file_paths, ts_key = "timestamp [ns]", local_tz = "Canada/Eastern", **kargs):
        """
        Adjusts the timestamps in provided files and saves them as a new file with prefix "ts_corr_".

        Args:
            file_paths (list): A list of dataframe files.
            timestamp_col (str): Column name for the timestamp column in dataframe.
            local_tz (str): Local timezone to which the corrected timezones will be converted.
            tqdm_desc (str): description field for the tqdm progress bar.
        """

        for file_ in tqdm(file_paths, **kargs):
            df = pd.read_csv(file_)            
            #correct timestamp offsets for timestamp cols
            for col in df.columns:
                if ts_key in col:
                    offset_col = col.replace(ts_key, "offset [ms]")
                    ts_corr_col = col.replace(ts_key, "timestamp_corrected")
                    df[offset_col] = self.ransac.predict(np.array(df[col]).reshape(-1,1))
                    df[ts_corr_col] = df[col] + df[offset_col]*1e6 #offsets are in ms
                    df[col.replace(ts_key, "datetime")] = pd.to_datetime(df[ts_corr_col], utc=True).dt.tz_convert(local_tz)
            #save dataframe
            df.to_csv(os.path.join(os.path.dirname(file_), "ts_corr_"+os.path.basename(file_)))

    def adjust_files(self, file_paths, ts_key = "timestamp [ns]", local_tz = "Canada/Eastern", **kargs):
        """
        This method is suitable for processing small-length recordings. It reads CSV files, identifies timestamp columns
        based on a given key, corrects offsets using preloaded device offset data, and adds corrected timestamp columns
        to the data. The corrected files are saved with a modified filename.

        Args:
            file_paths (list of str): Paths to the input CSV files.
            ts_key (str, optional): Substring to identify timestamp columns in the CSV files. Default is "timestamp [ns]".
            local_tz (str, optional): Timezone to convert the corrected timestamps to. Default is "Canada/Eastern".
            **kargs: Additional arguments to pass to `tqdm` for progress bar customization.

        """

        for file_ in tqdm(file_paths, **kargs):
            df = pd.read_csv(file_)            
            #correct timestamp offsets for timestamp cols
            for col in df.columns:
                if ts_key in col:
                    temp_df = pd.merge_asof(df.sort_values(by = col), 
                                            self.device_offsets_df.sort_values(by=ts_key), 
                                            left_on = col, right_on = ts_key, 
                                            direction="nearest")
                    ts_corr_col_name = col.replace(ts_key, "timestamp_corrected")
                    df[ts_corr_col_name] = (df[col] + temp_df["mean time offset [ms]"]*1e6).astype(int) #offsets are in ms
                    df[col.replace(ts_key, "datetime")] = pd.to_datetime(df[ts_corr_col_name], utc=True).dt.tz_convert(local_tz)
            #save dataframe
            df.to_csv(os.path.join(os.path.dirname(file_), "ts_corr_"+os.path.basename(file_)))
