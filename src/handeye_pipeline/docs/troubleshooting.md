# Troubleshooting

## `cv2.aruco` is unavailable

Install an OpenCV build with contrib modules. On ROS2 Humble systems, start with:

```bash
sudo apt install python3-opencv
```

## Too few corners

Move the board closer, improve lighting, reduce motion blur, and verify the configured board size, square length, marker length, and dictionary.

## TF lookup fails

Confirm these frames exist:

```bash
ros2 run tf2_ros tf2_echo link_base link_eef
```

If your robot uses different frame names, update the config file.

## Bad calibration result

Common causes:

- Not enough samples.
- Samples are too similar.
- Board flexes or moves relative to the end effector.
- Camera intrinsics are wrong.
- Mixed frame conventions in hand-written sample files.

Run:

```bash
handeye-validate --config config/uf850_realsense_eye_to_hand.yaml --result data/handeye_result.yaml
```
