""" Functions and classes for event-based processing.
"""

import copy

import numpy as np
import pandas as pd

from . import helpers


class Event:
    """
    Base class for a single event.
    An event is similar to a dictionary, but this class makes sure that there
    are at least the attributes 'start_t', 'end_t' and 'label' which are important
    for event processing.
    """

    def __init__(self, start_t, end_t, label, **kwargs):
        assert end_t >= start_t
        self.start_t = start_t
        self.end_t = end_t
        self.label = label
        self.properties = kwargs  # dictionary for all kinds of properties

    def set_start_time(self, start_t):
        """Changes the start time of the event."""
        assert start_t <= self.end_t
        self.start_t = start_t

    def set_end_time(self, end_t):
        """Changes the end time of the event."""
        assert end_t >= self.start_t
        self.end_t = end_t

    def update_properties(self, **kwargs):
        """Updates the properties dictionary of the event."""
        self.properties.update(**kwargs)

    def set_property(self, key, value):
        """Updates one key inf the properties dictionary."""
        if key == "start_t":
            self.start_t = value
        elif key == "end_t":
            self.end_t = value
        elif key == "label":
            self.label = value
        else:
            self.properties[key] = value

    def get_property(self, key):
        """Return the value of one requested property of the event."""
        if key == "start_t":
            return self.start_t
        elif key == "end_t":
            return self.end_t
        elif key == "label":
            return self.label
        else:
            return self.properties[key]

    def __getitem__(self, key):
        """Allows the Event to be treated as if it was a dictionary."""
        return self.get_property(key)

    def __setitem__(self, key, value):
        """Allows the Event to be treated as if it was a dictionary."""
        self.set_property(key, value)

    def to_dict(self):
        """Returns the event as a dictionary."""
        out = dict()
        out["start_t"] = self.start_t
        out["end_t"] = self.end_t
        out["label"] = self.label
        out.update(self.properties)
        return out


class DenseEventSequence:
    """
    Main class for event-based data processing.

    This class defines a sequence of events which is basically a list of Event-objects.
    However, this sequence has to be dense in the sense of that neither gaps nor any
    overlap between events are allowed.
    Gaps in the data are treated as events with the label 'gap'.
    Additionally, no events with the same label (or name) can follow each other.
    Subsequent events with the same label will be automatically merged into one
    larger event.
    This class makes sure that these requirements are fulfilled.
    """

    def __init__(self, events=None, verbose=False):
        if events is None:
            events = list()
        self.events = events
        self.verbose = verbose

    def __getitem__(self, item):
        return self.events.__getitem__(item)

    def __iter__(self):
        return self.events.__iter__()

    def append(self, new_event, assert_alternating_event=True):
        """Appends a new event at the end of the sequence.

        Args:
            new_event: event to be appended to the sequence.

            assert_alternating_event: if True, then it is asserted that events have to
            be added in alternating order (don't add two events with the same label
            after each other). If this can be assumend, we can turn off the automatism
            which checks if the sequence consists still of alternativ events. This
            saves some computational time while building the sequence.
        """
        assert isinstance(new_event, Event)
        if len(self.events) == 0:
            # initialize sequence if this is the first event to be appended
            self.events.append(new_event)
        else:
            # only add new events, if there is no gap between the new and the last event
            last_event = self.events[-1]
            assert (
                last_event.end_t == new_event.start_t
            ), "Make sure there are no gaps between events, or that there is no overlap."
            if assert_alternating_event:
                assert (
                    last_event.label != new_event.label
                ), "Event label must differ from the last event in the sequence."

            self.events.append(new_event)

        if not assert_alternating_event:
            # If we cannot be sure that events have been added in an alternating order,
            # then we have to make sure, each time a new event is added, that
            # consecutive events with the same label are merged.
            self.merge_consecutive_events()

    def __len__(self):
        return len(self.events)

    def remove(self, event):
        """Removes an event from the sequence"""
        index = self.events.index(event)

        if index - 1 >= 0:
            previous_event = self.events[index - 1]
            previous_event.end_t = event.end_t

        self.events.remove(event)
        self.merge_consecutive_events()

    def merge_consecutive_events(self):
        """
        Merges all consecutive events which have the same type, e.g. 2 fixations
        into 1 fixation.

        This algorithm goes through all events. Whenever two events are labelled
        equally, they are added to the same 'merge group', i.e. a collection of events
        which will be merged later.
        Whenever two events are not equal, a new merge group is started.
        """
        to_be_merged = []  # list for all merge groups
        merge_group = []  # starts an empty merge group
        prev_ev = None
        for ev in self.events:
            if prev_ev is None:
                prev_ev = ev  # skip first event
                continue

            if prev_ev.label == ev.label:
                # if events are of the same type, start a new merge group or append to
                # existing non-empty one
                if len(merge_group) == 0:
                    merge_group = [prev_ev, ev]
                else:
                    merge_group.append(ev)
            else:
                # if events are not equal, save previous merge group and start a new one
                if len(merge_group) > 0:
                    to_be_merged.append(merge_group)
                merge_group = []

            prev_ev = ev

        # don't forget the last merge group
        if len(merge_group) > 0:
            to_be_merged.append(merge_group)

        # merge all events which are in the same merge groups
        for merge_group in to_be_merged:
            # get first and last event in this group
            first_event = merge_group[0]
            last_event = merge_group[-1]

            # set end time of first event to end time of last event
            first_event.end_t = last_event.end_t
            if self.verbose:
                print(f"Merged events from {first_event.start_t} to {last_event.end_t}")

            # delete all other events in the group
            for ev in merge_group[1:]:
                self.events.remove(ev)

    def to_list(self):
        """
        Call the .to_dict method of each event in the sequence and returns them as
        a list of dictionaries for better interpretability.
        """
        return [ev.to_dict() for ev in self.events]

    def copy(self):
        """Returns a copied instance of this object."""
        events = copy.deepcopy(self.events)
        return DenseEventSequence(events=events)


def parse_labels_to_event_sequence(time_axis, labels, verbose=False):
    """
    Transforms a sample-based representation of labels into an event-based
    representation, based on an DenseEventSequence-object.

    Args:
        labels: list of labels
        time_axis: list of corresponding time points

    Returns:
        event_sequence: DenseEventSequence-object
    """
    event_sequence = DenseEventSequence(verbose=verbose)

    previous_label = None
    previous_t = None
    for i, (t, label) in enumerate(zip(time_axis, labels)):
        if previous_label is None:
            # add first event
            event = Event(t, t, label)
            event_sequence.append(event)
            previous_label = label
            previous_t = t
            continue

        if label == previous_label:
            # update end time of last event
            event_sequence.events[-1].set_end_time(t)
        else:
            # update end time of last event
            event_sequence.events[-1].set_end_time(t)

            # create new event
            event = Event(t, t, label)
            event_sequence.append(event)

        previous_label = label
        previous_t = t

    return event_sequence


def transform_event_sequence_to_samples(event_sequence, time_axis, mapping=None):
    """Transform a event-sequence into a stream of labelled samples.

    Args:
        event_sequence: input DenseEventSequence object
        time_axis: time axis to be labelled
        mapping (optional, dict): dictionary mapping labels to custom values
    """
    n_samples = len(time_axis)
    samples = pd.Series(
        np.zeros(
            n_samples,
        ),
        index=time_axis,
    )
    for event in event_sequence:
        if isinstance(mapping, dict):
            label = mapping[event.label]
        else:
            label = event.label

        samples.loc[event.start_t : event.end_t] = label

    return samples


def filter_microsaccades(
    event_sequence,
    saccade_label="gap",
    ang_thr=2,
    time_thr=0.05,
    verbose=False,
    make_copy=False,
):
    """Filter out all microsaccades from an event sequence.

    Args:
        event_sequence: Input DenseEventSequence objcet
        saccade_label (optional): label which identifies a saccade
        ang_thr (optional): spatial threshold in degrees for amplitude of microsaccades
        time_thr (optional): temporal threshold for length of microsaccades
        verbose (optional): whether to print out messages or not
        make_copy (optional): whether to make a copy of the sequence first or not

    Returns:
        Filtered DenseEventSequence
    """
    if make_copy:
        event_sequence = event_sequence.copy()

    i = 0
    while i < len(event_sequence):
        ev = event_sequence[i]  # get event

        if (
            (ev.label == saccade_label)
            and (ev["amplitude_deg"] <= ang_thr)
            and (ev["duration_sec"] <= time_thr)
        ):
            event_sequence.remove(ev)  # remove event if it is a microsaccade
            if verbose:
                print(f"Removed event (microsaccade): {ev.to_dict()}")
            i = i - 1  # go back to previous event

        i += 1

    return event_sequence


def filter_short_fixations(
    event_sequence,
    fixation_label="fixation",
    time_thr=0.05,
    verbose=False,
    make_copy=False,
):
    """
    Filter out all fixations shorter than a given threshold value from the
    event sequence.

    Args:
        event_sequence: Input DenseEventSequence objcet
        fixation_label (optional): label which identifies a fixation
        time_thr (optional): temporal threshold for length of fixations
        verbose (optional): whether to print out messages or not
        make_copy (optional): whether to make a copy of the sequence first or not
    """
    if make_copy:
        event_sequence = event_sequence.copy()

    i = 0
    while i < len(event_sequence):
        ev = event_sequence[i]  # get event

        if (ev.label == fixation_label) and (ev["duration_sec"] <= time_thr):
            if verbose:
                print(f"Removed event (too short fixation): {ev.to_dict()}")
            event_sequence.remove(ev)  # remove event if it is a microsaccade
            i = i - 1  # go back to previous event

        i += 1

    return event_sequence


def get_event_points_and_amplitude(
    ev, time_axis, gaze_xy_normalized, gaze_xy_distorted
):
    """Given an event, find the start and end points of this event, and
    calculate the amplitude in degrees and pixel space.

    Args:
        ev (dict): Event-object
        time_axis: time axis of the recording (in seconds)
        gaze_xy_normalized: Array of normalized 2D gaze coordinates for each time point
        gaze_xy_distorted: Array of distorted (pixel) 2D gaze coordinates for each
                           time point

    Returns:
        start_x, start_y, end_x, end_y, amplitude_deg, amplitude_px
    """
    # get start and end positions
    ind_start, _ = helpers.find_previous(time_axis, ev["start_t"])
    ind_end, _ = helpers.find_previous(time_axis, ev["end_t"])

    # get amplitude in degrees
    start_x = gaze_xy_normalized[ind_start, 0]
    start_y = gaze_xy_normalized[ind_start, 1]
    end_x = gaze_xy_normalized[ind_end, 0]
    end_y = gaze_xy_normalized[ind_end, 1]
    coords_xy = np.array([[start_x, start_y], [end_x, end_y]])
    amplitude_deg = helpers.get_consecutive_delta_angles_from_xy(
        coords_xy, out_format="degrees"
    )[0]

    # get amplitude in pixels
    start_x = gaze_xy_distorted[ind_start, 0]
    start_y = gaze_xy_distorted[ind_start, 1]
    end_x = gaze_xy_distorted[ind_end, 0]
    end_y = gaze_xy_distorted[ind_end, 1]
    coords_xy = np.array([[start_x, start_y], [end_x, end_y]])
    amplitude_px = np.sqrt(np.sum((coords_xy[1, :] - coords_xy[0, :]) ** 2))

    return start_x, start_y, end_x, end_y, amplitude_deg, amplitude_px


def update_events_with_stats(
    event_sequence,
    time_axis,
    gaze_xy_normalized,
    gaze_xy_distorted,
    velocity,
    make_copy=False,
):
    """Calculates some statistics for each event and updates the event's properties
    dictionary with these statistics.

    Args:
        input_events: input DenseEventSequence
        time_axis: time axis of the recording (in seconds)
        gaze_xy_normalized: array of normalized 2D gaze coordinates per time point
        gaze_xy_distorted: array of distorted (pixel) 2D gaze coordinates per time point
        velocity: velocity of gaze point at each time point

    Returns:
        Updated EventSequence object
    """
    if make_copy:
        event_sequence = event_sequence.copy()

    for ev in event_sequence.events:
        # get start position, end position and amplitude
        (
            start_x,
            start_y,
            end_x,
            end_y,
            amp_deg,
            amp_px,
        ) = get_event_points_and_amplitude(
            ev, time_axis, gaze_xy_normalized, gaze_xy_distorted
        )
        ev.set_property("start_x", start_x)
        ev.set_property("start_y", start_y)
        ev.set_property("end_x", end_x)
        ev.set_property("end_y", end_y)
        ev.set_property("amplitude_deg", amp_deg)
        ev.set_property("amplitude_px", amp_px)
        ev.set_property("instance", amp_px)

        # get duration
        ev.set_property("duration_sec", ev.end_t - ev.start_t)

        # get mean and peak velocity
        ind_start, _ = helpers.find_previous(time_axis, ev.start_t)  # find start sample
        ind_end, _ = helpers.find_previous(time_axis, ev.end_t)  # find end sample
        ind_end = min(ind_end, len(gaze_xy_normalized))  # bugfix
        ind_start = max(ind_start, 0)
        if ind_end > ind_start:
            ev.set_property("mean_vel", velocity[ind_start:ind_end].mean())
            ev.set_property("peak_vel", velocity[ind_start:ind_end].max())
        else:
            # bugfix, in the raw annotations there are some events with duration zero.
            # These will be filtered out later by the microsaccade filter, so here, we
            # will just assign 'NaN' if it cannot be calculcated
            ev.set_property("mean_vel", np.nan)
            ev.set_property("peak_vel", np.nan)

    return event_sequence
