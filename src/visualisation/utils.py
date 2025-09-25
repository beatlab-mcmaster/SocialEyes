import numpy as np
import cv2


def draw_gaze(frame, gaze_center, blink_center, blink_id=np.nan,
              inner_circle_color = (255,255,255), outer_circle_color = (0,0,0),
              outer_circle_radius = 8, radius_diff = 2,
              overlay_font=False, overlay_text = "",
              font_scale = 0.25, font_color=(150,150,150), font_thickness=1,
              x_off = -1, y_off=3,
              line_length = 18, line_length_diff = 8):

      gaze_center = (int(gaze_center[0]), int(gaze_center[1]))
      blink_center = (int(blink_center[0]), int(blink_center[1]))
      outer_circle_color = (
          tuple(int(255 * c) for c in outer_circle_color)
          if all(0.0 <= c <= 1.0 for c in outer_circle_color) else outer_circle_color
      )

      """
        Customized gaze/blink indicator for SocialEyes.

        Args:
            frame: Image to draw on.
            gaze_center: (x, y) for gaze marker.
            blink_center: (x, y) for blink marker.
            blink_id: If NaN, draws gaze; else draws blink.
            inner_circle_color: Color for inner circles/lines.
            outer_circle_color: Color for outermost circle/line.
            outer_circle_radius: Outermost circle radius.
            radius_diff: Difference between circle radii.
            overlay_font: Whether to overlay text.
            overlay_text: Text to overlay.
            font_scale: Font scale for overlay text.
            font_color: Color for overlay text.
            font_thickness: Thickness for overlay text/lines.
            x_off, y_off: Offsets for overlay text.
            line_length: Outermost blink line length.
            line_length_diff: Difference between blink line lengths.

        Returns:
            Frame with gaze or blink marker drawn.
     """

      if np.isnan(blink_id):
          for i, radius in enumerate(range(outer_circle_radius, 0, -1*radius_diff)):
              ## Pick color for the circles
              if i==0:
                  color = outer_circle_color #outermost circle has a unique color for each device
              elif i%2!=0:
                  color = inner_circle_color #following inwards from the outer circle(i==0) every odd numbered ring (i == 1,3,..) is white
              else:
                  color = (0,0,0) #and every even ring (i == 2,4,...) is black
              # Overlay circle on frame
              frame = cv2.circle(frame, gaze_center, radius, color, -1)
      else:
          #if blink (draw a line at give blink_center)
          for i, length in enumerate(range(line_length, 0, -1*line_length_diff)):
              ## Pick color for the circles
              if i==0:
                  color = outer_circle_color #outermost line has a unique color for each device
              elif i%2!=0:
                  color = inner_circle_color #following inwards from the outer circle(i==0) every odd numbered line (i == 1,3,..) is white
              else:
                  color = (0,0,0) #and every even line (i == 2,4,...) is black
              frame = cv2.line(frame, (blink_center[0]-length//2, blink_center[1]), (blink_center[0]+length//2, blink_center[1]), color, thickness=font_thickness*3)

      if overlay_font:
          frame = cv2.putText(frame, overlay_text, (gaze_center[0]+x_off, gaze_center[1]+y_off), cv2.FONT_HERSHEY_SIMPLEX , font_scale, font_color, font_thickness, cv2.LINE_AA)

      return frame


def draw_bbox(frame, df, x_col = "source_x", y_col="source_y", w_col = "source_w", h_col = "source_h", alternate_labels = False,
              box_color=(0, 255, 122), text_color=(255,255,255), thickness=2, font_scale = 0.7, font_thickness=2, label_bg = (0,0,0), bbox_label=True,
              label_y_pad = 20, pad1=4, pad2=1, pad3=2):
    """
        Draws bounding boxes and optional labels on a frame for each row in a DataFrame.

        Args:
            frame: Image to draw on.
            df: DataFrame with bounding box and label info.
            x_col, y_col, w_col, h_col: Column names for bbox.
            alternate_labels: Alternate label position for each box.
            box_color: Color for bounding box.
            text_color: Color for label text.
            thickness: Thickness of bounding box lines.
            font_scale: Font scale for label text.
            font_thickness: Thickness for label text.
            label_bg: Background color for label.
            bbox_label: Whether to draw labels.
            label_y_pad: Vertical padding for label position.
            pad1, pad2, pad3: Padding for label background and text.

        Returns:
            Frame with bounding boxes (and labels) drawn.
    """
    for i, (_, row) in enumerate(df.iterrows()):
        # Draw bbox
        x, y, w, h = int(row[x_col]), int(row[y_col]), int(row[w_col]), int(row[h_col])
        frame = cv2.rectangle(frame, (x, y), (x + w, y + h), box_color, thickness)

        if bbox_label:
            if alternate_labels:
                # Alternate label position: top if even, bottom if odd
                label_y = y + label_y_pad if i % 2 == 0 else y + h - label_y_pad
            else:
                label_y = y + label_y_pad

            # Draw label
            label = f"{row['face_name']} ({row['confidence']:.2f})"
            (text_width, text_height), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, font_scale, font_thickness)
            cv2.rectangle(frame, (x, label_y - text_height - pad1),
                          (x + text_width, label_y), label_bg, - pad2)
            cv2.putText(frame, label, (x, label_y - pad3),
                        cv2.FONT_HERSHEY_SIMPLEX, font_scale, text_color, font_thickness, cv2.LINE_AA)
    return frame