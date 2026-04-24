# Hand-Eye Pipeline v0.1

This package is a self-contained calibration module under `src/handeye_pipeline`. It keeps reusable calibration logic separate from `mtc_tutorial` and the pouring/manipulation pipeline.

Core transform convention:

- `T_parent_child` maps points from child coordinates into parent coordinates.
- Samples store `T_base_ee` and `T_camera_board`.
- The default eye-to-hand solver estimates `T_base_camera`.

Recommended capture checklist:

- Use at least 15 samples.
- Cover different x/y/z positions and rotations.
- Keep the ChArUco board rigidly attached to the end effector.
- Avoid motion blur and partial board views.
- Check reprojection error before trusting the result.

Main commands:

```bash
handeye-collect --config src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml
handeye-validate --config src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml
handeye-solve --config src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml
handeye-export-tf --config src/handeye_pipeline/config/uf850_realsense_eye_to_hand.yaml
```
