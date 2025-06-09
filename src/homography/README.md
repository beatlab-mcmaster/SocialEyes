# Homography Module

The homography module is responsible for mapping gaze points from **egoview** to **centralview**. The current implementation of this module uses the deep learning based approach of SuperPoint+SuperGlue [1][2], however, alternative approaches should be tested for different usecases. The module functions are interfaced through the [OfflineInterface](../offlineInterface/) module.

## Merge logic

The Homography module merges three different data streams: i) egoview, ii) gaze, and iii) centralview. Each of these streams can have different sample rates or temporal resolutions. For instance, in our Utility test, the gaze is sampled at 200 Hz and egoview at 30 Hz from the Pupil Labs Neon eye-trackers, while the centralview video was sampled at 60Hz. 

The module merges the three data streams using the egoview stream as the temporal reference. As a result, the merged data inherits the sampling rate of the egoview stream, which acts as the bottleneck for overall temporal resolution. Future implementations should take note of this bottleneck and consider alternative approaches if needed.


## References

[1] D. DeTone, T. Malisiewicz and A. Rabinovich, "SuperPoint: Self-Supervised Interest Point Detection and Description," 2018 IEEE/CVF Conference on Computer Vision and Pattern Recognition Workshops (CVPRW), Salt Lake City, UT, USA, 2018, pp. 337-33712, doi: 10.1109/CVPRW.2018.00060.
[2] Paul-Edouard Sarlin, Daniel DeTone, Tomasz Malisiewicz, & Andrew Rabinovich (2020). SuperGlue: Learning Feature Matching with Graph Neural Networks. In CVPR.