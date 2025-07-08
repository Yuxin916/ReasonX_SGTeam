import random
import rospy
from utils.read_in import read_waypoint_file, read_object_list_file


def decide_numerical_answer_random():
    number = random.randint(1, 10)
    return number

def decide_traj_follow(waypoint_file_dir):
    rospy.loginfo("Reading waypoint file...")
    try:
        waypointX, waypointY, waypointHeading = read_waypoint_file(waypoint_file_dir)
        rospy.loginfo("Waypoints loaded: %d", len(waypointX))
    except Exception as e:
        rospy.logfatal(f"Failed to read waypoint file: {e}")
        rospy.signal_shutdown("Waypoint load error")
        return

    return waypointX, waypointY, waypointHeading