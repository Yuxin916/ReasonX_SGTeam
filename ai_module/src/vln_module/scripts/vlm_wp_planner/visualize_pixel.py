import cv2
import os
import argparse

# --- Configuration ---
# Visualization parameters
marker_radius = 20
marker_color = (0, 0, 255)  # Bright Red (BGR format)
marker_thickness = 3
text_color = (255, 255, 255) # White
text_thickness = 3
font = cv2.FONT_HERSHEY_SIMPLEX
font_scale = 0.8

# --- Main Script ---

def visualize_and_save_waypoints(image_path, waypoints):
    """
    Loads an image, draws numbered waypoints, saves the result to a new folder,
    and displays it.
    """
    # 1. Check if the source image file exists
    if not os.path.exists(image_path):
        print(f"Error: Source image not found at: {image_path}")
        return

    # 2. Load the image
    image = cv2.imread(image_path)
    if image is None:
        print(f"Error: Failed to load image from {image_path}.")
        return

    print(f"Image loaded successfully. Dimensions: {image.shape[:2]} pixels.")
    print(f"Visualizing waypoints: {waypoints}")

    # 3. Draw the numbered markers on the image
    for i, (x, y) in enumerate(waypoints):
        x, y = int(x), int(y)
        cv2.circle(image, (x, y), marker_radius, marker_color, marker_thickness)
        text = str(i + 1)
        text_size = cv2.getTextSize(text, font, font_scale, text_thickness)[0]
        text_x = int(x - text_size[0] / 2)
        text_y = int(y + text_size[1] / 2)
        cv2.putText(image, text, (text_x, text_y), font, font_scale, text_color, text_thickness, cv2.LINE_AA)

    # 4. --- NEW: Prepare to save the annotated image ---
    script_directory = os.path.dirname(os.path.realpath(__file__))
    output_folder = os.path.join(script_directory, "annotated_images")
    
    # Create the output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)
    
    # Create a new filename for the annotated image
    base_filename = os.path.basename(image_path)
    name, ext = os.path.splitext(base_filename)
    annotated_filename = f"{name}_annotated{ext}"
    full_save_path = os.path.join(output_folder, annotated_filename)
    
    # 5. --- NEW: Save the image ---
    try:
        cv2.imwrite(full_save_path, image)
        print(f"Annotated image saved successfully to: {full_save_path}")
    except Exception as e:
        print(f"Error saving image: {e}")


    # 6. Display the image in a window (as before)
    window_name = "Waypoint Visualization"
    cv2.imshow(window_name, image)

    # 7. Wait for the user to press a key
    print("\nPress any key on the image window to close.")
    cv2.waitKey(0)

    # 8. Clean up and close the window
    cv2.destroyAllWindows()
    print("Window closed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Visualize and save a sequence of pixel waypoints on a specific image.")
    parser.add_argument("filename", type=str, help="The filename of the image to process (e.g., 'image_123.png').")
    parser.add_argument("waypoints", nargs='+', type=str, help="List of waypoint pixel coordinates as 'x,y' pairs (e.g., '100,200 300,400').")
    args = parser.parse_args()

    # Construct the full path to the source image
    script_directory = os.path.dirname(os.path.realpath(__file__))
    image_folder = os.path.join(script_directory, "saved_360_images")
    full_image_path = os.path.join(image_folder, args.filename)

    # Parse the waypoint strings into a list of (x, y) tuples
    parsed_waypoints = []
    for waypoint_str in args.waypoints:
        try:
            x_str, y_str = waypoint_str.split(',')
            parsed_waypoints.append((int(x_str), int(y_str)))
        except ValueError:
            print(f"Error: Invalid waypoint format '{waypoint_str}'. Expected 'x,y'.")
            exit(1)

    if parsed_waypoints:
        visualize_and_save_waypoints(full_image_path, parsed_waypoints)
        pass
    else:
        print("No valid waypoints provided.")