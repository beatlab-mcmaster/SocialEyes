# Visualisation Module

The visualisation module is responsible for plotting multi-person eye-tracking data to support exploratory analysis. For details on the available visualisation modes, please refer to the SocialEyes paper [1].

As with the homography module, this module's functions are accessible through the [OfflineInterface](../offlineInterface/) module. It also implements the same logic to merge the three primary data streams of i) egoview, ii) gaze, and iii) centralview.  The egoview stream serves as the temporal reference, meaning that the merged dataset adopts its sampling rate, which can act as a bottleneck for downstream resolution.

Given that visualising social and multi-person eye-tracking data is an evolving area of research, this module is under active development and subject to frequent updates. We incourage community contributions to expand the available modes of visualisations in this module!


## References

[1] Shreshth Saxena, Areez Visram, Neil Lobo, Zahid Mirza, Mehak Khan, Biranugan Pirabaharan, Alexander Nguyen, and Lauren K Fink. 2025. SocialEyes: Scaling Mobile Eye-tracking to Multi-person Social Settings. In Proceedings of the 2025 CHI Conference on Human Factors in Computing Systems (CHI '25). Association for Computing Machinery, New York, NY, USA, Article 751, 1–19. [https://doi.org/10.1145/3706598.3713910](https://doi.org/10.1145/3706598.3713910)

