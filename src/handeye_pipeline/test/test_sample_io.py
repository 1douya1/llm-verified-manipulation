from handeye_pipeline.sample_io import append_sample, load_samples, make_sample, validate_sample_file


def test_sample_file_validation(tmp_path):
    path = tmp_path / "samples.yaml"
    sample = make_sample(
        {"translation": [0, 0, 0], "rotation": [0, 0, 0, 1]},
        {"translation": [1, 0, 0], "rotation": [0, 0, 0, 1]},
        {
            "robot_base": "link_base",
            "robot_ee": "link_eef",
            "camera_optical": "camera_color_optical_frame",
            "calibration_board": "charuco_board",
        },
    )
    append_sample(path, sample)
    assert validate_sample_file(path)
    assert load_samples(path)[0]["id"] == sample["id"]
