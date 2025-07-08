import rospy


def read_waypoint_file(waypoint_file_dir):
    waypointX, waypointY, waypointHeading = [], [], []

    with open(waypoint_file_dir, 'r') as f:
        while True:
            line = f.readline().strip()
            if line == "end_header":
                break
            if line.startswith("element vertex"):
                pointNum = int(line.split()[-1])

        for _ in range(pointNum):
            line = f.readline().strip().split()
            if len(line) < 3:
                rospy.logerr("Invalid waypoint format.")
                exit(1)
            x, y, heading = map(float, line)
            waypointX.append(x)
            waypointY.append(y)
            waypointHeading.append(heading)

    return waypointX, waypointY, waypointHeading


def read_object_list_file(object_list_file_dir):
    rospy.loginfo(f"Opening object list file: {object_list_file_dir}")

    with open(object_list_file_dir, 'r') as f:
        parts = []
        while len(parts) < 9:
            line = f.readline()
            if not line:
                rospy.logfatal("Unexpected end of file while reading object data.")
                rospy.signal_shutdown("Malformed object file")
                return None
            parts += line.strip().split()

        rospy.loginfo(f"Parsed object parts: {parts}")

        try:
            objID = int(parts[0])
            objMidX = float(parts[1])
            objMidY = float(parts[2])
            objMidZ = float(parts[3])
            objL = float(parts[4])
            objW = float(parts[5])
            objH = float(parts[6])
            objHeading = float(parts[7])
            objLabel = parts[8].strip('"')
        except Exception as e:
            rospy.logfatal(f"Error parsing object values: {e}")
            rospy.signal_shutdown("Parse error")
            return None

        # Handle multi-word label (e.g., "dining table")
        if not parts[8].endswith('"'):
            rest = []
            while True:
                word = f.readline().strip()
                if word == '':
                    rospy.logfatal("Unterminated object label")
                    rospy.signal_shutdown("Malformed label")
                    return None
                rest.append(word)
                if word.endswith('"'):
                    break
            objLabel += ' ' + ' '.join(rest).strip('"')

    rospy.loginfo(f"Object label: {objLabel}")
    return objID, objMidX, objMidY, objMidZ, objL, objW, objH, objHeading, objLabel

