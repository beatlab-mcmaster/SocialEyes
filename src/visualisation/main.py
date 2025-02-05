"""
main.py

Author: Shreshth Saxena
Purpose: Implementation of the visualisation module for SocialEyes.
"""

import time
import os
import argparse
import concurrent.futures
import seaborn as sns
import cv2
import numpy as np
import matplotlib.pyplot as plt
from matplotlib import cm 
from scipy.ndimage import gaussian_filter
from scipy.spatial import ConvexHull
from tqdm import tqdm

try:
    from visualisation.homography_visualiser import HomographyVisualizer
    from offlineInterface.file_processing import FileProcessor
    from analysis.main import generate_heatmap, plot_heatmap
    from homography.config import config
except:
    #resolve relative paths when executing independently    
    import sys
    sys.path.append("../")
    from visualisation.homography_visualiser import HomographyVisualizer
    from analysis.main import generate_heatmap, plot_heatmap
    from offlineInterface.file_processing import FileProcessor
    from homography.config import config


def viz_homography(input_dir, cam_dir, output_dir="./", custom_dir_structure=True, search_key= ""):
    """
    Visualize homography results by rendering videos from glasses and central camera.

    Args:
        input_dir (str): Directory containing input files (worldview video and gaze data).
        cam_dir (str): Directory containing centralview camera files.
        output_dir (str, optional): Directory to save output videos. Defaults to "./".
        custom_dir_structure (bool, optional): Whether to use a custom directory structure for input files. Defaults to True.
        search_key (str, optional): Key for filtering specific glasses data. Defaults to "".

    Returns:
        None: This function does not return a value, but it creates visualizations of the homography processing.
    """
        
    worldview_video_paths, worldview_timestamps_paths, gaze_paths, glasses_names = FileProcessor.parse_glasses_dir(input_dir, custom_dir_structure, search_key= search_key)
    central_video_path, central_timestamps_path = FileProcessor.parse_central_camera_dir(cam_dir)
    gaze_tranforms_paths = [os.path.join(output_dir, f'transformed_gaze_{name}.csv') for name in glasses_names]
    colors = sns.color_palette("colorblind", len(glasses_names))

    # # Create Visualizer instances
    viz_instances = []
    for i in range(len(glasses_names)):
        viz_instances.append(HomographyVisualizer(
            config['homography']['resize'],
            worldview_video_paths[i],
            worldview_timestamps_paths[i],
            gaze_paths[i],
            gaze_tranforms_paths[i],
            central_video_path,
            central_timestamps_path,
            colors[i],
            glasses_names[i]
        ))

    concurrent_start = time.time()
    # Use ProcessPoolExecutor to execute perform_homography concurrently
    with concurrent.futures.ThreadPoolExecutor() as executor:
        # Submit all tasks to the executor
        futures = [
            executor.submit(
                instance.render_single_device,
                os.path.join(output_dir, f"homography_viz_{instance.device_name}.mp4")
            )
            for instance in viz_instances
        ]

    for future in concurrent.futures.as_completed(futures):
        result = future.result()
    
    concurrent_final = time.time()
    print("Time for concurrent: ", concurrent_final - concurrent_start)

def create_grid(images_g, image_c, grid_res, 
                grid_rows = 4, grid_cols = 9,
                center_rows_range = (1,3), center_cols_range = (3,6)): 
    """
    Create a grid layout of images for visualization. 
    Note that default values are used from the SocialEyes Utility Test, only for example purposes. 

    Args:
        images_g (list of np.ndarray): List of gaze images to be arranged in the grid.
        image_c (np.ndarray): Central image to be displayed in the center of the grid.
        grid_res (tuple): Resolution (width, height) for the output grid.
        grid_rows (int, optional): Number of rows in the grid. Defaults to 4.
        grid_cols (int, optional): Number of columns in the grid. Defaults to 9.
        center_rows_range (tuple, optional): Row range for placing the central image. Defaults to (1, 3).
        center_cols_range (tuple, optional): Column range for placing the central image. Defaults to (3, 6).

    Returns:
        np.ndarray: A canvas containing the arranged grid of images.
    """
    #Init dimensions
    image_width = grid_res[0]//grid_cols
    image_height = grid_res[1]//grid_rows
    canvas = np.zeros((grid_res[1], grid_res[0], 3), dtype=np.uint8)

    #Resize images
    images_g_res = [cv2.resize(image, (image_width, image_height),cv2.INTER_AREA) for image in images_g]
    image_c_res = cv2.resize(image_c, (image_width*3, image_height*2),cv2.INTER_AREA)

    image_index = 0
    for i in range(grid_rows):
        for j in range(grid_cols):
            if i in range(*center_rows_range) and j in range(*center_cols_range): 
                if i == center_rows_range[0] and j == center_cols_range[0]:
                    canvas[i*image_height:(i+2)*image_height, j*image_width:(j+3)*image_width] = image_c_res
            else:
                if image_index < len(images_g):
                    y_start = i * image_height
                    y_end = (i + 1) * image_height
                    x_start = j * image_width
                    x_end = (j + 1) * image_width
                    canvas[y_start:y_end, x_start:x_end] = images_g_res[image_index]
                    image_index += 1
    return canvas

def frames_generator(viz_instances, res=(640,480), heatmap = False, convexhull=False, **kargs):
    """
    Generate frames for visualization from multiple instances.

    Args:
        viz_instances (list): List of HomographyVisualizer instances.
        res (tuple, optional): Resolution for the output images. Defaults to (640, 480).
        heatmap (bool, optional): Flag to indicate if heatmaps should be generated. Defaults to False.
        **kargs: Additional keyword arguments for the sync_generator method.

    Yields:
        tuple: A tuple containing a list of gaze images and the combined central image.

    Raises:
        StopIteration: If any of the frame generators exhaust their frames.
        Exception: For any other error that may arise during frame generation.
    """
    frame_generators = [instance.sync_generator(**kargs) for instance in viz_instances]
    while True:
        try:
            images_g = []
            gaze_pts_c = {}
            image_c_comb = None
            for instance, gen in zip(viz_instances, frame_generators):
                image_g,_,_,_,gaze_x_c,gaze_y_c, blink_id, image_c_raw = next(gen)
                images_g.append(image_g)
                if not (heatmap or convexhull): #to display gaze points
                    image_c_comb = instance.draw_gaze(image_c_raw if image_c_comb is None else image_c_comb, (gaze_x_c, gaze_y_c), blink_id) #draw first on raw central image
                # else if no blink and gaze is in frame (when generating heatmap)
                elif np.isnan(blink_id) and 0<=gaze_x_c<res[0] and 0<=gaze_y_c<res[1]:
                    gaze_pts_c[instance.device_name] = (int(gaze_x_c),int(gaze_y_c))
            
            #all valid transformed gaze pts
            x_pts, y_pts = [pt[0] for pt in gaze_pts_c.values()], [pt[1] for pt in gaze_pts_c.values()] 
            valid_pts = np.column_stack((x_pts, y_pts))

            # import pdb
            # pdb.set_trace()

            if heatmap:
                pred_heatmap = generate_heatmap(x_pts, y_pts, res=(640, 480), sigma=20)
                pred_heatmap = plot_heatmap(pred_heatmap, colormap = cv2.COLORMAP_VIRIDIS)
                # Create overlay
                image_c_comb = cv2.addWeighted(image_c_raw, 0.7, pred_heatmap, 0.3, 0)

            elif convexhull and valid_pts.size != 0:
                # hull = ConvexHull(valid_pts)
                # vertices = valid_pts[hull.vertices].astype(np.int32) 

                #Use plt to draw hull and errorbars
                fig, ax = plt.subplots(figsize=(image_c_raw.shape[1] / 100, image_c_raw.shape[0] / 100), dpi=100)
                ax.imshow(cv2.cvtColor(image_c_raw, cv2.COLOR_BGR2RGB))  
                # vertices = np.append(hull.vertices, hull.vertices[0])
                # plt.plot(valid_pts[vertices, 0], valid_pts[vertices, 1], 'r--', lw=2, label='Convex Hull')  # Plot the convex hull
                plt.errorbar(np.mean(x_pts), np.mean(y_pts), xerr=np.std(x_pts), yerr=np.std(y_pts), fmt='o', markersize=8, capsize=5, label='Mean Point with Error Bars', color = "white")
                plt.legend(loc='upper right', framealpha=0.7)
                ax.axis('off'); ax.set_aspect('auto')
                plt.tight_layout(pad=0)

                # Convert the figure to a cv2 image (NumPy array)
                fig.canvas.draw()
                image_c_comb = np.array(fig.canvas.renderer.buffer_rgba())
                image_c_comb = cv2.cvtColor(image_c_comb, cv2.COLOR_RGB2BGR)
                plt.close(fig)  # to free memory
                
            yield images_g, image_c_comb
        except Exception as e:
            raise e

def viz_homography_grid(input_dir, cam_dir, output_dir="./", custom_dir_structure=True, 
                        output_res = (2880,960), fourcc = cv2.VideoWriter_fourcc(*'mp4v'), fps=30.0, show_heatmap=False, search_key= "", preempt = None, device_name_from_info=False):

    """
    Visualize homography results in a grid format by rendering videos from glasses and central camera.
    The function also dumps a separate video of the homography-transformed gaze heatmap (central cell in the grid).

    Args:
        input_dir (str): Directory containing input files (e.g., video or gaze data).
        cam_dir (str): Directory containing camera files.
        output_dir (str, optional): Directory to save output videos. Defaults to "./".
        custom_dir_structure (bool, optional): Whether to use a custom directory structure for input files. Defaults to True.
        output_res (tuple, optional): Resolution (width, height) for the output video grid. Defaults to (2880, 960).
        fourcc (int, optional): FourCC code for the video codec. Defaults to cv2.VideoWriter_fourcc(*'mp4v').
        fps (float, optional): Frames per second for the output video. Defaults to 30.0.
        show_heatmap (bool, optional): If True, generate and display heatmaps instead of gaze points. Defaults to False.
        search_key (str, optional): Key for filtering specific glasses data. Defaults to "".
        preempt (int or None, optional): Specifies the maximum number of frames to process before preempting; if None, all frames are processed. Defaults to None.

    Raises:
        FileNotFoundError: If the input or camera directory does not contain the expected files.
        Exception: For any other errors that may arise during video processing.
    """
        
    worldview_video_paths, worldview_timestamps_paths, gaze_paths, glasses_names = FileProcessor.parse_glasses_dir(input_dir, custom_dir_structure, search_key=search_key, device_name_from_info=device_name_from_info)
    central_video_path, central_timestamps_path = FileProcessor.parse_central_camera_dir(cam_dir)
    gaze_tranforms_paths = [os.path.join(output_dir, f'transformed_gaze_{name}.csv') for name in glasses_names]
    colors = sns.color_palette("colorblind", len(glasses_names))

    # Create Visualizer instances
    viz_instances = []
    for i in range(len(glasses_names)):
        viz_instances.append(HomographyVisualizer(
            config['homography']['resize'],
            worldview_video_paths[i],
            worldview_timestamps_paths[i],
            gaze_paths[i],
            gaze_tranforms_paths[i],
            central_video_path,
            central_timestamps_path,
            colors[i],
            glasses_names[i]
        ))

    out = cv2.VideoWriter(os.path.join(output_dir, f"viz_homography_grid{'_heatmap' if show_heatmap else '_gaze_pts'}.mp4"), fourcc, fps, output_res)
    out_central_comb = cv2.VideoWriter(os.path.join(output_dir, f"viz_homography_central_comb{'_heatmap' if show_heatmap else '_gaze_pts'}.mp4"), fourcc, fps, 
                          (config['homography']['resize'][0],config['homography']['resize'][1]))
    try:
        i=0
        for images_g, image_c_comb in tqdm(frames_generator(viz_instances, res=config['homography']['resize'], heatmap=show_heatmap,
                                                            outer_circle_radius=16, line_length=30, font_thickness=2)):
            out.write(create_grid(images_g, image_c_comb, output_res))
            out_central_comb.write(image_c_comb)
            i+=1
            if preempt is not None and i >= preempt:
                raise Exception("Pre-empting")
    except Exception as e:
        print(e)
        out.release()
        out_central_comb.release()


def viz_homography_centralonly(input_dir, cam_dir, output_dir="./", custom_dir_structure=True, 
                        output_res = (720,480), fourcc = cv2.VideoWriter_fourcc(*'mp4v'), fps=30.0, show_heatmap=False, show_hull = False, search_key= "", preempt = None, device_name_from_info=False):

    """
    Visualize homography transformed gaze of all viewers on the shared centralcam view. (No independent views are visualised)

    Args:
        input_dir (str): Directory containing input files (e.g., video or gaze data).
        cam_dir (str): Directory containing camera files.
        output_dir (str, optional): Directory to save output videos. Defaults to "./".
        custom_dir_structure (bool, optional): Whether to use a custom directory structure for input files. Defaults to True.
        output_res (tuple, optional): Resolution (width, height) for the output video grid. Defaults to (2880, 960).
        fourcc (int, optional): FourCC code for the video codec. Defaults to cv2.VideoWriter_fourcc(*'mp4v').
        fps (float, optional): Frames per second for the output video. Defaults to 30.0.
        show_heatmap (bool, optional): If True, generate and display heatmaps instead of gaze points. Defaults to False.
        search_key (str, optional): Key for filtering specific glasses data. Defaults to "".
        preempt (int or None, optional): Specifies the maximum number of frames to process before preempting; if None, all frames are processed. Defaults to None.

    Raises:
        FileNotFoundError: If the input or camera directory does not contain the expected files.
        Exception: For any other errors that may arise during video processing.
    """
        
    worldview_video_paths, worldview_timestamps_paths, gaze_paths, glasses_names = FileProcessor.parse,_glasses_dir(input_dir, custom_dir_structure, search_key=search_key, device_name_from_info = device_name_from_info)
    central_video_path, central_timestamps_path = FileProcessor.parse_central_camera_dir(cam_dir)
    gaze_tranforms_paths = [os.path.join(output_dir, f'transformed_gaze_{name}.csv') for name in glasses_names]
    colors = sns.color_palette("colorblind", len(glasses_names))

    # Create Visualizer instances
    viz_instances = []
    for i in range(len(glasses_names)):
        viz_instances.append(HomographyVisualizer(
            config['homography']['resize'],
            worldview_video_paths[i],
            worldview_timestamps_paths[i],
            gaze_paths[i],
            gaze_tranforms_paths[i],
            central_video_path,
            central_timestamps_path,
            colors[i],
            glasses_names[i]
        ))
    
    if show_heatmap and show_hull:
        raise Exception("Incorrect args: Only one of show_heatmap and show_hull should be True at a time")
    
    out_fname = f"visualize_centralonly_{'heatmap' if show_heatmap else 'convexhull' if show_hull else 'gaze_pts'}.mp4"
    out_central_comb = cv2.VideoWriter(os.path.join(output_dir, out_fname), fourcc, fps, 
                          (config['homography']['resize'][0],config['homography']['resize'][1]))
    try:
        i=0
        for _, image_c_comb in tqdm(frames_generator(viz_instances, res=config['homography']['resize'], heatmap=show_heatmap, convexhull=show_hull,
                                                            outer_circle_radius=16, line_length=30, font_thickness=2)):
            out_central_comb.write(image_c_comb)
            i+=1
            if preempt is not None and i >= preempt:
                raise Exception("Pre-empting")
    except Exception as e:
        print(e)
        out_central_comb.release()


if __name__ == "__main__":
    # Perform homography concurrently for multiple instances.
    parser = argparse.ArgumentParser(
        description='Visualise homography results',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # Add arguments
    parser.add_argument(
        '--input_dir', type=str, default='./',
        help='Path to the directory that contains data for glasses in separate dub-directories')
    parser.add_argument(
        '--cam_dir', type=str, default='./',
        help='Path to the directory that contains data for central camera recording')
    parser.add_argument(
        '--output_dir', type=str, default='./',
        help='Path to the directory in which the .npz results and optionally,'
        'the visualization images are written')
    parser.add_argument(
        '--custom_dir_structure', type=bool, default=True,
        help='If data is not downloaded from homography interface and exists in a custom directory structure')

    opt = parser.parse_args()
    viz_homography(opt.input_dir, opt.cam_dir, opt.output_dir, opt.custom_dir_structure)